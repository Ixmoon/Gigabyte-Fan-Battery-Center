# -*- coding: utf-8 -*-
"""
提供一个极其轻薄、扁平化的WMI交互接口。
该模块负责：
1. 管理一个后台工作线程，该线程根据外部指令处理所有WMI调用。
2. 提供一个通用的、阻塞式的 `execute_method` 来执行所有WMI写入操作。
3. 提供三个高度优化的只读方法，分别用于UI更新、自动温控和全局刷新。
4. 管理一个独立的QTimer，用于动态地、高效地触发后台核心传感器轮询。
"""

import threading
import queue
import time
import math
import sys
from typing import Optional, Any, Dict, Tuple, Callable

from gui.qt import QObject, QTimer, Slot

_wmi_available = False
try:
    import wmi
    import pythoncom
    _wmi_available = True
except ImportError:
    print("警告: 未找到 'wmi' 或 'pythoncom' 包。WMI功能将被禁用。", file=sys.stderr)
    wmi = None
    pythoncom = None

from config.settings import (
    WMI_NAMESPACE, DEFAULT_WMI_GET_CLASS, DEFAULT_WMI_SET_CLASS,
    GET_CPU_TEMP, GET_GPU_TEMP1, GET_GPU_TEMP2,
    GET_RPM1, GET_RPM2, GET_CHARGE_POLICY, GET_CHARGE_STOP,
    WMI_REQUEST_TIMEOUT_S, TEMP_READ_ERROR_VALUE, RPM_READ_ERROR_VALUE,
    CHARGE_POLICY_READ_ERROR_VALUE, CHARGE_THRESHOLD_READ_ERROR_VALUE,
    WMIInternalSignal
)

WMIResult = Tuple[Optional[Any], Optional[Exception]]
WMIRequest = Tuple[Any, Dict[str, Any], Optional[queue.Queue]]

class WMIError(Exception): pass
class WMIConnectionError(WMIError): pass
class WMIRequestTimeoutError(WMIError): pass
class WMICommandError(WMIError):
    def __init__(self, message, original_exception=None):
        super().__init__(message)
        self.original_exception = original_exception

class WMIWorker(threading.Thread):
    """后台线程，处理所有阻塞的WMI调用。"""
    def __init__(self, request_queue: queue.Queue, wmi_get_class: str, wmi_set_class: str):
        super().__init__(name="WMIWorkerThread", daemon=True)
        self._request_queue = request_queue
        self._wmi_get_class_name = wmi_get_class
        self._wmi_set_class_name = wmi_set_class
        self._wmi_get_obj: Optional[Any] = None
        self._wmi_set_obj: Optional[Any] = None
        self._com_initialized: bool = False
        self.initialization_error: Optional[Exception] = None
        self.initialization_complete = threading.Event()
        self._latest_core_sensor_data: Dict[str, Any] = {}
        self._data_lock = threading.Lock()

    def _init_wmi(self) -> bool:
        if not _wmi_available or not pythoncom or not wmi:
            self.initialization_error = WMIConnectionError("WMI或pythoncom库未找到。")
            return False
        try:
            pythoncom.CoInitializeEx(pythoncom.COINIT_MULTITHREADED)
            self._com_initialized = True
            wmi_conn = wmi.WMI(namespace=WMI_NAMESPACE)
            self._wmi_get_obj = self._get_wmi_instance(wmi_conn, self._wmi_get_class_name)
            self._wmi_set_obj = self._get_wmi_instance(wmi_conn, self._wmi_set_class_name)
            if not self._wmi_get_obj or not self._wmi_set_obj:
                raise WMIConnectionError("未能获取WMI对象。请确保技嘉驱动已安装。")
            return True
        except Exception as e:
            self.initialization_error = e
            self._cleanup_com()
            return False

    def _get_wmi_instance(self, conn: Any, class_name: str) -> Optional[Any]:
        try:
            instances = conn.query(f"SELECT * FROM {class_name}")
            return instances[0] if instances else None
        except Exception: return None

    def _cleanup_com(self):
        if self._com_initialized and pythoncom:
            try: pythoncom.CoUninitialize()
            except Exception: pass
            self._com_initialized = False

    def run(self):
        """WMI工作线程的主循环，仅处理请求队列。"""
        if not self._init_wmi():
            self.initialization_complete.set()
            return
        self.initialization_complete.set()

        while True:
            request = self._request_queue.get()
            if request[0] is WMIInternalSignal.STOP:
                break
            self._process_request(request)
        
        self._cleanup_com()

    def get_latest_core_sensor_data(self) -> Dict[str, Any]:
        with self._data_lock:
            return self._latest_core_sensor_data.copy()

    def _process_request(self, request: WMIRequest):
        """处理单个请求，智能选择WMI对象并调用核心执行器。"""
        method_or_signal, params, callback_queue = request
        result, exception = None, None
        try:
            if method_or_signal is WMIInternalSignal.POLL_CORE_SENSORS:
                result = self._get_core_sensors()
                with self._data_lock: self._latest_core_sensor_data = result
            elif method_or_signal == "_get_all_sensors":
                result = self._get_all_sensors()
            elif method_or_signal == "_get_temperatures":
                result = self._get_temperatures()
            elif isinstance(method_or_signal, str):
                method_name = method_or_signal
                target_obj = self._wmi_set_obj if method_name.startswith("Set") else self._wmi_get_obj
                result = self._execute_wmi_method(target_obj, method_name, **params)
            else:
                exception = ValueError("无效的WMI请求类型")
        except Exception as e:
            exception = e
        
        if callback_queue:
            try: callback_queue.put((result, exception), block=False)
            except queue.Full: print("警告: WMI响应队列已满。", file=sys.stderr)

    def _execute_wmi_method(self, wmi_obj: Any, method_name: str, **kwargs) -> Any:
        """执行任何WMI方法的唯一入口。"""
        if not wmi_obj: raise WMIConnectionError("WMI对象不可用。")
        method_func = getattr(wmi_obj, method_name)
        raw_result = method_func(**kwargs)
        # 内联结果解析
        return raw_result[0] if isinstance(raw_result, tuple) and len(raw_result) > 0 else raw_result

    def _validate_temp(self, value: Any) -> float:
        try:
            temp = float(value)
            return temp if 0 < temp < 150 and not math.isnan(temp) else TEMP_READ_ERROR_VALUE
        except (ValueError, TypeError): return TEMP_READ_ERROR_VALUE

    def _validate_rpm(self, value: Any) -> int:
        try:
            raw_int = int(value)
            if 0 <= raw_int <= 65535:
                low_byte, high_byte = raw_int & 0xFF, (raw_int >> 8) & 0xFF
                corrected = (low_byte << 8) | high_byte
                return corrected if corrected > 50 else 0
            return RPM_READ_ERROR_VALUE
        except (ValueError, TypeError): return RPM_READ_ERROR_VALUE

    def _get_temperatures(self) -> Dict[str, float]:
        cpu_temp = self._validate_temp(self._execute_wmi_method(self._wmi_get_obj, GET_CPU_TEMP))
        temps = [self._validate_temp(self._execute_wmi_method(self._wmi_get_obj, m)) for m in [GET_GPU_TEMP1, GET_GPU_TEMP2] if hasattr(self._wmi_get_obj, m)]
        gpu_temp = max([t for t in temps if t != TEMP_READ_ERROR_VALUE], default=TEMP_READ_ERROR_VALUE)
        return {'cpu_temp': cpu_temp, 'gpu_temp': gpu_temp}

    def _get_core_sensors(self) -> Dict[str, Any]:
        data = self._get_temperatures()
        data['fan1_rpm'] = self._validate_rpm(self._execute_wmi_method(self._wmi_get_obj, GET_RPM1))
        data['fan2_rpm'] = self._validate_rpm(self._execute_wmi_method(self._wmi_get_obj, GET_RPM2))
        return data

    def _get_all_sensors(self) -> Dict[str, Any]:
        data = self._get_core_sensors()
        data['charge_policy'] = int(self._execute_wmi_method(self._wmi_get_obj, GET_CHARGE_POLICY))
        data['charge_threshold'] = int(self._execute_wmi_method(self._wmi_get_obj, GET_CHARGE_STOP))
        return data

class WMIInterface(QObject):
    """提供一个极简的、线程安全的WMI操作公共API。"""
    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._request_queue = queue.Queue(maxsize=50)
        self._worker_thread: Optional[WMIWorker] = None
        self._is_running = False
        self._initialization_error: Optional[Exception] = None
        # 使用QTimer进行动态轮询
        self._polling_timer = QTimer(self)
        self._polling_timer.timeout.connect(self._request_core_sensor_poll)

    @property
    def is_running(self) -> bool:
        return self._is_running and self._worker_thread is not None and self._worker_thread.is_alive()

    def start(self) -> bool:
        if self.is_running: return self._initialization_error is None
        if not _wmi_available:
            self._initialization_error = WMIConnectionError("WMI库未找到。")
            return False

        self._initialization_error = None
        self._worker_thread = WMIWorker(self._request_queue, DEFAULT_WMI_GET_CLASS, DEFAULT_WMI_SET_CLASS)
        self._worker_thread.start()
        
        self._worker_thread.initialization_complete.wait(timeout=15.0)
        if self._worker_thread.initialization_error or not self._worker_thread.is_alive():
            self._initialization_error = self._worker_thread.initialization_error or WMIConnectionError("WMI工作线程未能启动。")
            self._worker_thread = None
            return False
        
        self._is_running = True
        self._polling_timer.start(1000) # 启动时使用默认间隔
        return True

    def stop(self):
        if not self.is_running or not self._worker_thread: return
        self._is_running = False
        self._polling_timer.stop()
        self._request_queue.put((WMIInternalSignal.STOP, {}, None))
        self._worker_thread.join(timeout=WMI_REQUEST_TIMEOUT_S)
        self._worker_thread = None

    def get_initialization_error(self) -> Optional[Exception]:
        return self._initialization_error

    def _execute_sync(self, method_or_signal: Any, params: Optional[Dict] = None, timeout: float = WMI_REQUEST_TIMEOUT_S) -> Any:
        if not self.is_running: raise self._initialization_error or WMIConnectionError("WMI接口未运行。")
        result_queue = queue.Queue(maxsize=1)
        request: WMIRequest = (method_or_signal, params or {}, result_queue)
        try:
            self._request_queue.put(request, block=True, timeout=1.0)
        except queue.Full:
            raise WMIRequestTimeoutError(f"WMI请求队列已满。")
        try:
            result, exc = result_queue.get(block=True, timeout=timeout)
            if exc: raise WMICommandError(f"WMI方法 '{method_or_signal}' 失败。", original_exception=exc)
            return result
        except queue.Empty:
            raise WMIRequestTimeoutError(f"WMI请求 '{method_or_signal}' 超时。")

    # --- 公共API方法 ---
    def execute_method(self, method_name: str, **kwargs) -> Any:
        """通用的、阻塞式的WMI方法执行器，主要用于Setters。"""
        if 'Data' in kwargs and isinstance(kwargs['Data'], (int, float)):
             kwargs['Data'] = float(kwargs['Data'])
        return self._execute_sync(method_name, kwargs)

    def get_latest_core_sensor_data(self) -> Dict[str, Any]:
        """非阻塞地从缓存获取最新的核心传感器数据（温度、转速）。"""
        if not self.is_running or not self._worker_thread: return {}
        return self._worker_thread.get_latest_core_sensor_data()

    def get_all_sensors_sync(self) -> Dict[str, Any]:
        """阻塞式地获取所有传感器数据（包括电池）。"""
        return self._execute_sync("_get_all_sensors")

    def get_temperatures_sync(self) -> Dict[str, float]:
        """阻塞式地仅获取CPU和GPU温度。"""
        return self._execute_sync("_get_temperatures")

    def set_polling_interval(self, interval_ms: int):
        """动态设置后台轮询间隔。"""
        if self._polling_timer.interval() != interval_ms:
            self._polling_timer.setInterval(interval_ms)

    @Slot()
    def _request_core_sensor_poll(self):
        """由QTimer触发，向后台线程发送一个非阻塞的轮询请求。"""
        if self.is_running:
            self._request_queue.put((WMIInternalSignal.POLL_CORE_SENSORS, {}, None))