# core/wmi_interface.py
# -*- coding: utf-8 -*-
"""
Provides an interface for interacting with WMI to control Gigabyte-specific
fan and battery settings. Manages a background worker thread for WMI calls.
"""

import threading
import queue
import time
import math
import sys
from typing import Optional, Any, Dict, Tuple

# Import WMI libraries if available
_wmi_available = False
_pythoncom_available = False
try:
    import wmi
    _wmi_available = True
    import pythoncom
    _pythoncom_available = True
except ImportError:
    print("Warning: 'wmi' or 'pythoncom' package not found. WMI functionality will be disabled.", file=sys.stderr)
    wmi = None # Define as None to allow type hinting
    pythoncom = None

# Import settings for WMI configuration and error values
from config.settings import (
    WMI_NAMESPACE, DEFAULT_WMI_GET_CLASS, DEFAULT_WMI_SET_CLASS,
    WMI_GET_CPU_TEMP, WMI_GET_GPU_TEMP1, WMI_GET_GPU_TEMP2,
    WMI_GET_RPM1, WMI_GET_RPM2, WMI_GET_CHARGE_POLICY, WMI_GET_CHARGE_STOP,
    WMI_SET_FIXED_FAN_STATUS, WMI_SET_SUPER_QUIET, WMI_SET_AUTO_FAN_STATUS,
    WMI_SET_STEP_FAN_STATUS, WMI_SET_FIXED_FAN_SPEED, WMI_SET_GPU_FAN_DUTY,
    WMI_SET_CHARGE_POLICY, WMI_SET_CHARGE_STOP,
    WMI_WORKER_STOP_SIGNAL, WMI_REQUEST_TIMEOUT_S,
    TEMP_READ_ERROR_VALUE, RPM_READ_ERROR_VALUE,
    CHARGE_POLICY_READ_ERROR_VALUE, CHARGE_THRESHOLD_READ_ERROR_VALUE,
    CHARGE_POLICY_STANDARD, CHARGE_POLICY_CUSTOM, MIN_CHARGE_PERCENT, MAX_CHARGE_PERCENT
)

# Type Hinting
WMIResult = Tuple[Optional[Any], Optional[Exception]]
WMIRequest = Tuple[str, Dict[str, Any], queue.Queue] # action, params, callback_queue

class WMIWorker(threading.Thread):
    """Background thread to handle blocking WMI calls."""
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

    def _init_wmi(self) -> bool:
        """Initializes COM and connects to the WMI namespace."""
        if not _wmi_available or not _pythoncom_available:
            self.initialization_error = ImportError("WMI or pythoncom library not found.")
            return False
        try:
            pythoncom.CoInitializeEx(pythoncom.COINIT_MULTITHREADED)
            self._com_initialized = True

            self._wmi_conn = wmi.WMI(namespace=WMI_NAMESPACE)

            self._wmi_get_obj = self._get_wmi_instance(self._wmi_get_class_name)
            self._wmi_set_obj = self._get_wmi_instance(self._wmi_set_class_name)

            if not self._wmi_get_obj or not self._wmi_set_obj:
                missing = []
                if not self._wmi_get_obj: missing.append(self._wmi_get_class_name)
                if not self._wmi_set_obj: missing.append(self._wmi_set_class_name)
                error_msg = (f"Failed to get WMI objects ({', '.join(missing)}). "
                             "Ensure Gigabyte software/drivers are installed and running.")
                self.initialization_error = RuntimeError(error_msg)
                self._cleanup_com()
                return False

            return True
        except Exception as e:
            self.initialization_error = e
            self._cleanup_com()
            return False

    def _get_wmi_instance(self, class_name: str) -> Optional[Any]:
        """Safely gets the first instance of a WMI class."""
        if not self._wmi_conn: return None
        try:
            if hasattr(self._wmi_conn, class_name):
                instances = getattr(self._wmi_conn, class_name)()
                return instances[0] if instances else None
            instances = self._wmi_conn.query(f"SELECT * FROM {class_name}")
            return instances[0] if instances else None
        except AttributeError as ae:
             if f"'{class_name}'" in str(ae):
                 try:
                     instances = self._wmi_conn.query(f"SELECT * FROM {class_name}")
                     return instances[0] if instances else None
                 except Exception:
                     return None
             else:
                 return None
        except Exception:
            return None

    def _execute_wmi_method(self, obj: Any, method_name: str, is_setter: bool, **kwargs) -> Any:
        """Executes a method on a WMI object instance."""
        if not obj:
            raise RuntimeError(f"WMI {'Set' if is_setter else 'Get'} object is not available.")

        processed_kwargs = kwargs
        if is_setter and 'Data' in kwargs and isinstance(kwargs['Data'], (int, float)):
             processed_kwargs = {k: float(v) if k == "Data" else v for k, v in kwargs.items()}

        if not hasattr(obj, method_name):
            raise AttributeError(f"WMI object does not have method '{method_name}'")

        method_func = getattr(obj, method_name)
        return method_func(**processed_kwargs)

    def _send_response(self, callback_queue: queue.Queue, result: Any = None, exception: Optional[Exception] = None):
        """Puts the result or exception onto the callback queue."""
        try:
            response: WMIResult = (result, exception)
            callback_queue.put(response, block=False)
        except queue.Full:
            print("Warning: WMI response queue was unexpectedly full. Discarding response.", file=sys.stderr)
            pass

    def _handle_request(self, request: WMIRequest):
        """Handles a single WMI request from the queue."""
        action, params, callback_queue = request
        result: Any = None
        exception: Optional[Exception] = None

        try:
            if action == "get_cpu_temp":
                res = self._execute_wmi_method(self._wmi_get_obj, WMI_GET_CPU_TEMP, False)
                val_list = list(res) if isinstance(res, tuple) else [res]
                temp = TEMP_READ_ERROR_VALUE
                if val_list and val_list[0] is not None:
                    try:
                        temp_val = float(val_list[0])
                        if not math.isnan(temp_val) and 0 < temp_val < 150:
                            temp = temp_val
                    except (ValueError, TypeError, IndexError): pass
                result = temp

            elif action == "get_gpu_temp":
                temps = []
                for method in [WMI_GET_GPU_TEMP1, WMI_GET_GPU_TEMP2]:
                    try:
                        res = self._execute_wmi_method(self._wmi_get_obj, method, False)
                        val_list = list(res) if isinstance(res, tuple) else [res]
                        if val_list and val_list[0] is not None:
                            temp_val = float(val_list[0])
                            if not math.isnan(temp_val) and 0 < temp_val < 150:
                                temps.append(temp_val)
                    except (AttributeError, ValueError, TypeError, IndexError):
                        pass
                result = max(temps) if temps else TEMP_READ_ERROR_VALUE

            elif action == "get_rpm":
                method_name = params["method_name"]
                res = self._execute_wmi_method(self._wmi_get_obj, method_name, False)
                rpm = RPM_READ_ERROR_VALUE
                raw_value = None
                if isinstance(res, tuple) and len(res) > 0: raw_value = res[0]
                elif isinstance(res, (int, float)): raw_value = res

                if raw_value is not None:
                    try:
                        raw_int_value = int(raw_value)
                        if 0 <= raw_int_value <= 65535:
                            low_byte = raw_int_value & 0xFF
                            high_byte = (raw_int_value >> 8) & 0xFF
                            corrected_rpm = (low_byte << 8) | high_byte
                            rpm = corrected_rpm if corrected_rpm > 50 else 0
                    except (ValueError, TypeError): pass
                result = rpm

            elif action == "get_charge_policy":
                res = self._execute_wmi_method(self._wmi_get_obj, WMI_GET_CHARGE_POLICY, False)
                policy = CHARGE_POLICY_READ_ERROR_VALUE
                raw_value = None
                if isinstance(res, tuple) and len(res) > 0: raw_value = res[0]
                elif isinstance(res, (int, float)): raw_value = res
                if raw_value is not None:
                    try: policy = int(raw_value)
                    except (ValueError, TypeError): pass
                result = policy

            elif action == "get_charge_stop":
                res = self._execute_wmi_method(self._wmi_get_obj, WMI_GET_CHARGE_STOP, False)
                threshold = CHARGE_THRESHOLD_READ_ERROR_VALUE
                raw_value = None
                if isinstance(res, tuple) and len(res) > 0: raw_value = res[0]
                elif isinstance(res, (int, float)): raw_value = res
                if raw_value is not None:
                    try: threshold = int(raw_value)
                    except (ValueError, TypeError): pass
                result = threshold

            elif action == "configure_manual_fan":
                self._execute_wmi_method(self._wmi_set_obj, WMI_SET_FIXED_FAN_STATUS, True, Data=1.0)
                self._execute_wmi_method(self._wmi_set_obj, WMI_SET_SUPER_QUIET, True, Data=0.0)
                self._execute_wmi_method(self._wmi_set_obj, WMI_SET_AUTO_FAN_STATUS, True, Data=0.0)
                self._execute_wmi_method(self._wmi_set_obj, WMI_SET_STEP_FAN_STATUS, True, Data=0.0)
                result = True

            elif action == "set_fan_speed_raw":
                speed_value = params["speed_value"]
                self._execute_wmi_method(self._wmi_set_obj, WMI_SET_FIXED_FAN_SPEED, True, Data=speed_value)
                self._execute_wmi_method(self._wmi_set_obj, WMI_SET_GPU_FAN_DUTY, True, Data=speed_value)
                result = True

            elif action == "set_charge_policy":
                policy_value = params["policy_value"]
                self._execute_wmi_method(self._wmi_set_obj, WMI_SET_CHARGE_POLICY, True, Data=policy_value)
                result = True

            elif action == "set_charge_stop":
                threshold_value = params["threshold_value"]
                self._execute_wmi_method(self._wmi_set_obj, WMI_SET_CHARGE_STOP, True, Data=threshold_value)
                result = True

            else:
                exception = ValueError(f"Unknown WMI action requested: {action}")

        except Exception as e:
            exception = e

        self._send_response(callback_queue, result, exception)

    def _cleanup_com(self):
        """Uninitializes COM for this thread."""
        if self._com_initialized and _pythoncom_available:
            try:
                pythoncom.CoUninitialize()
                self._com_initialized = False
            except Exception as e:
                print(f"Error during COM uninitialization: {e}", file=sys.stderr)

    def run(self):
        """Main loop of the WMI worker thread."""
        try:
            if not self._init_wmi():
                self.initialization_complete.set()
                return

            self.initialization_complete.set()

            while True:
                try:
                    request = self._request_queue.get()

                    if request == WMI_WORKER_STOP_SIGNAL:
                        break

                    if isinstance(request, tuple) and len(request) == 3:
                        self._handle_request(request)
                    else:
                        print(f"WMI Worker: Received invalid request format: {request}", file=sys.stderr)

                except Exception as e:
                    print(f"WMI Worker: Unhandled exception in main loop: {e}", file=sys.stderr)
                    time.sleep(0.1)
        finally:
            self._wmi_get_obj = None
            self._wmi_set_obj = None
            self._wmi_conn = None
            self._cleanup_com()


class WMIInterface:
    """Provides a synchronous interface to WMI operations using a background worker."""

    def __init__(self, get_class=DEFAULT_WMI_GET_CLASS, set_class=DEFAULT_WMI_SET_CLASS):
        self._wmi_get_class = get_class
        self._wmi_set_class = set_class
        self._request_queue = queue.Queue(maxsize=50)
        self._worker_thread: Optional[WMIWorker] = None
        self._lock = threading.Lock()
        self._is_running = False
        self._initialization_error: Optional[Exception] = None

    def is_running(self) -> bool:
        """Safely check if the worker thread is considered running."""
        with self._lock:
            return self._is_running and self._worker_thread is not None and self._worker_thread.is_alive()

    def start(self) -> bool:
        """Starts the WMI worker thread and waits for initialization."""
        with self._lock:
            if self._is_running or not _wmi_available or not _pythoncom_available:
                return self._is_running and self._initialization_error is None

            self._initialization_error = None
            self._worker_thread = WMIWorker(self._request_queue, self._wmi_get_class, self._wmi_set_class)
            self._worker_thread.start()
            self._is_running = True

        initialized = self._worker_thread.initialization_complete.wait(timeout=15.0)

        with self._lock:
            if not initialized or not self._worker_thread or not self._worker_thread.is_alive():
                self._initialization_error = getattr(self._worker_thread, 'initialization_error', None) or \
                                             RuntimeError("WMI worker thread failed to start or timed out.")
                self._cleanup_worker_nolock()
                self._is_running = False
                return False
            elif self._worker_thread.initialization_error:
                 self._initialization_error = self._worker_thread.initialization_error
                 self._cleanup_worker_nolock()
                 self._is_running = False
                 return False
            else:
                return True

    def stop(self):
        """Signals the WMI worker thread to stop and waits for it to exit."""
        thread_to_join: Optional[WMIWorker] = None
        with self._lock:
            if not self._is_running or not self._worker_thread:
                return

            thread_to_join = self._worker_thread
            self._is_running = False

            try:
                self._request_queue.put_nowait(WMI_WORKER_STOP_SIGNAL)
            except queue.Full:
                print("Warning: WMI request queue full, could not send stop signal.", file=sys.stderr)
            except Exception as e:
                print(f"Error sending stop signal to WMI worker: {e}", file=sys.stderr)

        if thread_to_join:
            thread_to_join.join(timeout=WMI_REQUEST_TIMEOUT_S + 2.0)
            if thread_to_join.is_alive():
                print("Warning: WMI worker thread did not stop gracefully after join.", file=sys.stderr)

        with self._lock:
            self._worker_thread = None

    def _cleanup_worker_nolock(self):
        """Joins the worker thread if it exists. Assumes lock is already held."""
        thread_to_join = self._worker_thread
        if thread_to_join and thread_to_join.is_alive():
            thread_to_join.join(timeout=1.0)
            if thread_to_join.is_alive():
                 print("Warning: WMI worker thread did not stop during cleanup join.", file=sys.stderr)
        self._worker_thread = None

    def get_initialization_error(self) -> Optional[Exception]:
        """Returns the error encountered during initialization, if any."""
        with self._lock:
            return self._initialization_error

    def _execute_sync(self, action: str, params: Optional[Dict] = None, timeout: float = WMI_REQUEST_TIMEOUT_S) -> WMIResult:
        """
        Sends a request to the worker and waits for the response synchronously.
        """
        if not self.is_running():
             return (None, self._initialization_error or RuntimeError("WMI interface is not running."))

        if params is None:
            params = {}

        result_queue = queue.Queue(maxsize=1)
        request: WMIRequest = (action, params, result_queue)

        try:
            self._request_queue.put(request, block=True, timeout=1.0)
        except queue.Full:
             err = RuntimeError(f"WMI request queue is full. Action '{action}' dropped.")
             return (None, err)
        except Exception as e:
             return (None, RuntimeError(f"Failed to queue WMI request '{action}': {e}"))

        try:
            result_data, exception_obj = result_queue.get(block=True, timeout=timeout)
            return (result_data, exception_obj)
        except queue.Empty:
            err = TimeoutError(f"WMI request '{action}' timed out after {timeout}s.")
            return (None, err)
        except Exception as e:
            return (None, e)

    def get_cpu_temperature(self) -> float:
        """Gets the current CPU temperature."""
        result, exception = self._execute_sync("get_cpu_temp")
        if exception:
            return TEMP_READ_ERROR_VALUE
        return float(result) if isinstance(result, (float, int)) else TEMP_READ_ERROR_VALUE

    def get_gpu_temperature(self) -> float:
        """Gets the current GPU temperature (max of available sensors)."""
        result, exception = self._execute_sync("get_gpu_temp")
        if exception:
            return TEMP_READ_ERROR_VALUE
        return float(result) if isinstance(result, (float, int)) else TEMP_READ_ERROR_VALUE

    def get_fan_rpm(self, fan_index: int) -> int:
        """Gets the RPM for the specified fan index (1 or 2)."""
        if fan_index not in [1, 2]: return RPM_READ_ERROR_VALUE
        method = WMI_GET_RPM1 if fan_index == 1 else WMI_GET_RPM2
        result, exception = self._execute_sync("get_rpm", {"method_name": method})
        if exception:
            return RPM_READ_ERROR_VALUE
        return int(result) if isinstance(result, int) else RPM_READ_ERROR_VALUE

    def get_battery_charge_policy(self) -> int:
        """Gets the current battery charge policy code."""
        result, exception = self._execute_sync("get_charge_policy")
        if exception:
            return CHARGE_POLICY_READ_ERROR_VALUE
        return int(result) if isinstance(result, int) else CHARGE_POLICY_READ_ERROR_VALUE

    def get_battery_charge_threshold(self) -> int:
        """Gets the current battery charge stop threshold percentage."""
        result, exception = self._execute_sync("get_charge_stop")
        if exception:
            return CHARGE_THRESHOLD_READ_ERROR_VALUE
        return int(result) if isinstance(result, (int, float)) else CHARGE_THRESHOLD_READ_ERROR_VALUE

    def configure_manual_fan_control(self) -> bool:
        """Sets the necessary WMI flags to enable manual/fixed fan speed control."""
        result, exception = self._execute_sync("configure_manual_fan")
        if exception:
            print(f"WMI Error (configure_manual_fan): {exception}", file=sys.stderr)
            return False
        return bool(result)

    def set_fan_speed_raw(self, raw_speed_value: float) -> bool:
        """Sets the raw speed value (0-229) for both fans."""
        raw_speed_value = max(0.0, min(229.0, float(raw_speed_value)))
        result, exception = self._execute_sync("set_fan_speed_raw", {"speed_value": raw_speed_value})
        if exception:
            print(f"WMI Error (set_fan_speed_raw): {exception}", file=sys.stderr)
            return False
        return bool(result)

    def set_battery_charge_policy(self, policy_code: int) -> bool:
        """Sets the battery charge policy using the raw code (e.g., 0 or 4)."""
        result, exception = self._execute_sync("set_charge_policy", {"policy_value": float(policy_code)})
        if exception:
            print(f"WMI Error (set_charge_policy): {exception}", file=sys.stderr)
            return False
        return bool(result)

    def set_battery_charge_threshold(self, threshold_percent: int) -> bool:
        """Sets the battery charge stop threshold percentage."""
        threshold_percent = max(MIN_CHARGE_PERCENT, min(MAX_CHARGE_PERCENT, int(threshold_percent)))
        result, exception = self._execute_sync("set_charge_stop", {"threshold_value": float(threshold_percent)})
        if exception:
            print(f"WMI Error (set_charge_stop): {exception}", file=sys.stderr)
            return False
        return bool(result)