# -*- coding: utf-8 -*-
"""
提供一个健壮、线程安全的WMI交互接口，用于控制技嘉特定的风扇和电池设置。
管理一个后台工作线程处理所有阻塞的WMI调用，确保主应用保持响应。
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
    WMI_SET_CUSTOM_FAN_STATUS, WMI_SET_SUPER_QUIET, WMI_SET_AUTO_FAN_STATUS,
    WMI_SET_STEP_FAN_STATUS, WMI_SET_CUSTOM_FAN_SPEED, WMI_SET_GPU_FAN_DUTY,
    WMI_SET_CHARGE_POLICY, WMI_SET_CHARGE_STOP,
    WMI_WORKER_STOP_SIGNAL, WMI_REQUEST_TIMEOUT_S,
    TEMP_READ_ERROR_VALUE, RPM_READ_ERROR_VALUE,
    CHARGE_POLICY_READ_ERROR_VALUE, CHARGE_THRESHOLD_READ_ERROR_VALUE,
    MIN_CHARGE_PERCENT, MAX_CHARGE_PERCENT,
    WMI_ACTION_GET_CPU_TEMP, WMI_ACTION_GET_GPU_TEMP, WMI_ACTION_GET_RPM,
    WMI_ACTION_GET_CHARGE_POLICY, WMI_ACTION_GET_CHARGE_STOP, WMI_ACTION_GET_ALL_SENSORS,
    WMI_ACTION_GET_NON_TEMP_SENSORS, WMI_ACTION_CONFIGURE_CUSTOM_FAN, WMI_ACTION_CONFIGURE_BIOS_FAN,
    WMI_ACTION_SET_FAN_SPEED_RAW, WMI_ACTION_SET_CHARGE_POLICY, WMI_ACTION_SET_CHARGE_STOP
)

# 类型提示
WMIResult = Tuple[Optional[Any], Optional[Exception]]
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
    后台线程，处理所有阻塞的WMI调用，确保主应用线程永不冻结。
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

        # --- 动作分派表，用于更清晰的请求处理 ---
        self._action_handlers: Dict[str, Callable] = {
            WMI_ACTION_GET_CPU_TEMP: self._handle_get_cpu_temp,
            WMI_ACTION_GET_GPU_TEMP: self._handle_get_gpu_temp,
            WMI_ACTION_GET_RPM: self._handle_get_rpm,
            WMI_ACTION_GET_CHARGE_POLICY: self._handle_get_charge_policy,
            WMI_ACTION_GET_CHARGE_STOP: self._handle_get_charge_stop,
            WMI_ACTION_GET_ALL_SENSORS: self._handle_get_all_sensors,
            WMI_ACTION_GET_NON_TEMP_SENSORS: self._handle_get_non_temp_sensors,
            WMI_ACTION_CONFIGURE_CUSTOM_FAN: self._handle_configure_custom_fan,
            WMI_ACTION_CONFIGURE_BIOS_FAN: self._handle_configure_bios_fan,
            WMI_ACTION_SET_FAN_SPEED_RAW: self._handle_set_fan_speed_raw,
            WMI_ACTION_SET_CHARGE_POLICY: self._handle_set_charge_policy,
            WMI_ACTION_SET_CHARGE_STOP: self._handle_set_charge_stop,
        }

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
        """WMI工作线程的主循环。"""
        try:
            if not self._init_wmi():
                self.initialization_complete.set() # 发出失败信号以解除主线程阻塞
                return

            self.initialization_complete.set() # 在进入循环前发出成功信号

            while True:
                request = self._request_queue.get()
                if request == WMI_WORKER_STOP_SIGNAL:
                    break
                if isinstance(request, tuple) and len(request) == 3:
                    self._process_request(request)
                else:
                    print(f"WMI Worker: 收到无效的请求格式: {request}", file=sys.stderr)
        except Exception as e:
            print(f"WMI Worker: 主循环中未处理的异常: {e}", file=sys.stderr)
        finally:
            self._wmi_get_obj = self._wmi_set_obj = self._wmi_conn = None
            self._cleanup_com()

    def _process_request(self, request: WMIRequest):
        """使用分派表处理单个请求。"""
        action, params, callback_queue = request
        result, exception = None, None
        try:
            handler = self._action_handlers.get(action)
            if handler:
                result = handler(params)
            else:
                exception = ValueError(f"请求了未知的WMI动作: {action}")
        except Exception as e:
            exception = e
        self._send_response(callback_queue, result, exception)

    def _send_response(self, callback_queue: queue.Queue, result: Any, exception: Optional[Exception]):
        """将结果或异常放入回调队列。"""
        try:
            callback_queue.put((result, exception), block=False)
        except queue.Full:
            print("警告: WMI响应队列意外已满。正在丢弃响应。", file=sys.stderr)

    # --- WMI方法执行和值解析 ---
    def _execute_wmi_method(self, obj: Any, method_name: str, **kwargs) -> Any:
        """在WMI对象实例上执行方法，引发详细错误。"""
        if not obj:
            raise WMIConnectionError("WMI对象不可用，无法执行方法。")
        if not hasattr(obj, method_name):
            raise AttributeError(f"WMI对象没有方法 '{method_name}'")
        
        # 确保传递给WMI的数值是浮点数，以提高兼容性
        if 'Data' in kwargs and isinstance(kwargs['Data'], (int, float)):
             kwargs['Data'] = float(kwargs['Data'])
             
        method_func = getattr(obj, method_name)
        return method_func(**kwargs)

    def _parse_wmi_result(self, result: Any) -> Optional[Any]:
        """从典型的WMI方法结果元组中提取主值。"""
        if isinstance(result, tuple) and len(result) > 0:
            return result[0]
        return result

    def _validate_temp(self, value: Any) -> float:
        """验证并清理温度读数。"""
        try:
            temp = float(value)
            return temp if 0 < temp < 150 and not math.isnan(temp) else TEMP_READ_ERROR_VALUE
        except (ValueError, TypeError, IndexError):
            return TEMP_READ_ERROR_VALUE

    def _validate_rpm(self, value: Any) -> int:
        """验证并清理RPM读数，包括字节交换。"""
        try:
            raw_int = int(value)
            if 0 <= raw_int <= 65535:
                low_byte = raw_int & 0xFF
                high_byte = (raw_int >> 8) & 0xFF
                corrected_rpm = (low_byte << 8) | high_byte
                return corrected_rpm if corrected_rpm > 50 else 0
            return RPM_READ_ERROR_VALUE
        except (ValueError, TypeError):
            return RPM_READ_ERROR_VALUE

    def _validate_int(self, value: Any, default_error_val: int) -> int:
        """验证并清理通用整数读数。"""
        try:
            return int(value)
        except (ValueError, TypeError):
            return default_error_val

    # --- 动作处理器 (从分派表调用) ---
    def _handle_get_cpu_temp(self, params: Dict) -> float:
        raw_res = self._execute_wmi_method(self._wmi_get_obj, WMI_GET_CPU_TEMP)
        return self._validate_temp(self._parse_wmi_result(raw_res))

    def _handle_get_gpu_temp(self, params: Dict) -> float:
        temps = []
        for method in [WMI_GET_GPU_TEMP1, WMI_GET_GPU_TEMP2]:
            try:
                raw_res = self._execute_wmi_method(self._wmi_get_obj, method)
                temp = self._validate_temp(self._parse_wmi_result(raw_res))
                if temp != TEMP_READ_ERROR_VALUE:
                    temps.append(temp)
            except AttributeError: # 如果方法不存在则忽略
                pass
        return max(temps) if temps else TEMP_READ_ERROR_VALUE

    def _handle_get_rpm(self, params: Dict) -> int:
        method_name = params["method_name"]
        raw_res = self._execute_wmi_method(self._wmi_get_obj, method_name)
        return self._validate_rpm(self._parse_wmi_result(raw_res))

    def _handle_get_charge_policy(self, params: Dict) -> int:
        raw_res = self._execute_wmi_method(self._wmi_get_obj, WMI_GET_CHARGE_POLICY)
        return self._validate_int(self._parse_wmi_result(raw_res), CHARGE_POLICY_READ_ERROR_VALUE)

    def _handle_get_charge_stop(self, params: Dict) -> int:
        raw_res = self._execute_wmi_method(self._wmi_get_obj, WMI_GET_CHARGE_STOP)
        return self._validate_int(self._parse_wmi_result(raw_res), CHARGE_THRESHOLD_READ_ERROR_VALUE)

    def _handle_get_all_sensors(self, params: Dict) -> Dict[str, Any]:
        """在单个操作中处理组合的传感器读取动作。"""
        return {
            'cpu_temp': self._handle_get_cpu_temp({}),
            'gpu_temp': self._handle_get_gpu_temp({}),
            'fan1_rpm': self._handle_get_rpm({"method_name": WMI_GET_RPM1}),
            'fan2_rpm': self._handle_get_rpm({"method_name": WMI_GET_RPM2}),
            'charge_policy': self._handle_get_charge_policy({}),
            'charge_threshold': self._handle_get_charge_stop({})
        }

    def _handle_get_non_temp_sensors(self, params: Dict) -> Dict[str, Any]:
        """处理除温度外的传感器读取。"""
        return {
            'fan1_rpm': self._handle_get_rpm({"method_name": WMI_GET_RPM1}),
            'fan2_rpm': self._handle_get_rpm({"method_name": WMI_GET_RPM2}),
            'charge_policy': self._handle_get_charge_policy({}),
            'charge_threshold': self._handle_get_charge_stop({})
        }

    def _handle_configure_custom_fan(self, params: Dict) -> bool:
        self._execute_wmi_method(self._wmi_set_obj, WMI_SET_CUSTOM_FAN_STATUS, Data=1.0)
        self._execute_wmi_method(self._wmi_set_obj, WMI_SET_SUPER_QUIET, Data=0.0)
        self._execute_wmi_method(self._wmi_set_obj, WMI_SET_AUTO_FAN_STATUS, Data=0.0)
        self._execute_wmi_method(self._wmi_set_obj, WMI_SET_STEP_FAN_STATUS, Data=0.0)
        return True

    def _handle_configure_bios_fan(self, params: Dict) -> bool:
        self._execute_wmi_method(self._wmi_set_obj, WMI_SET_AUTO_FAN_STATUS, Data=1.0)
        self._execute_wmi_method(self._wmi_set_obj, WMI_SET_CUSTOM_FAN_STATUS, Data=0.0)
        return True

    def _handle_set_fan_speed_raw(self, params: Dict) -> bool:
        speed_value = params["speed_value"]
        self._execute_wmi_method(self._wmi_set_obj, WMI_SET_CUSTOM_FAN_SPEED, Data=speed_value)
        self._execute_wmi_method(self._wmi_set_obj, WMI_SET_GPU_FAN_DUTY, Data=speed_value)
        return True

    def _handle_set_charge_policy(self, params: Dict) -> bool:
        policy_value = params["policy_value"]
        self._execute_wmi_method(self._wmi_set_obj, WMI_SET_CHARGE_POLICY, Data=policy_value)
        return True

    def _handle_set_charge_stop(self, params: Dict) -> bool:
        threshold_value = params["threshold_value"]
        self._execute_wmi_method(self._wmi_set_obj, WMI_SET_CHARGE_STOP, Data=threshold_value)
        return True

# ==============================================================================
# WMIInterface (公共同步API)
# ==============================================================================
class WMIInterface:
    """
    提供同步、线程安全的WMI操作公共API，隐藏后台工作线程的复杂性。
    """
    def __init__(self, get_class=DEFAULT_WMI_GET_CLASS, set_class=DEFAULT_WMI_SET_CLASS):
        self._wmi_get_class = get_class
        self._wmi_set_class = set_class
        self._request_queue = queue.Queue(maxsize=50)
        self._worker_thread: Optional[WMIWorker] = None
        self._lock = threading.Lock()
        self._is_running = False
        self._initialization_error: Optional[Exception] = None

    @property
    def is_running(self) -> bool:
        """安全地检查工作线程是否被认为是正在运行。"""
        with self._lock:
            return self._is_running and self._worker_thread is not None and self._worker_thread.is_alive()

    def start(self) -> bool:
        """启动WMI工作线程并等待其初始化。"""
        with self._lock:
            if self._is_running:
                return self._initialization_error is None
            if not _wmi_available:
                self._initialization_error = WMIConnectionError("WMI库未找到。")
                return False

            self._initialization_error = None
            self._worker_thread = WMIWorker(self._request_queue, self._wmi_get_class, self._wmi_set_class)
            self._worker_thread.start()
            self._is_running = True

        # 等待工作线程完成其初始化尝试。
        self._worker_thread.initialization_complete.wait(timeout=15.0)

        with self._lock:
            # 等待后检查初始化错误。
            if self._worker_thread.initialization_error:
                self._initialization_error = WMIConnectionError(
                    f"WMI工作线程初始化失败: {self._worker_thread.initialization_error}"
                )
                self._cleanup_worker_nolock()
                return False
            # 检查超时或线程死亡。
            if not self._worker_thread.is_alive():
                self._initialization_error = WMIConnectionError("WMI工作线程未能启动或意外死亡。")
                self._cleanup_worker_nolock()
                return False
            return True

    def stop(self):
        """向WMI工作线程发送停止信号并等待其退出。"""
        thread_to_join: Optional[WMIWorker] = None
        with self._lock:
            if not self._is_running or not self._worker_thread:
                return
            thread_to_join = self._worker_thread
            self._is_running = False
            try:
                self._request_queue.put_nowait(WMI_WORKER_STOP_SIGNAL)
            except queue.Full:
                print("警告: WMI请求队列已满，无法发送停止信号。", file=sys.stderr)

        if thread_to_join:
            thread_to_join.join(timeout=WMI_REQUEST_TIMEOUT_S + 2.0)
            if thread_to_join.is_alive():
                print("警告: WMI工作线程未能优雅地停止。", file=sys.stderr)
        
        with self._lock:
            self._worker_thread = None

    def _cleanup_worker_nolock(self):
        """内部清理辅助函数。假定锁已被持有。"""
        self._is_running = False
        thread = self._worker_thread
        if thread and thread.is_alive():
            try:
                self._request_queue.put_nowait(WMI_WORKER_STOP_SIGNAL)
            except queue.Full:
                pass
            thread.join(timeout=1.0)
        self._worker_thread = None

    def get_initialization_error(self) -> Optional[Exception]:
        """返回初始化期间遇到的错误（如果有）。"""
        with self._lock:
            return self._initialization_error

    def _execute_sync(self, action: str, params: Optional[Dict] = None, timeout: float = WMI_REQUEST_TIMEOUT_S) -> Any:
        """
        向工作线程发送请求并同步等待响应。
        失败时引发WMIError异常。
        """
        if not self.is_running:
            raise self._initialization_error or WMIConnectionError("WMI接口未运行。")

        result_queue = queue.Queue(maxsize=1)
        request: WMIRequest = (action, params or {}, result_queue)

        try:
            self._request_queue.put(request, block=True, timeout=1.0)
        except queue.Full:
            raise WMIRequestTimeoutError(f"WMI请求队列已满。动作 '{action}' 被丢弃。")

        try:
            result_data, exception_obj = result_queue.get(block=True, timeout=timeout)
            if exception_obj:
                raise WMICommandError(f"WMI动作 '{action}' 失败。", original_exception=exception_obj)
            return result_data
        except queue.Empty:
            raise WMIRequestTimeoutError(f"WMI请求 '{action}' 在 {timeout}s 后超时。")
        except WMIError as e:
            raise e # 重新引发我们的特定错误
        except Exception as e:
            raise WMIError(f"等待WMI对 '{action}' 的响应时发生意外错误: {e}")

    # --- 公共API方法 ---
    def get_cpu_temperature(self) -> float:
        """获取当前CPU温度。"""
        try:
            return self._execute_sync(WMI_ACTION_GET_CPU_TEMP)
        except WMIError:
            return TEMP_READ_ERROR_VALUE

    def get_gpu_temperature(self) -> float:
        """获取当前GPU温度 (可用传感器的最大值)。"""
        try:
            return self._execute_sync(WMI_ACTION_GET_GPU_TEMP)
        except WMIError:
            return TEMP_READ_ERROR_VALUE

    def get_fan_rpm(self, fan_index: int) -> int:
        """获取指定风扇索引 (1或2) 的RPM。"""
        if fan_index not in [1, 2]: return RPM_READ_ERROR_VALUE
        method = WMI_GET_RPM1 if fan_index == 1 else WMI_GET_RPM2
        try:
            return self._execute_sync(WMI_ACTION_GET_RPM, {"method_name": method})
        except WMIError:
            return RPM_READ_ERROR_VALUE

    def get_battery_charge_policy(self) -> int:
        """获取当前电池充电策略代码。"""
        try:
            return self._execute_sync(WMI_ACTION_GET_CHARGE_POLICY)
        except WMIError:
            return CHARGE_POLICY_READ_ERROR_VALUE

    def get_battery_charge_threshold(self) -> int:
        """获取当前电池充电停止阈值百分比。"""
        try:
            return self._execute_sync(WMI_ACTION_GET_CHARGE_STOP)
        except WMIError:
            return CHARGE_THRESHOLD_READ_ERROR_VALUE

    def get_all_sensors(self) -> Dict[str, Any]:
        """在单个高效的WMI调用中获取所有传感器读数。"""
        try:
            return self._execute_sync(WMI_ACTION_GET_ALL_SENSORS)
        except WMIError:
            # 失败时，返回带有默认错误值的字典
            return {
                'cpu_temp': TEMP_READ_ERROR_VALUE,
                'gpu_temp': TEMP_READ_ERROR_VALUE,
                'fan1_rpm': RPM_READ_ERROR_VALUE,
                'fan2_rpm': RPM_READ_ERROR_VALUE,
                'charge_policy': CHARGE_POLICY_READ_ERROR_VALUE,
                'charge_threshold': CHARGE_THRESHOLD_READ_ERROR_VALUE
            }

    def get_non_temp_sensors(self) -> Dict[str, Any]:
        """在单个调用中获取所有非温度传感器读数。"""
        try:
            return self._execute_sync(WMI_ACTION_GET_NON_TEMP_SENSORS)
        except WMIError:
            return {
                'fan1_rpm': RPM_READ_ERROR_VALUE,
                'fan2_rpm': RPM_READ_ERROR_VALUE,
                'charge_policy': CHARGE_POLICY_READ_ERROR_VALUE,
                'charge_threshold': CHARGE_THRESHOLD_READ_ERROR_VALUE
            }

    def configure_custom_fan_control(self) -> bool:
        """设置必要的WMI标志以启用自定义（应用控制的）风扇速度。"""
        try:
            return self._execute_sync(WMI_ACTION_CONFIGURE_CUSTOM_FAN)
        except WMIError as e:
            print(f"WMI错误 (configure_custom_fan): {e}", file=sys.stderr)
            return False

    def configure_bios_fan_control(self) -> bool:
        """设置必要的WMI标志以将风扇控制权交还给BIOS/EC。"""
        try:
            return self._execute_sync(WMI_ACTION_CONFIGURE_BIOS_FAN)
        except WMIError as e:
            print(f"WMI错误 (configure_bios_fan): {e}", file=sys.stderr)
            return False

    def set_fan_speed_raw(self, raw_speed_value: float) -> bool:
        """为两个风扇设置原始速度值 (0-229)。"""
        raw_speed_value = max(0.0, min(229.0, float(raw_speed_value)))
        try:
            return self._execute_sync(WMI_ACTION_SET_FAN_SPEED_RAW, {"speed_value": raw_speed_value})
        except WMIError as e:
            print(f"WMI错误 (set_fan_speed_raw): {e}", file=sys.stderr)
            return False

    def set_battery_charge_policy(self, policy_code: int) -> bool:
        """使用原始代码设置电池充电策略 (例如, 0 或 4)。"""
        try:
            return self._execute_sync(WMI_ACTION_SET_CHARGE_POLICY, {"policy_value": float(policy_code)})
        except WMIError as e:
            print(f"WMI错误 (set_charge_policy): {e}", file=sys.stderr)
            return False

    def set_battery_charge_threshold(self, threshold_percent: int) -> bool:
        """设置电池充电停止阈值百分比。"""
        threshold_percent = max(MIN_CHARGE_PERCENT, min(MAX_CHARGE_PERCENT, int(threshold_percent)))
        try:
            return self._execute_sync(WMI_ACTION_SET_CHARGE_STOP, {"threshold_value": float(threshold_percent)})
        except WMIError as e:
            print(f"WMI错误 (set_charge_stop): {e}", file=sys.stderr)
            return False