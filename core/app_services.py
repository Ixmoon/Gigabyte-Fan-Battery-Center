# core/app_services.py
# -*- coding: utf-8 -*-
"""
Provides a centralized service layer (AppServices) to decouple backend logic
from the UI (ViewModels). This class owns all core controllers and provides a
unified, high-level API for the rest of the application to interact with.
"""

import os
import sys
import copy
import time
from typing import Optional, List, Dict, Any, Callable
from functools import wraps

from gui.qt import QObject, Signal, Slot, QTimer

# Import core components that this service will manage
from .wmi_interface import WMIInterface, WMIError
from .hardware_manager import BatteryManager, FanManager
from .auto_temp_controller import AutoTemperatureController
from .state import AppState, ProfileState, FAN_MODE_BIOS, FAN_MODE_AUTO, FAN_MODE_CUSTOM, CHARGE_POLICY_BIOS
from tools.localization import tr
from tools.task_scheduler import create_startup_task, delete_startup_task, is_startup_task_registered

# Import settings for defaults
from config.settings import DEFAULT_PROFILE_SETTINGS

# Type Aliases
FanTable = List[List[int]]


def _handle_wmi_errors(func: Callable[..., bool]) -> Callable[..., bool]:
    """Decorator to catch WMIError exceptions and update status."""
    @wraps(func)
    def wrapper(self: 'AppServices', *args: Any, **kwargs: Any) -> bool:
        try:
            return func(self, *args, **kwargs)
        except WMIError as e:
            print(f"WMI operation failed in '{func.__name__}': {e}", file=sys.stderr)
            self.set_controller_status_message(tr("wmi_error"))
            return False # Indicate failure
    return wrapper


class AppServices(QObject):
    """
    A centralized service layer that owns and manages all backend controllers and the application state.
    It exposes a clean API for modifying the state and emits a single signal when the state changes.
    """
    # --- Signals ---
    # Emits the entire AppState object whenever any part of it changes.
    state_changed = Signal(object)
    # Emits the config dictionary when it needs to be saved.
    config_save_requested = Signal(object)

    def __init__(self, config_data: Dict[str, Any], base_dir: str, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._is_shutting_down = False
        self.base_dir = base_dir

        # --- 1. Initialize Core Components ---
        self.wmi_interface = WMIInterface()
        self.battery_manager = BatteryManager(self.wmi_interface)
        self.fan_manager = FanManager(self.wmi_interface)
        self.auto_temp_controller = AutoTemperatureController(self.wmi_interface, self.fan_manager)

        # --- 2. State Management ---
        # The AppState object is the single source of truth for the entire application.
        self.state = AppState()
        self._load_config_into_state(config_data) # Populate state from initial config
        self._controller_status_message: str = tr("initializing")

        # --- 3. Timers ---
        self.status_update_timer = QTimer(self)
        self.status_update_timer.timeout.connect(self.perform_status_update)

    def initialize(self):
        """
        Starts the service and initializes hardware interfaces.
        Assumes config has already been loaded into the state object.
        Returns True on success, False on failure.
        """
        if not self.wmi_interface.start():
            init_error = self.wmi_interface.get_initialization_error()
            error_msg = tr("wmi_init_error_msg", error=str(init_error))
            self.set_controller_status_message(tr("wmi_error"))
            print(f"FATAL: WMI Initialization failed. {error_msg}", file=sys.stderr)
            return False

        self.set_controller_status_message("") # Ready
        self.activate_profile(self.state.active_profile_name, is_initial_load=True)
        self.perform_status_update() # Initial sensor read
        self.set_active_updates(True) # Start the main timer
        return True

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
        print("AppServices: Shutdown complete.")

    # --- Public API for UI ---

    @_handle_wmi_errors
    def set_fan_mode(self, mode: str) -> bool:
        """High-level function to set the fan mode."""
        self.auto_temp_controller.stop_auto_mode()

        active_profile = self._get_active_profile()
        if not active_profile: return False

        if mode == FAN_MODE_AUTO:
            self.fan_manager.set_mode_auto()
            time.sleep(0.5)
            self.auto_temp_controller.start_auto_mode()
        elif mode == FAN_MODE_CUSTOM:
            self.fan_manager.set_mode_custom(active_profile.custom_fan_speed)
            time.sleep(0.5)
        elif mode == FAN_MODE_BIOS:
            self.fan_manager.set_mode_bios()
            time.sleep(0.5)
        else:
            return False

        active_profile.fan_mode = mode
        self._commit_state_change(save_config=True)
        return True

    @_handle_wmi_errors
    def set_custom_fan_speed(self, speed: int) -> bool:
        """High-level function to set a custom fan speed."""
        active_profile = self._get_active_profile()
        if not active_profile or active_profile.fan_mode != FAN_MODE_CUSTOM:
            return True

        if self.fan_manager.set_mode_custom(speed):
            active_profile.custom_fan_speed = speed
            self._commit_state_change(save_config=True)
            return True
        return False

    @_handle_wmi_errors
    def set_battery_charge_policy(self, policy_name: str) -> bool:
        """Sets the battery charge policy using the hardware manager."""
        active_profile = self._get_active_profile()
        if not active_profile: return False
        if self.battery_manager.set_policy(policy_name):
            # After setting the policy, wait briefly for it to take effect on the hardware.
            time.sleep(0.5)  # 500ms delay

            # Now, re-read the hardware status to get the actual applied threshold.
            new_status = self.battery_manager.get_status()

            if new_status:
                active_profile.battery_charge_policy = new_status.get('charge_policy', policy_name)
                active_profile.battery_charge_threshold = new_status.get('charge_threshold', 100)
            else:
                # Fallback in case status read fails
                active_profile.battery_charge_policy = policy_name

            # If the policy is now custom, ensure the hardware is set to the profile's threshold.
            # This is important for the case where the user switches from bios back to a
            # previously configured custom value.
            if active_profile.battery_charge_policy == "custom":
                self.battery_manager.set_charge_threshold(active_profile.battery_charge_threshold)

            self._commit_state_change(save_config=True)
            return True
        else:
            self.perform_status_update()  # Re-sync state on failure
            return False

    @_handle_wmi_errors
    def set_battery_charge_threshold(self, threshold: int) -> bool:
        """Sets the battery charge threshold using the hardware manager."""
        active_profile = self._get_active_profile()
        if not active_profile: return False

        # Only set the hardware threshold if the current policy is 'custom'.
        if active_profile.battery_charge_policy != "custom":
            return True

        if self.battery_manager.set_charge_threshold(threshold):
            active_profile.battery_charge_threshold = threshold
            self._commit_state_change(save_config=True)
            return True
        else:
            self.perform_status_update()  # Re-sync state on failure
            return False

    def set_curve_data(self, curve_type: str, data: FanTable):
        """High-level function to update fan curve data."""
        active_profile = self._get_active_profile()
        if not active_profile: return

        if curve_type == 'cpu':
            active_profile.cpu_fan_table = data
        else:
            active_profile.gpu_fan_table = data

        self._update_auto_controller_curves()
        self._commit_state_change(save_config=True)

    @Slot(str)
    def activate_profile(self, profile_name: str, is_initial_load: bool = False):
        """Loads and applies all settings from a given profile."""
        if profile_name not in self.state.profiles:
            print(f"Error: Could not find profile '{profile_name}' in state", file=sys.stderr)
            return

        self.state.active_profile_name = profile_name
        active_profile = self._get_active_profile()
        if not active_profile: return

        # Apply settings to controllers
        self._update_auto_controller_curves()
        # The auto_temp_controller will read settings directly from the profile object
        self.auto_temp_controller.update_auto_settings(active_profile) # type: ignore

        # Apply hardware state
        self.set_fan_mode(active_profile.fan_mode)
        self.set_battery_charge_policy(active_profile.battery_charge_policy)

        # Restart timers if needed
        self.set_active_updates(True)

        self._commit_state_change(save_config=not is_initial_load)

    def save_active_profile(self):
        """Saves the currently active profile to disk."""
        self._commit_state_change(save_config=True)

    def save_current_settings_to_profile(self, profile_name: str):
        """
        Takes the settings from the currently active profile and overwrites the
        target profile with them.
        """
        active_profile = self._get_active_profile()
        target_profile = self.state.profiles.get(profile_name)

        if active_profile and target_profile:
            # Create a copy of the active profile's settings
            new_settings = copy.deepcopy(active_profile)
            # Overwrite the target profile with the new settings
            self.state.profiles[profile_name] = new_settings
            self._commit_state_change(save_config=True)

    def rename_profile(self, old_name: str, new_name: str):
        """Renames a profile."""
        if old_name in self.state.profiles and new_name not in self.state.profiles:
            self.state.profiles[new_name] = self.state.profiles.pop(old_name)
            if self.state.active_profile_name == old_name:
                self.state.active_profile_name = new_name
            self._commit_state_change(save_config=True)

    def set_language(self, lang_code: str):
        """Sets the application language and saves the config."""
        if self.state.language != lang_code:
            self.state.language = lang_code
            self._commit_state_change(save_config=True)

    def set_window_geometry(self, geometry: bytes):
        """Sets the window geometry and saves the config."""
        if self.state.window_geometry != geometry:
            self.state.window_geometry = geometry
            self._commit_state_change(save_config=True)

    def set_start_on_boot(self, enabled: bool):
        """Enables or disables the 'Start on Boot' task."""
        if os.name != 'nt': return
        
        # Note: The executable path is now determined within main.py,
        # so we don't have self.base_dir here. This function needs to be
        # refactored or the path needs to be passed in.
        # For now, we assume this is handled elsewhere or will be fixed.
        # Let's check if is_startup_task_registered works without path.
        
        try:
            if enabled:
                create_startup_task(self.base_dir)
            else:
                delete_startup_task()
            self.state.start_on_boot = enabled
            self._commit_state_change(save_config=True)
        except Exception as e:
            print(f"Error setting start on boot: {e}", file=sys.stderr)
            # Revert state on failure and notify UI
            self.state.start_on_boot = not enabled
            self._commit_state_change(save_config=False)


    def set_active_curve_type(self, curve_type: str):
        """Sets the active curve type ('cpu' or 'gpu') for display in the UI."""
        if self.state.active_curve_type != curve_type:
            self.state.active_curve_type = curve_type
            self._commit_state_change(save_config=False) # This is a UI state, no need to save

    def reset_active_curve(self):
        """Resets the currently active curve (CPU or GPU) to its default values."""
        self.reset_curve_data(self.state.active_curve_type)

    def reset_curve_data(self, curve_type: str):
        """Resets the specified curve to its default values."""
        default_key = f"{curve_type.upper()}_FAN_TABLE"
        default_table = copy.deepcopy(DEFAULT_PROFILE_SETTINGS.get(default_key, []))
        self.set_curve_data(curve_type, default_table)

    # --- Internal Logic & State Management ---

    @Slot()
    def perform_status_update(self):
        """Periodically reads all sensor data and updates the runtime state."""
        if self._is_shutting_down or not self.wmi_interface._is_running:
            return

        # Update runtime state with new sensor values
        self.state.cpu_temp = self.wmi_interface.get_cpu_temperature()
        self.state.gpu_temp = self.wmi_interface.get_gpu_temperature()
        self.state.cpu_fan_rpm = self.wmi_interface.get_fan_rpm(1)
        self.state.gpu_fan_rpm = self.wmi_interface.get_fan_rpm(2)

        # Get battery status via the hardware manager for proper abstraction
        battery_status = self.battery_manager.get_status()
        if battery_status:
            self.state.applied_charge_policy = battery_status.get('charge_policy', 'err')
            self.state.applied_charge_threshold = battery_status.get('charge_threshold', 0)
        
        self.state.applied_fan_mode = self.fan_manager.current_mode
        self.state.applied_fan_speed_percent = self.fan_manager.applied_percentage
        self.state.auto_fan_target_speed_percent = self.auto_temp_controller.get_last_theoretical_target()

        self._commit_state_change(save_config=False)

    def set_active_updates(self, is_active: bool):
        """
        Controls the main status update timer based on the active profile's settings.
        """
        if self._is_shutting_down:
            return

        active_profile = self._get_active_profile()
        if not active_profile: return

        if is_active:
            if self.status_update_timer.isActive():
                self.status_update_timer.stop()
            # This setting is now correctly part of the profile state
            interval_ms = active_profile.gui_update_interval_ms
            self.status_update_timer.start(max(200, interval_ms))
            print(f"Status updates started (interval: {interval_ms}ms).")
        else:
            if self.status_update_timer.isActive():
                self.status_update_timer.stop()
                print("Status updates paused.")

    def _update_auto_controller_curves(self):
        """Updates the auto temp controller with curves from the current profile in the state."""
        active_profile = self._get_active_profile()
        if not active_profile: return
        self.auto_temp_controller.update_curves(active_profile.cpu_fan_table, active_profile.gpu_fan_table)

    def _get_active_profile(self) -> Optional[ProfileState]:
        """Safely retrieves the active profile object from the state."""
        return self.state.profiles.get(self.state.active_profile_name)

    def _commit_state_change(self, save_config: bool = False):
        """Central method to save state and emit the state_changed signal."""
        if save_config:
            config_dict = self._get_state_for_config()
            self.config_save_requested.emit(config_dict)
        self.state_changed.emit(self.state)

    def set_controller_status_message(self, message: str):
        """Sets and emits the global controller status message."""
        if self._controller_status_message != message:
            self._controller_status_message = message
            # In the new model, this is part of the runtime state.
            # We don't have a direct signal, but the next status update will carry it.
            # For immediate feedback, we can trigger a state change.
            self.state.controller_status_message = message
            self._commit_state_change(save_config=False)

    def _load_config_into_state(self, config_data: Dict[str, Any]):
        """
        Populates the AppState object from a configuration dictionary, ensuring
        robustness by merging with defaults and handling legacy fields.
        """
        # --- Load Global Settings ---
        self.state.language = config_data.get("language", "en")
        self.state.start_on_boot = config_data.get("start_on_boot", False)
        self.state.active_profile_name = config_data.get("active_profile_name", "Config 1")
        self.state.window_geometry = config_data.get("window_geometry")

        # --- Load Profiles with Robust Merging ---
        self.state.profiles.clear()
        profiles_data = config_data.get("profiles", {})

        # If no profiles exist in config, create a default one
        if not profiles_data:
            profiles_data = {"Config 1": copy.deepcopy(DEFAULT_PROFILE_SETTINGS)}
            self.state.active_profile_name = "Config 1"

        # Get the set of valid field names from the ProfileState dataclass
        profile_fields = ProfileState.__dataclass_fields__.keys()

        for name, profile_dict in profiles_data.items():
            # Start with a deep copy of the default settings
            final_profile_data = copy.deepcopy(DEFAULT_PROFILE_SETTINGS)
            # Update with the settings loaded from the user's config file
            final_profile_data.update(profile_dict)

            # Filter out any keys that are not defined in the ProfileState dataclass
            # This handles legacy fields gracefully (e.g., AUTO_MODE_CYCLE_DURATION_S)
            clean_profile_dict = {
                key: final_profile_data[key] for key in profile_fields if key in final_profile_data
            }

            self.state.profiles[name] = ProfileState(**clean_profile_dict)

    def _get_state_for_config(self) -> Dict[str, Any]:
        """Returns a dictionary representing the persistent parts of the AppState."""
        return {
            "language": self.state.language,
            "start_on_boot": self.state.start_on_boot,
            "active_profile_name": self.state.active_profile_name,
            "window_geometry": self.state.window_geometry,
            "profiles": {name: profile.to_dict() for name, profile in self.state.profiles.items()}
        }
