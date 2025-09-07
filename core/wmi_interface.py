# -*- coding: utf-8 -*-
"""
【重构】提供一个极其轻薄、扁平化的WMI交互接口。
该模块负责：
1. 管理一个后台工作线程，该线程主动、定期地轮询核心传感器（温度、转速），并将结果缓存。
2. 提供一个通用的、阻塞式的 `execute_method` 来执行所有WMI写入操作。
3. 提供三个高度优化的只读方法，分别用于UI更新、自动温控和全局刷新。
"""

import threading
import queue
import time
import math
import sys
from typing import Optional, Any, Dict, Tuple, Callable

# 如果可用，则导入WMI库，提供清晰的回退路径。
_wmi_available = False
try:
    import wmi
    import pythoncom
    _wmi_available = True
except ImportError:
    print("警告: 未找到 'wmi' 或 'pythoncom' 包。WMI功能将被禁用。", file=sys.stderr)
    wmi = None
    pythoncom = None

# 从中央设置文件导入所有必要的常量。
from config.settings import (
    WMI_NAMESPACE, DEFAULT_WMI_GET_CLASS, DEFAULT_WMI_SET_CLASS,
    WMI_GET_CPU_TEMP, WMI_GET_GPU_TEMP1, WMI_GET_GPU_TEMP2,
    WMI_GET_RPM1, WMI_GET_RPM2, WMI_GET_CHARGE_POLICY, WMI_GET_CHARGE_STOP,
    WMI_WORKER_STOP_SIGNAL, WMI_REQUEST_TIMEOUT_S,
    TEMP_READ_ERROR_VALUE, RPM_READ_ERROR_VALUE,
    CHARGE_POLICY_READ_ERROR_VALUE, CHARGE_THRESHOLD_READ_ERROR_VALUE,
    MIN_CHARGE_PERCENT, MAX_CHARGE_PERCENT
)

# 类型提示
WMIResult = Tuple[Optional[Any], Optional[Exception]]
# 【重构】请求现在是方法名和参数，不再需要复杂的action
WMIRequest = Tuple[str, Dict[str, Any], queue.Queue]

# --- 自定义异常以实现清晰的错误处理 ---
class WMIError(Exception):
    """WMI接口错误的基类异常。"""
    pass

class WMIConnectionError(WMIError):
    """当WMI连接或初始化失败时引发。"""
    pass

class WMIRequestTimeoutError(WMIError):
    """当WMI请求超时时引发。"""
    pass

class WMICommandError(WMIError):
    """当WMI方法调用在执行期间失败时引发。"""
    def __init__(self, message, original_exception=None):
        super().__init__(message)
        self.original_exception = original_exception

# ==============================================================================
# WMIWorker 线程
# ==============================================================================
class WMIWorker(threading.Thread):
    """
    后台线程，处理所有阻塞的WMI调用，并主动轮询核心传感器数据。
    """
    def __init__(self, request_queue: queue.Queue, wmi_get_class: str, wmi_set_class: str):
        super().__init__(name="WMIWorkerThread", daemon=True)
        self._request_queue = request_queue
        self._wmi_get_class_name = wmi_get_class
        self._wmi_set_class_name = wmi_set_class
        self._wmi_conn: Optional[Any] = None
        self._wmi_get_obj: Optional[Any] = None
        self._wmi_set_obj: Optional[Any] = None
        self._com_initialized: bool = False
        self.initialization_complete = threading.Event()
        self.initialization_error: Optional[Exception] = None
        
        # --- 后台轮询相关 ---
        self._stop_event = threading.Event()
        self._polling_interval_s = 1.0  # UI轮询间隔
        self._latest_core_sensor_data: Dict[str, Any] = {}
        self._data_lock = threading.Lock()

    # --- 初始化和清理 ---
    def _init_wmi(self) -> bool:
        """初始化COM并连接到WMI命名空间。"""
        if not _wmi_available or not pythoncom or not wmi:
            self.initialization_error = WMIConnectionError("WMI或pythoncom库未找到。")
            return False
        try:
            pythoncom.CoInitializeEx(pythoncom.COINIT_MULTITHREADED)
            self._com_initialized = True

            self._wmi_conn = wmi.WMI(namespace=WMI_NAMESPACE)
            self._wmi_get_obj = self._get_wmi_instance(self._wmi_get_class_name)
            self._wmi_set_obj = self._get_wmi_instance(self._wmi_set_class_name)

            if not self._wmi_get_obj or not self._wmi_set_obj:
                missing = [name for name, obj in [(self._wmi_get_class_name, self._wmi_get_obj),
                                                  (self._wmi_set_class_name, self._wmi_set_obj)] if not obj]
                error_msg = (f"未能获取WMI对象 ({', '.join(missing)})。 "
                             "请确保技嘉软件/驱动已安装并正在运行。")
                raise WMIConnectionError(error_msg)

            return True
        except Exception as e:
            self.initialization_error = e
            self._cleanup_com()
            return False

    def _get_wmi_instance(self, class_name: str) -> Optional[Any]:
        """安全地获取WMI类的第一个实例。"""
        if not self._wmi_conn: return None
        try:
            instances = self._wmi_conn.query(f"SELECT * FROM {class_name}")
            return instances[0] if instances else None
        except Exception:
            return None

    def _cleanup_com(self):
        """反初始化此线程的COM。"""
        if self._com_initialized and pythoncom:
            try:
                pythoncom.CoUninitialize()
            except Exception as e:
                print(f"COM反初始化期间出错: {e}", file=sys.stderr)
            finally:
                self._com_initialized = False

    # --- 核心逻辑 ---
    def run(self):
        """WMI工作线程的主循环，现在包含主动轮询逻辑。"""
        if not self._init_wmi():
            self.initialization_complete.set()
            return

        self.initialization_complete.set()

        while not self._stop_event.is_set():
            try:
                # 1. 处理外部请求（例如Setters）
                request = self._request_queue.get(timeout=self._polling_interval_s)
                if request == WMI_WORKER_STOP_SIGNAL:
                    break
                self._process_request(request)
            except queue.Empty:
                # 2. 如果没有请求，执行后台轮询
                self._poll_core_sensors()
        
        self._cleanup_com()

    def stop(self):
        """设置停止事件以终止主循环。"""
        self._stop_event.set()

    def get_latest_core_sensor_data(self) -> Dict[str, Any]:
        """线程安全地获取最新的传感器数据缓存。"""
        with self._data_lock:
            return self._latest_core_sensor_data.copy()

    def _poll_core_sensors(self):
        """在后台执行核心传感器（温度、转速）的轮询并更新缓存。"""
        try:
            data = self._get_core_sensors()
            with self._data_lock:
                self._latest_core_sensor_data = data
        except Exception as e:
            print(f"WMI后台轮询失败: {e}", file=sys.stderr)
            # 在失败时也更新缓存，以反映错误状态
            with self._data_lock:
                self._latest_core_sensor_data = {
                    'cpu_temp': TEMP_READ_ERROR_VALUE, 'gpu_temp': TEMP_READ_ERROR_VALUE,
                    'fan1_rpm': RPM_READ_ERROR_VALUE, 'fan2_rpm': RPM_READ_ERROR_VALUE
                }

    def _process_request(self, request: WMIRequest):
        """
        【重构】处理单个外部请求。不再需要分派表。
        """
        method_name, params, callback_queue = request
        result, exception = None, None
        try:
            # 根据方法名决定是调用Getter还是Setter
            if method_name.startswith("Set"):
                result = self._execute_set_method(method_name, **params)
            # 【重构】为特殊的合并查询提供专用处理
            elif method_name == "_get_all_sensors":
                result = self._get_all_sensors()
            elif method_name == "_get_temperatures":
                result = self._get_temperatures()
            else: # 默认为Getter
                result = self._execute_get_method(method_name, **params)
        except Exception as e:
            exception = e
        
        try:
            callback_queue.put((result, exception), block=False)
        except queue.Full:
            print("警告: WMI响应队列意外已满。正在丢弃响应。", file=sys.stderr)

    # --- WMI方法执行和值解析 ---
    def _execute_get_method(self, method_name: str, **kwargs) -> Any:
        """在GB_WMIACPI_Get对象上执行方法。"""
        if not self._wmi_get_obj: raise WMIConnectionError("WMI Get对象不可用。")
        method_func = getattr(self._wmi_get_obj, method_name)
        return method_func(**kwargs)

    def _execute_set_method(self, method_name: str, **kwargs) -> Any:
        """在GB_WMIACPI_Set对象上执行方法。"""
        if not self._wmi_set_obj: raise WMIConnectionError("WMI Set对象不可用。")
        method_func = getattr(self._wmi_set_obj, method_name)
        return method_func(**kwargs)

    def _parse_and_validate(self, raw_result: Any, validator: Callable) -> Any:
        """辅助函数，用于解析WMI元组结果并进行验证。"""
        value = raw_result[0] if isinstance(raw_result, tuple) and len(raw_result) > 0 else raw_result
        return validator(value)

    def _validate_temp(self, value: Any) -> float:
        try:
            temp = float(value)
            return temp if 0 < temp < 150 and not math.isnan(temp) else TEMP_READ_ERROR_VALUE
        except (ValueError, TypeError, IndexError): return TEMP_READ_ERROR_VALUE

    def _validate_rpm(self, value: Any) -> int:
        try:
            raw_int = int(value)
            if 0 <= raw_int <= 65535:
                low_byte = raw_int & 0xFF; high_byte = (raw_int >> 8) & 0xFF
                corrected_rpm = (low_byte << 8) | high_byte
                return corrected_rpm if corrected_rpm > 50 else 0
            return RPM_READ_ERROR_VALUE
        except (ValueError, TypeError): return RPM_READ_ERROR_VALUE

    def _validate_int(self, value: Any, default_error_val: int) -> int:
        try: return int(value)
        except (ValueError, TypeError): return default_error_val

    # --- 合并查询的内部实现 ---
    def _get_temperatures(self) -> Dict[str, float]:
        """仅获取温度。"""
        cpu_temp = self._parse_and_validate(self._execute_get_method(WMI_GET_CPU_TEMP), self._validate_temp)
        
        temps = []
        for method in [WMI_GET_GPU_TEMP1, WMI_GET_GPU_TEMP2]:
            try:
                temp = self._parse_and_validate(self._execute_get_method(method), self._validate_temp)
                if temp != TEMP_READ_ERROR_VALUE: temps.append(temp)
            except AttributeError: pass
        gpu_temp = max(temps) if temps else TEMP_READ_ERROR_VALUE
        
        return {'cpu_temp': cpu_temp, 'gpu_temp': gpu_temp}

    def _get_core_sensors(self) -> Dict[str, Any]:
        """获取温度和转速，用于后台轮询。"""
        data = self._get_temperatures()
        data['fan1_rpm'] = self._parse_and_validate(self._execute_get_method(WMI_GET_RPM1), self._validate_rpm)
        data['fan2_rpm'] = self._parse_and_validate(self._execute_get_method(WMI_GET_RPM2), self._validate_rpm)
        return data

    def _get_all_sensors(self) -> Dict[str, Any]:
        """获取所有传感器数据，包括不常变化的电池信息。"""
        data = self._get_core_sensors()
        data['charge_policy'] = self._parse_and_validate(self._execute_get_method(WMI_GET_CHARGE_POLICY), lambda v: self._validate_int(v, CHARGE_POLICY_READ_ERROR_VALUE))
        data['charge_threshold'] = self._parse_and_validate(self._execute_get_method(WMI_GET_CHARGE_STOP), lambda v: self._validate_int(v, CHARGE_THRESHOLD_READ_ERROR_VALUE))
        return data

# ==============================================================================
# WMIInterface (公共同步API)
# ==============================================================================
class WMIInterface:
    """
    【重构】提供一个极简的、线程安全的WMI操作公共API。
    """
    def __init__(self, get_class=DEFAULT_WMI_GET_CLASS, set_class=DEFAULT_WMI_SET_CLASS):
        self._request_queue = queue.Queue(maxsize=50)
        self._worker_thread: Optional[WMIWorker] = None
        self._lock = threading.Lock()
        self._is_running = False
        self._initialization_error: Optional[Exception] = None
        self._wmi_get_class = get_class
        self._wmi_set_class = set_class

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._is_running and self._worker_thread is not None and self._worker_thread.is_alive()

    def start(self) -> bool:
        """启动WMI工作线程并等待其初始化。"""
        with self._lock:
            if self._is_running: return self._initialization_error is None
            if not _wmi_available:
                self._initialization_error = WMIConnectionError("WMI库未找到。")
                return False

            self._initialization_error = None
            self._worker_thread = WMIWorker(self._request_queue, self._wmi_get_class, self._wmi_set_class)
            self._worker_thread.start()
            self._is_running = True

        self._worker_thread.initialization_complete.wait(timeout=15.0)

        with self._lock:
            if self._worker_thread.initialization_error:
                self._initialization_error = WMIConnectionError(f"WMI工作线程初始化失败: {self._worker_thread.initialization_error}")
                self._cleanup_worker_nolock()
                return False
            if not self._worker_thread.is_alive():
                self._initialization_error = WMIConnectionError("WMI工作线程未能启动或意外死亡。")
                self._cleanup_worker_nolock()
                return False
            return True

    def stop(self):
        """向WMI工作线程发送停止信号并等待其退出。"""
        thread_to_join: Optional[WMIWorker] = None
        with self._lock:
            if not self._is_running or not self._worker_thread: return
            thread_to_join = self._worker_thread
            self._is_running = False
            self._worker_thread.stop() # 发送停止事件
            try:
                self._request_queue.put_nowait(WMI_WORKER_STOP_SIGNAL) # 唤醒工作线程以检查停止事件
            except queue.Full: pass

        if thread_to_join:
            thread_to_join.join(timeout=WMI_REQUEST_TIMEOUT_S + 2.0)
        
        with self._lock:
            self._worker_thread = None

    def _cleanup_worker_nolock(self):
        self._is_running = False
        thread = self._worker_thread
        if thread and thread.is_alive():
            thread.stop()
            try: self._request_queue.put_nowait(WMI_WORKER_STOP_SIGNAL)
            except queue.Full: pass
            thread.join(timeout=1.0)
        self._worker_thread = None

    def get_initialization_error(self) -> Optional[Exception]:
        with self._lock: return self._initialization_error

    def _execute_sync(self, method_name: str, params: Optional[Dict] = None, timeout: float = WMI_REQUEST_TIMEOUT_S) -> Any:
        """
        【重构】通用的同步执行器，向工作线程发送请求并等待响应。
        """
        if not self.is_running:
            raise self._initialization_error or WMIConnectionError("WMI接口未运行。")

        result_queue = queue.Queue(maxsize=1)
        request: WMIRequest = (method_name, params or {}, result_queue)

        try:
            self._request_queue.put(request, block=True, timeout=1.0)
        except queue.Full:
            raise WMIRequestTimeoutError(f"WMI请求队列已满。方法 '{method_name}' 被丢弃。")

        try:
            result_data, exception_obj = result_queue.get(block=True, timeout=timeout)
            if exception_obj:
                raise WMICommandError(f"WMI方法 '{method_name}' 失败。", original_exception=exception_obj)
            return result_data
        except queue.Empty:
            raise WMIRequestTimeoutError(f"WMI请求 '{method_name}' 在 {timeout}s 后超时。")
        except WMIError as e: raise e
        except Exception as e: raise WMIError(f"等待WMI对 '{method_name}' 的响应时发生意外错误: {e}")

    # --- 公共API方法 ---

    def execute_method(self, method_name: str, **kwargs) -> Any:
        """
        【新增】通用的、阻塞式的WMI方法执行器，主要用于Setters。
        """
        # 确保传递给WMI的数值是浮点数，以提高兼容性
        if 'Data' in kwargs and isinstance(kwargs['Data'], (int, float)):
             kwargs['Data'] = float(kwargs['Data'])
        return self._execute_sync(method_name, kwargs)

    def get_latest_core_sensor_data(self) -> Dict[str, Any]:
        """
        【新增】非阻塞地从缓存获取最新的核心传感器数据（温度、转速）。
        专为高频UI更新设计，对UI线程零影响。
        """
        if not self.is_running or not self._worker_thread: return {}
        return self._worker_thread.get_latest_core_sensor_data()

    def get_all_sensors_sync(self) -> Dict[str, Any]:
        """
        【新增】阻塞式地获取所有传感器数据（包括电池）。
        用于启动、窗口激活、设置更改等需要即时反馈的场景。
        """
        try:
            return self._execute_sync("_get_all_sensors")
        except WMIError:
            return {
                'cpu_temp': TEMP_READ_ERROR_VALUE, 'gpu_temp': TEMP_READ_ERROR_VALUE,
                'fan1_rpm': RPM_READ_ERROR_VALUE, 'fan2_rpm': RPM_READ_ERROR_VALUE,
                'charge_policy': CHARGE_POLICY_READ_ERROR_VALUE,
                'charge_threshold': CHARGE_THRESHOLD_READ_ERROR_VALUE
            }

    def get_temperatures_sync(self) -> Dict[str, float]:
        """
        【新增】阻塞式地仅获取CPU和GPU温度。
        专为后台自动温控逻辑设计，以最小化WMI开销。
        """
        try:
            return self._execute_sync("_get_temperatures")
        except WMIError:
            return {'cpu_temp': TEMP_READ_ERROR_VALUE, 'gpu_temp': TEMP_READ_ERROR_VALUE}