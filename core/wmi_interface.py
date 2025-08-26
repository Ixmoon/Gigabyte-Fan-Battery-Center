# core/wmi_interface.py
# -*- coding: utf-8 -*-
"""
Provides a robust, thread-safe interface for interacting with WMI to control
Gigabyte-specific fan and battery settings. Manages a background worker thread
for all blocking WMI calls to ensure the main application remains responsive.
"""

import threading
import queue
import time
import math
import sys
from typing import Optional, Any, Dict, Tuple, Callable, TYPE_CHECKING

# Import WMI libraries if available, providing a clear fallback path.
_wmi_available = False
_pythoncom_available = False
try:
    import wmi
    _wmi_available = True
    import pythoncom
    _pythoncom_available = True
except ImportError:
    print("Warning: 'wmi' or 'pythoncom' package not found. WMI functionality will be disabled.", file=sys.stderr)
    wmi = None
    pythoncom = None

# Import all necessary constants from the central settings file.
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
    # --- NEW: Import action constants ---
    WMI_ACTION_GET_CPU_TEMP, WMI_ACTION_GET_GPU_TEMP, WMI_ACTION_GET_RPM,
    WMI_ACTION_GET_CHARGE_POLICY, WMI_ACTION_GET_CHARGE_STOP, WMI_ACTION_GET_ALL_SENSORS,
    WMI_ACTION_GET_NON_TEMP_SENSORS, WMI_ACTION_CONFIGURE_CUSTOM_FAN, WMI_ACTION_CONFIGURE_BIOS_FAN,
    WMI_ACTION_SET_FAN_SPEED_RAW, WMI_ACTION_SET_CHARGE_POLICY, WMI_ACTION_SET_CHARGE_STOP
)

# --- Type Hinting ---
if TYPE_CHECKING and wmi:
    WMIConnectionType = wmi.WMI
else:
    WMIConnectionType = Any

WMIResult = Tuple[Optional[Any], Optional[Exception]]
WMIRequest = Tuple[str, Dict[str, Any], queue.Queue]

# --- Custom Exceptions for Clear Error Handling ---
class WMIError(Exception):
    """Base exception for WMI interface errors."""
    pass

class WMIConnectionError(WMIError):
    """Raised when the WMI connection or initialization fails."""
    pass

class WMIRequestTimeoutError(WMIError):
    """Raised when a WMI request times out."""
    pass

class WMICommandError(WMIError):
    """Raised when a WMI method call fails during execution."""
    def __init__(self, message, original_exception=None):
        super().__init__(message)
        self.original_exception = original_exception

# ==============================================================================
# WMIWorker Thread
# ==============================================================================
class WMIWorker(threading.Thread):
    """
    Background thread to handle all blocking WMI calls, ensuring the main
    application thread never freezes.
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

        # --- NEW: Action dispatch table for cleaner request handling ---
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

    # --- Initialization and Cleanup ---
    def _init_wmi(self) -> bool:
        """Initializes COM and connects to the WMI namespace."""
        if not _wmi_available or not _pythoncom_available:
            self.initialization_error = WMIConnectionError("WMI or pythoncom library not found.")
            return False
        try:
            if pythoncom:
                pythoncom.CoInitializeEx(pythoncom.COINIT_MULTITHREADED)
                self._com_initialized = True

            if wmi:
                self._wmi_conn = wmi.WMI(namespace=WMI_NAMESPACE)
                self._wmi_get_obj = self._get_wmi_instance(self._wmi_get_class_name)
                self._wmi_set_obj = self._get_wmi_instance(self._wmi_set_class_name)

            if not self._wmi_get_obj or not self._wmi_set_obj:
                missing = [name for name, obj in [(self._wmi_get_class_name, self._wmi_get_obj),
                                                  (self._wmi_set_class_name, self._wmi_set_obj)] if not obj]
                error_msg = (f"Failed to get WMI objects ({', '.join(missing)}). "
                             "Ensure Gigabyte software/drivers are installed and running.")
                raise WMIConnectionError(error_msg)

            return True
        except Exception as e:
            self.initialization_error = e
            self._cleanup_com()
            return False

    def _get_wmi_instance(self, class_name: str) -> Optional[Any]:
        """Safely gets the first instance of a WMI class."""
        if not self._wmi_conn: return None
        try:
            # The wmi library might dynamically create methods for classes.
            # A direct query is more robust.
            instances = self._wmi_conn.query(f"SELECT * FROM {class_name}")
            return instances[0] if instances else None
        except Exception:
            return None

    def _cleanup_com(self):
        """Uninitializes COM for this thread."""
        if self._com_initialized and _pythoncom_available and pythoncom:
            try:
                pythoncom.CoUninitialize()
            except Exception as e:
                print(f"Error during COM uninitialization: {e}", file=sys.stderr)
            finally:
                self._com_initialized = False

    # --- Core Logic ---
    def run(self):
        """Main loop of the WMI worker thread."""
        try:
            if not self._init_wmi():
                self.initialization_complete.set() # Signal failure to unblock main thread
                return

            self.initialization_complete.set() # Signal success before entering loop

            while True:
                request = self._request_queue.get()
                if request == WMI_WORKER_STOP_SIGNAL:
                    break
                if isinstance(request, tuple) and len(request) == 3:
                    self._process_request(request)
                else:
                    print(f"WMI Worker: Received invalid request format: {request}", file=sys.stderr)
        except Exception as e:
            print(f"WMI Worker: Unhandled exception in main loop: {e}", file=sys.stderr)
        finally:
            self._wmi_get_obj = self._wmi_set_obj = self._wmi_conn = None
            self._cleanup_com()

    def _process_request(self, request: WMIRequest):
        """Processes a single request using the dispatch table."""
        action, params, callback_queue = request
        result, exception = None, None
        try:
            handler = self._action_handlers.get(action)
            if handler:
                result = handler(params)
            else:
                exception = ValueError(f"Unknown WMI action requested: {action}")
        except Exception as e:
            exception = e
        self._send_response(callback_queue, result, exception)

    def _send_response(self, callback_queue: queue.Queue, result: Any, exception: Optional[Exception]):
        """Puts the result or exception onto the callback queue."""
        try:
            callback_queue.put((result, exception), block=False)
        except queue.Full:
            print("Warning: WMI response queue was unexpectedly full. Discarding response.", file=sys.stderr)

    # --- WMI Method Execution and Value Parsing ---
    def _execute_wmi_method(self, obj: Any, method_name: str, **kwargs) -> Any:
        """Executes a method on a WMI object instance, raising detailed errors."""
        if not obj:
            raise WMIConnectionError("WMI object is not available for method execution.")
        if not hasattr(obj, method_name):
            raise AttributeError(f"WMI object does not have method '{method_name}'")
        
        # Ensure numeric data is passed as float for compatibility.
        if 'Data' in kwargs and isinstance(kwargs['Data'], (int, float)):
             kwargs['Data'] = float(kwargs['Data'])
             
        method_func = getattr(obj, method_name)
        return method_func(**kwargs)

    def _parse_wmi_result(self, result: Any) -> Optional[Any]:
        """Extracts the primary value from a typical WMI method result tuple."""
        if isinstance(result, tuple) and len(result) > 0:
            return result[0]
        return result

    def _validate_temp(self, value: Any) -> float:
        """Validates and cleans a temperature reading."""
        try:
            temp = float(value)
            return temp if 0 < temp < 150 and not math.isnan(temp) else TEMP_READ_ERROR_VALUE
        except (ValueError, TypeError, IndexError, TypeError):
            return TEMP_READ_ERROR_VALUE

    def _validate_rpm(self, value: Any) -> int:
        """Validates and cleans an RPM reading, including byte swapping."""
        try:
            raw_int = int(value)
            if 0 <= raw_int <= 65535:
                # Gigabyte's RPM value is often byte-swapped.
                low_byte = raw_int & 0xFF
                high_byte = (raw_int >> 8) & 0xFF
                corrected_rpm = (low_byte << 8) | high_byte
                return corrected_rpm if corrected_rpm > 50 else 0
            return RPM_READ_ERROR_VALUE
        except (ValueError, TypeError):
            return RPM_READ_ERROR_VALUE

    def _validate_int(self, value: Any, default_error_val: int) -> int:
        """Validates and cleans a generic integer reading."""
        try:
            return int(value)
        except (ValueError, TypeError):
            return default_error_val

    # --- Action Handlers (called from dispatch table) ---
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
            except AttributeError: # Ignore if a method doesn't exist
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
        """Handles the combined sensor read action in a single operation."""
        return {
            'cpu_temp': self._handle_get_cpu_temp({}),
            'gpu_temp': self._handle_get_gpu_temp({}),
            'fan1_rpm': self._handle_get_rpm({"method_name": WMI_GET_RPM1}),
            'fan2_rpm': self._handle_get_rpm({"method_name": WMI_GET_RPM2}),
            'charge_policy': self._handle_get_charge_policy({}),
            'charge_threshold': self._handle_get_charge_stop({})
        }

    def _handle_get_non_temp_sensors(self, params: Dict) -> Dict[str, Any]:
        """Handles reading sensors except for temperatures."""
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
# WMIInterface (Public Synchronous API)
# ==============================================================================
class WMIInterface:
    """
    Provides a synchronous, thread-safe public API for WMI operations,
    hiding the complexity of the background worker thread.
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
        """Safely check if the worker thread is considered running."""
        with self._lock:
            return self._is_running and self._worker_thread is not None and self._worker_thread.is_alive()

    def start(self) -> bool:
        """Starts the WMI worker thread and waits for it to initialize."""
        with self._lock:
            if self._is_running:
                return self._initialization_error is None
            if not _wmi_available:
                self._initialization_error = WMIConnectionError("WMI library not found.")
                return False

            self._initialization_error = None
            self._worker_thread = WMIWorker(self._request_queue, self._wmi_get_class, self._wmi_set_class)
            self._worker_thread.start()
            self._is_running = True

        # Wait for the worker to finish its initialization attempt.
        self._worker_thread.initialization_complete.wait(timeout=15.0)

        with self._lock:
            # Check for initialization errors after waiting.
            if self._worker_thread.initialization_error:
                self._initialization_error = WMIConnectionError(
                    f"WMI worker failed to initialize: {self._worker_thread.initialization_error}"
                )
                self._cleanup_worker_nolock()
                return False
            # Check for timeout or thread death.
            if not self._worker_thread.is_alive():
                self._initialization_error = WMIConnectionError("WMI worker thread failed to start or died unexpectedly.")
                self._cleanup_worker_nolock()
                return False
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

        if thread_to_join:
            thread_to_join.join(timeout=WMI_REQUEST_TIMEOUT_S + 2.0)
            if thread_to_join.is_alive():
                print("Warning: WMI worker thread did not stop gracefully.", file=sys.stderr)
        
        with self._lock:
            self._worker_thread = None

    def _cleanup_worker_nolock(self):
        """Internal cleanup helper. Assumes lock is already held."""
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
        """Returns the error encountered during initialization, if any."""
        with self._lock:
            return self._initialization_error

    def _execute_sync(self, action: str, params: Optional[Dict] = None, timeout: float = WMI_REQUEST_TIMEOUT_S) -> Any:
        """
        Sends a request to the worker and waits for the response synchronously.
        Raises WMIError exceptions on failure.
        """
        if not self.is_running:
            raise self._initialization_error or WMIConnectionError("WMI interface is not running.")

        result_queue = queue.Queue(maxsize=1)
        request: WMIRequest = (action, params or {}, result_queue)

        try:
            self._request_queue.put(request, block=True, timeout=1.0)
        except queue.Full:
            raise WMIRequestTimeoutError(f"WMI request queue is full. Action '{action}' dropped.")

        try:
            result_data, exception_obj = result_queue.get(block=True, timeout=timeout)
            if exception_obj:
                raise WMICommandError(f"WMI action '{action}' failed.", original_exception=exception_obj)
            return result_data
        except queue.Empty:
            raise WMIRequestTimeoutError(f"WMI request '{action}' timed out after {timeout}s.")
        except WMIError as e:
            raise e # Re-raise our specific errors
        except Exception as e:
            raise WMIError(f"Unexpected error waiting for WMI response for '{action}': {e}")

    # --- Public API Methods ---
    def get_cpu_temperature(self) -> float:
        """Gets the current CPU temperature."""
        try:
            return self._execute_sync(WMI_ACTION_GET_CPU_TEMP)
        except WMIError:
            return TEMP_READ_ERROR_VALUE

    def get_gpu_temperature(self) -> float:
        """Gets the current GPU temperature (max of available sensors)."""
        try:
            return self._execute_sync(WMI_ACTION_GET_GPU_TEMP)
        except WMIError:
            return TEMP_READ_ERROR_VALUE

    def get_fan_rpm(self, fan_index: int) -> int:
        """Gets the RPM for the specified fan index (1 or 2)."""
        if fan_index not in [1, 2]: return RPM_READ_ERROR_VALUE
        method = WMI_GET_RPM1 if fan_index == 1 else WMI_GET_RPM2
        try:
            return self._execute_sync(WMI_ACTION_GET_RPM, {"method_name": method})
        except WMIError:
            return RPM_READ_ERROR_VALUE

    def get_battery_charge_policy(self) -> int:
        """Gets the current battery charge policy code."""
        try:
            return self._execute_sync(WMI_ACTION_GET_CHARGE_POLICY)
        except WMIError:
            return CHARGE_POLICY_READ_ERROR_VALUE

    def get_battery_charge_threshold(self) -> int:
        """Gets the current battery charge stop threshold percentage."""
        try:
            return self._execute_sync(WMI_ACTION_GET_CHARGE_STOP)
        except WMIError:
            return CHARGE_THRESHOLD_READ_ERROR_VALUE

    def get_all_sensors(self) -> Dict[str, Any]:
        """Gets all sensor readings in a single, efficient WMI call."""
        try:
            return self._execute_sync(WMI_ACTION_GET_ALL_SENSORS)
        except WMIError:
            # On failure, return a dictionary with default error values
            return {
                'cpu_temp': TEMP_READ_ERROR_VALUE,
                'gpu_temp': TEMP_READ_ERROR_VALUE,
                'fan1_rpm': RPM_READ_ERROR_VALUE,
                'fan2_rpm': RPM_READ_ERROR_VALUE,
                'charge_policy': CHARGE_POLICY_READ_ERROR_VALUE,
                'charge_threshold': CHARGE_THRESHOLD_READ_ERROR_VALUE
            }

    def get_non_temp_sensors(self) -> Dict[str, Any]:
        """Gets all non-temperature sensor readings in a single call."""
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
        """Sets the necessary WMI flags to enable custom (app-controlled) fan speed."""
        try:
            return self._execute_sync(WMI_ACTION_CONFIGURE_CUSTOM_FAN)
        except WMIError as e:
            print(f"WMI Error (configure_custom_fan): {e}", file=sys.stderr)
            return False

    def configure_bios_fan_control(self) -> bool:
        """Sets the necessary WMI flags to return fan control to the BIOS/EC."""
        try:
            return self._execute_sync(WMI_ACTION_CONFIGURE_BIOS_FAN)
        except WMIError as e:
            print(f"WMI Error (configure_bios_fan): {e}", file=sys.stderr)
            return False

    def set_fan_speed_raw(self, raw_speed_value: float) -> bool:
        """Sets the raw speed value (0-229) for both fans."""
        raw_speed_value = max(0.0, min(229.0, float(raw_speed_value)))
        try:
            return self._execute_sync(WMI_ACTION_SET_FAN_SPEED_RAW, {"speed_value": raw_speed_value})
        except WMIError as e:
            print(f"WMI Error (set_fan_speed_raw): {e}", file=sys.stderr)
            return False

    def set_battery_charge_policy(self, policy_code: int) -> bool:
        """Sets the battery charge policy using the raw code (e.g., 0 or 4)."""
        try:
            return self._execute_sync(WMI_ACTION_SET_CHARGE_POLICY, {"policy_value": float(policy_code)})
        except WMIError as e:
            print(f"WMI Error (set_charge_policy): {e}", file=sys.stderr)
            return False

    def set_battery_charge_threshold(self, threshold_percent: int) -> bool:
        """Sets the battery charge stop threshold percentage."""
        threshold_percent = max(MIN_CHARGE_PERCENT, min(MAX_CHARGE_PERCENT, int(threshold_percent)))
        try:
            return self._execute_sync(WMI_ACTION_SET_CHARGE_STOP, {"threshold_value": float(threshold_percent)})
        except WMIError as e:
            print(f"WMI Error (set_charge_stop): {e}", file=sys.stderr)
            return False