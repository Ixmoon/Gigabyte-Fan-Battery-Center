# core/app_services.py
# -*- coding: utf-8 -*-
"""
Provides a centralized service layer (AppServices) to decouple backend logic
from the UI (ViewModels). This class owns all core controllers and provides a
unified, high-level API for the rest of the application to interact with.
"""

import os
import sys
from typing import Optional, List, Dict, Any
from functools import wraps

from gui.qt import QObject, Signal, Slot, QTimer

# Import core components that this service will manage
from .wmi_interface import WMIInterface, WMIError
from .fan_controller import FanController
from .battery_controller import BatteryController
from .auto_temp_controller import AutoTemperatureController
from tools.config_manager import ConfigManager, ProfileSettings
from tools.localization import tr
from tools.task_scheduler import create_startup_task, delete_startup_task, is_startup_task_registered
from gui.main_window import AppStatus # Import the data structure

# Import settings for defaults and constants
from config.settings import (
    DEFAULT_PROFILE_SETTINGS,
    TEMP_READ_ERROR_VALUE, RPM_READ_ERROR_VALUE,
    CHARGE_THRESHOLD_READ_ERROR_VALUE,
    FAN_MODE_AUTO, FAN_MODE_FIXED, CHARGE_POLICY_CUSTOM_STR
)

# Type Aliases
FanTable = List[List[int]]

class AppServices(QObject):
    """
    A centralized service layer that owns and manages all backend controllers.
    It exposes a clean API to the ViewModels and emits signals for state changes.
    """
    # --- Signals for ViewModel consumption ---
    # Status Updates
    status_updated = Signal(object) # Emits an AppStatus-like object
    controller_status_message_changed = Signal(str) # e.g., "WMI Error", "Applying Settings"

    # Fan Control Updates
    fan_control_updated = Signal(str, int) # fan_mode, applied_speed

    # Battery Control Updates
    battery_control_updated = Signal(str, int) # charge_policy, charge_threshold

    # Profile Updates
    profile_list_changed = Signal(list, str) # profile_names, active_profile_name
    active_profile_applied = Signal(dict) # The full settings dictionary of the active profile

    # Curve Updates
    curve_data_updated = Signal(str, list) # curve_type ('cpu' or 'gpu'), new_data

    # System Settings Updates
    start_on_boot_changed = Signal(bool)

    def __init__(self, base_dir: str, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.base_dir = base_dir
        self._is_shutting_down = False

        # --- 1. Initialize Core Components ---
        self.config_manager = ConfigManager(base_dir=self.base_dir)
        self.wmi_interface = WMIInterface()
        self.fan_controller = FanController(self.wmi_interface)
        self.battery_controller = BatteryController(self.wmi_interface)
        self.auto_temp_controller = AutoTemperatureController(self.wmi_interface, self.fan_controller)

        # --- 2. State Variables ---
        self._current_profile: ProfileSettings = DEFAULT_PROFILE_SETTINGS.copy()
        self._controller_status_message: str = tr("initializing")

        # --- 3. Timers ---
        self.status_update_timer = QTimer(self)
        self.status_update_timer.timeout.connect(self.perform_status_update)

    def initialize(self):
        """
        Starts the service, loads configuration, and initializes hardware interfaces.
        Returns True on success, False on failure.
        """
        self.config_manager.load_config()

        if not self.wmi_interface.start():
            init_error = self.wmi_interface.get_initialization_error()
            error_msg = tr("wmi_init_error_msg", error=str(init_error))
            self.set_controller_status_message(tr("wmi_error"))
            # In a real app, you might emit a fatal error signal here
            print(f"FATAL: WMI Initialization failed. {error_msg}", file=sys.stderr)
            return False

        self.set_controller_status_message("") # Ready
        self.activate_profile(self.config_manager.get_active_profile_name(), is_initial_load=True)
        self.perform_status_update() # Initial sensor read
        self.set_active_updates(True) # Start the main timer
        self.start_on_boot_changed.emit(is_startup_task_registered())
        return True

    def reload_and_reapply_config(self):
        """Forces a reload of the config from disk and reapplies it."""
        self.config_manager.load_config(force_reload=True)
        self.activate_profile(self.config_manager.get_active_profile_name())
        # Emit signals to notify the UI layer of potential changes
        self.start_on_boot_changed.emit(self.is_start_on_boot_enabled())

    def is_start_on_boot_enabled(self) -> bool:
        """Checks if the start on boot task is registered."""
        return is_startup_task_registered()

    def shutdown(self):
        """Gracefully shuts down all services."""
        if self._is_shutting_down:
            return
        self._is_shutting_down = True
        print("AppServices: Initiating shutdown...")
        self.status_update_timer.stop()
        if self.auto_temp_controller:
            self.auto_temp_controller.stop_auto_mode()

        if self.wmi_interface:
            self.wmi_interface.stop()

        if self.config_manager:
            # Final save of geometry or other non-profile settings might be needed
            self.config_manager.save_config()
        print("AppServices: Shutdown complete.")

    # --- Public API for ViewModels ---

    # General
    def get_all_profile_names(self) -> List[str]:
        return self.config_manager.get_profile_names()

    def get_active_profile_name(self) -> str:
        return self.config_manager.get_active_profile_name()

    def get_initial_ui_profile(self) -> Optional[ProfileSettings]:
        """Provides the initial, full profile settings for the UI layer."""
        return self.config_manager.get_active_profile()

    # --- Error Handling Decorator ---
    def _handle_wmi_errors(func):
        """Decorator to catch WMIError exceptions and update status."""
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            try:
                return func(self, *args, **kwargs)
            except WMIError as e:
                print(f"WMI operation failed in '{func.__name__}': {e}", file=sys.stderr)
                self.set_controller_status_message(tr("wmi_error"))
                return False # Indicate failure
        return wrapper

    # --- Wrapped Public API Methods ---

    @_handle_wmi_errors
    def set_fan_mode(self, mode: str, desired_fixed_speed: Optional[int] = None) -> bool:
        """High-level function to set the fan mode."""
        self.auto_temp_controller.stop_auto_mode() # Always stop for any mode change

        if mode == FAN_MODE_AUTO:
            self.fan_controller.set_mode_auto()
            self.auto_temp_controller.start_auto_mode() # Restart after setting to auto
        elif mode == FAN_MODE_FIXED:
            speed = desired_fixed_speed if desired_fixed_speed is not None else self._current_profile.get("fixed_fan_speed", 50)
            self.fan_controller.set_mode_fixed(speed)
        else:
            return False # Invalid mode

        # The decorator handles WMI errors, so if we reach here, the operation was queued.
        # We can optimistically update the state.
        self._save_setting_to_active_profile("fan_mode", mode)
        if mode == FAN_MODE_FIXED:
            self._save_setting_to_active_profile("fixed_fan_speed", speed)
        
        self.fan_control_updated.emit(self.fan_controller.current_mode, self.fan_controller.applied_percentage)
        return True

    @_handle_wmi_errors
    def set_fixed_fan_speed(self, speed: int) -> bool:
        """High-level function to set a fixed fan speed."""
        if self.fan_controller.current_mode != FAN_MODE_FIXED:
            return True # Not an error, just do nothing.

        if self.fan_controller.set_mode_fixed(speed):
            self._save_setting_to_active_profile("fixed_fan_speed", speed)
            self.fan_control_updated.emit(self.fan_controller.current_mode, self.fan_controller.applied_percentage)
            return True
        return False

    @_handle_wmi_errors
    def set_charge_policy(self, policy: str, desired_threshold: Optional[int] = None) -> bool:
        """High-level function to set the battery charge policy."""
        self.battery_controller.set_policy(policy)

        self._save_setting_to_active_profile("charge_policy", policy)
        if policy == CHARGE_POLICY_CUSTOM_STR:
            threshold = desired_threshold if desired_threshold is not None else self._current_profile.get("charge_threshold", 80)
            # set_charge_threshold is also decorated, so we just call it.
            self.set_charge_threshold(threshold)
        
        self.battery_control_updated.emit(self.battery_controller.current_policy, self.battery_controller.current_threshold)
        return True

    @_handle_wmi_errors
    def set_charge_threshold(self, threshold: int) -> bool:
        """High-level function to set the charge threshold."""
        if self.battery_controller.current_policy != CHARGE_POLICY_CUSTOM_STR:
            return True # Not an error, do nothing.

        if self.battery_controller.set_threshold(threshold):
            self._save_setting_to_active_profile("charge_threshold", threshold)
            self.battery_control_updated.emit(self.battery_controller.current_policy, self.battery_controller.current_threshold)
            return True
        return False

    # Curve Control
    def set_curve_data(self, curve_type: str, data: FanTable):
        """High-level function to update fan curve data."""
        config_key = "cpu_fan_table" if curve_type == 'cpu' else "gpu_fan_table"
        self._save_setting_to_active_profile(config_key, data)
        self._update_auto_controller_curves()
        self.curve_data_updated.emit(curve_type, data)

    def reset_active_curve(self, curve_type: str):
        """Resets the specified curve to its default values."""
        default_key = f"{curve_type}_fan_table"
        default_table = DEFAULT_PROFILE_SETTINGS.get(default_key, [])
        self.set_curve_data(curve_type, default_table)

    # Profile Management
    @Slot(str)
    def activate_profile(self, profile_name: str, is_initial_load: bool = False):
        """Loads and applies all settings from a given profile."""
        profile_settings = self.config_manager.get_profile(profile_name)
        if not profile_settings:
            print(f"Error: Could not load profile '{profile_name}'", file=sys.stderr)
            return

        self._current_profile = profile_settings.copy()
        self.config_manager.set_active_profile_name(profile_name)

        # Apply settings to controllers
        self._update_auto_controller_curves()
        self.auto_temp_controller.update_auto_settings(self._current_profile)

        # Apply hardware state
        self.set_fan_mode(self._current_profile.get("fan_mode"), self._current_profile.get("fixed_fan_speed"))
        self.set_charge_policy(self._current_profile.get("charge_policy"), self._current_profile.get("charge_threshold"))

        # Restart timers if needed
        self.set_active_updates(True)

        if not is_initial_load:
            self.config_manager.save_config()

        # Notify listeners
        self.active_profile_applied.emit(self._current_profile)
        self.profile_list_changed.emit(self.get_all_profile_names(), self.get_active_profile_name())


    def save_profile(self, profile_name: str):
        """Gathers current state and saves it to a profile."""
        settings_to_save = self.gather_current_settings_for_profile()
        self.config_manager.save_profile(profile_name, settings_to_save)
        self.config_manager.save_config()
        if profile_name == self.get_active_profile_name():
            # If we just saved the active profile, ensure our internal state matches exactly
            # what was just saved.
            self._current_profile = settings_to_save.copy()
            self.activate_profile(profile_name) # Re-apply to ensure consistency

    def rename_profile(self, old_name: str, new_name: str):
        """Renames a profile."""
        success = self.config_manager.rename_profile(old_name, new_name)
        if success:
            self.config_manager.save_config()
            self.profile_list_changed.emit(self.get_all_profile_names(), self.get_active_profile_name())

    # System Settings
    def set_start_on_boot(self, enabled: bool):
        """Enables or disables the 'Start on Boot' task."""
        if os.name != 'nt': return
        success, message = create_startup_task(self.base_dir) if enabled else delete_startup_task()
        if success:
            self.config_manager.set("start_on_boot", enabled)
            self.config_manager.save_config()
            self.start_on_boot_changed.emit(enabled)
        else:
            print(f"Error setting start on boot: {message}", file=sys.stderr)
            self.start_on_boot_changed.emit(not enabled) # Revert state on failure

    # --- Internal Logic ---

    @Slot()
    def perform_status_update(self):
        """Periodically reads all sensor data and emits update signals."""
        if self._is_shutting_down or not self.wmi_interface._is_running:
            return

        # Read all hardware states
        cpu_temp = self.wmi_interface.get_cpu_temperature()
        gpu_temp = self.wmi_interface.get_gpu_temperature()
        fan1_rpm = self.wmi_interface.get_fan_rpm(1)
        fan2_rpm = self.wmi_interface.get_fan_rpm(2)
        self.battery_controller.refresh_status() # Update controller's internal state
        charge_policy = self.battery_controller.current_policy
        charge_threshold = self.battery_controller.current_threshold
        theoretical_target = self.auto_temp_controller.get_last_theoretical_target()

        # Consolidate status into a single object for the main status panel
        status_obj = AppStatus(
            cpu_temp=cpu_temp,
            gpu_temp=gpu_temp,
            fan1_rpm=fan1_rpm,
            fan2_rpm=fan2_rpm,
            current_fan_mode=self.fan_controller.current_mode,
            applied_fan_percentage=self.fan_controller.applied_percentage,
            theoretical_target_percentage=theoretical_target,
            current_charge_policy=charge_policy,
            current_charge_threshold=charge_threshold,
            controller_status_message=self._controller_status_message
        )
        self.status_updated.emit(status_obj)

        # Emit specific signals for dedicated ViewModels
        self.fan_control_updated.emit(self.fan_controller.current_mode, self.fan_controller.applied_percentage)
        self.battery_control_updated.emit(charge_policy, charge_threshold)

    def set_active_updates(self, is_active: bool):
        """
        Controls the main status update timer. Call with True for foreground/active
        operation and False for background/paused operation.
        """
        if self._is_shutting_down:
            return

        if is_active:
            if self.status_update_timer.isActive():
                self.status_update_timer.stop()
            interval_ms = self._current_profile.get("GUI_UPDATE_INTERVAL_MS", 1500)
            self.status_update_timer.start(max(200, interval_ms))
            print(f"Status updates started (interval: {interval_ms}ms).")
        else:
            if self.status_update_timer.isActive():
                self.status_update_timer.stop()
                print("Status updates paused.")

    def _update_auto_controller_curves(self):
        """Updates the auto temp controller with curves from the current profile."""
        cpu_curve = self._current_profile.get("cpu_fan_table", [])
        gpu_curve = self._current_profile.get("gpu_fan_table", [])
        self.auto_temp_controller.update_curves(cpu_curve, gpu_curve)

    def _save_setting_to_active_profile(self, key: str, value: Any):
        """Helper to save a single setting to the active profile and config file."""
        active_name = self.get_active_profile_name()
        profile = self.config_manager.get_profile(active_name)
        if profile:
            profile[key] = value
            self.config_manager.save_profile(active_name, profile)
            self.config_manager.save_config()
            self._current_profile = profile.copy() # Keep internal state synced

    def set_controller_status_message(self, message: str):
        """Sets and emits the global controller status message."""
        if self._controller_status_message != message:
            self._controller_status_message = message
            self.controller_status_message_changed.emit(message)

    def gather_current_settings_for_profile(self) -> ProfileSettings:
        """
        Gathers all relevant settings from the current internal state (_current_profile)
        which is kept in sync by the various set_* methods.
        """
        # The _current_profile dictionary is the single source of truth,
        # constantly updated by user actions via the set_* methods.
        return self._current_profile.copy()
