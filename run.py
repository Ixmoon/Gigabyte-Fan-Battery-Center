# run.py
# -*- coding: utf-8 -*-
"""
Contains the AppRunner class which orchestrates the application's core components
and manages the main update loop.
"""
import os
import sys
import time
from typing import Optional, List, Dict, Any

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QObject, QTimer, pyqtSlot, QCoreApplication

# Import core components
from core.wmi_interface import WMIInterface
from core.fan_controller import FanController
from core.battery_controller import BatteryController
from core.auto_temp_controller import AutoTemperatureController

# Import tools
from tools.config_manager import ConfigManager, ProfileSettings
from tools.localization import tr, set_language, load_translations
from tools.task_scheduler import create_startup_task, delete_startup_task, is_startup_task_registered

# Import GUI
from gui.main_window import MainWindow, AppStatus

# Import ViewModels
from viewmodels.fan_control_viewmodel import FanControlViewModel
from viewmodels.battery_control_viewmodel import BatteryControlViewModel
from viewmodels.curve_control_viewmodel import CurveControlViewModel

# Import settings
from config.settings import (
    TEMP_READ_ERROR_VALUE, RPM_READ_ERROR_VALUE,
    CHARGE_POLICY_READ_ERROR_VALUE, CHARGE_THRESHOLD_READ_ERROR_VALUE,
    INIT_APPLIED_PERCENTAGE, DEFAULT_PROFILE_SETTINGS
)

# Type alias for internal use
CurveType = str
FanTable = List[List[int]]

class AppRunner(QObject):
    """Orchestrates application components and manages the update loop."""

    def __init__(self, config_manager: ConfigManager, start_minimized: bool):
        super().__init__()
        self.config_manager = config_manager
        self.start_minimized = start_minimized

        # --- Instantiate Core Components ---
        self.wmi_interface = WMIInterface()
        self.fan_controller = FanController(self.wmi_interface)
        self.battery_controller = BatteryController(self.wmi_interface)
        self.auto_temp_controller = AutoTemperatureController(self.wmi_interface, self.fan_controller)

        # --- Instantiate ViewModels ---
        self.fan_control_vm = FanControlViewModel(self)
        self.battery_control_vm = BatteryControlViewModel(self)
        self.curve_control_vm = CurveControlViewModel(self)
        
        # --- Instantiate GUI (passing ViewModels) ---
        self.main_window = MainWindow(
            app_runner=self,
            config_manager=self.config_manager,
            fan_control_vm=self.fan_control_vm,
            battery_control_vm=self.battery_control_vm,
            curve_control_vm=self.curve_control_vm,
            start_minimized=self.start_minimized
        )

        # --- State Variables ---
        self._current_profile: ProfileSettings = DEFAULT_PROFILE_SETTINGS.copy()
        self._last_status_update_time: float = 0.0
        self._controller_status_message: str = tr("initializing")
        self._is_shutting_down: bool = False
        self._is_in_background: bool = start_minimized

        # --- Timers ---
        self.status_update_timer = QTimer(self)
        self.status_update_timer.timeout.connect(self.perform_status_update)

        # --- Connect Signals ---
        self._connect_signals()

        # --- Initialization ---
        self._initialize_components()

    def _connect_signals(self):
        """Connect signals between components, including ViewModels."""
        # Connections from MainWindow to AppRunner (for non-ViewModel managed parts or global actions)
        self.main_window.quit_requested.connect(self.shutdown)
        self.main_window.language_changed_signal.connect(self.handle_language_change) # SettingsPanel direct
        self.main_window.background_state_changed.connect(self.set_background_state)
        
        # Curve data changes from CurveCanvas (still owned by MainWindow)
        self.main_window.curve_changed_signal.connect(self.handle_curve_change)

        # Profile and Start on Boot actions are now connected to CurveControlViewModel
        self.curve_control_vm.profile_to_activate_signal.connect(self.handle_profile_activation)
        self.curve_control_vm.profile_to_save_signal.connect(self.handle_profile_save) # Assumes VM emits (name, settings_dict)
        self.curve_control_vm.profile_to_rename_signal.connect(self.handle_profile_rename)
        self.curve_control_vm.start_on_boot_to_apply_signal.connect(self.handle_start_on_boot_change)
        self.curve_control_vm.curve_to_reset_signal.connect(self.handle_curve_reset_request)

        # Fan and Battery control signals from MainWindow (which were relays) are removed.
        # FanControlViewModel and BatteryControlViewModel directly call AppRunner's set_X_for_hardware methods.

    def _initialize_components(self):
        """Initializes WMI, loads config, applies initial profile, starts timers."""
        if not self.wmi_interface.start():
            init_error = self.wmi_interface.get_initialization_error()
            error_msg = tr("wmi_init_error_msg", error=str(init_error))
            self._controller_status_message = tr("wmi_error")
            self.main_window.show_error_message(tr("wmi_init_error_title"), error_msg)
            self.main_window.set_controls_enabled_state(False) # Disables all panels via MainWindow
            # Also explicitly disable ViewModels
            self.fan_control_vm.set_panel_enabled(False)
            self.battery_control_vm.set_panel_enabled(False)
            self.curve_control_vm.set_panel_enabled(False)
            self._emit_status_update() # Update StatusInfoPanel
        else:
            self._controller_status_message = tr("ready")
            self.main_window.set_controls_enabled_state(True)
            self.fan_control_vm.set_panel_enabled(True)
            self.battery_control_vm.set_panel_enabled(True)
            self.curve_control_vm.set_panel_enabled(True)
            
            self.handle_profile_activation(self.config_manager.get_active_profile_name(), is_initial_load=True)
            self.perform_status_update() # Initial sensor read and VM update
            
            if not self._is_in_background:
                self._configure_and_start_status_timer()

        self._sync_start_on_boot_state_with_vm()


    def _configure_and_start_status_timer(self):
        """Starts or restarts the main status update timer."""
        if self._is_shutting_down: return
        if self.status_update_timer.isActive():
            self.status_update_timer.stop()
        status_interval_ms = self._current_profile.get("GUI_UPDATE_INTERVAL_MS", DEFAULT_PROFILE_SETTINGS['GUI_UPDATE_INTERVAL_MS'])
        status_interval_ms = max(200, status_interval_ms)
        if not self._is_in_background:
            self.status_update_timer.start(status_interval_ms)

    def _sync_start_on_boot_state_with_vm(self):
        """Ensures config, task scheduler, and ViewModel state match."""
        if os.name == 'nt':
            try:
                is_registered = is_startup_task_registered()
                self.curve_control_vm.update_start_on_boot_status(is_registered) # Update VM
                
                config_value = self.config_manager.get("start_on_boot", False)
                if config_value != is_registered:
                    self.config_manager.set("start_on_boot", is_registered)
                    self.config_manager.save_config()
            except Exception as e:
                print(f"Error syncing start on boot state: {e}", file=sys.stderr)
        else: # Not on Windows
            self.curve_control_vm.update_start_on_boot_status(False)
            # MainWindow's start_on_boot_checkbox is managed by CurveControlPanel via CurveControlViewModel

    @pyqtSlot()
    def perform_status_update(self):
        """Periodically called by status timer to read sensors and update ViewModels and StatusInfoPanel."""
        if self._is_shutting_down or not self.wmi_interface._is_running or self._is_in_background:
            return

        now = time.monotonic()
        self._last_status_update_time = now

        cpu_temp = self.wmi_interface.get_cpu_temperature()
        gpu_temp = self.wmi_interface.get_gpu_temperature()
        fan1_rpm = self.wmi_interface.get_fan_rpm(1)
        fan2_rpm = self.wmi_interface.get_fan_rpm(2)
        charge_policy_str, charge_threshold = self.battery_controller.refresh_status()
        theoretical_target = self.auto_temp_controller.get_last_theoretical_target()

        if not self.main_window._is_showing_transient_status: # MainWindow still manages its own transient status for now
            self._controller_status_message = tr("wmi_error") if not self.wmi_interface._is_running else tr("ready")

        # Update ViewModels
        self.fan_control_vm.update_fan_mode_from_status(self.fan_controller.current_mode)
        self.fan_control_vm.update_applied_fixed_speed_from_status(self.fan_controller.applied_percentage)
        
        self.battery_control_vm.update_charge_policy_from_status(charge_policy_str)
        self.battery_control_vm.update_applied_charge_threshold_from_status(charge_threshold)

        # CurveControlViewModel doesn't have direct status fields like temp/RPM to update from here.
        # Its state (profile names, active profile) is updated by specific actions.

        # Emit status for StatusInfoPanel (via MainWindow) and potentially other non-VM listeners
        self._emit_status_to_mainwindow(cpu_temp, gpu_temp, fan1_rpm, fan2_rpm,
                                       charge_policy_str, charge_threshold, theoretical_target)

    def _emit_status_to_mainwindow(self, cpu_temp=None, gpu_temp=None, fan1_rpm=None, fan2_rpm=None,
                                 charge_policy=None, charge_threshold=None, theoretical_target=None):
        """Constructs AppStatus and sends it to MainWindow (primarily for StatusInfoPanel and CurveCanvas)."""
        status = AppStatus(
            cpu_temp=cpu_temp if cpu_temp is not None else TEMP_READ_ERROR_VALUE,
            gpu_temp=gpu_temp if gpu_temp is not None else TEMP_READ_ERROR_VALUE,
            fan1_rpm=fan1_rpm if fan1_rpm is not None else RPM_READ_ERROR_VALUE,
            fan2_rpm=fan2_rpm if fan2_rpm is not None else RPM_READ_ERROR_VALUE,
            current_fan_mode=self.fan_controller.current_mode, # Source of truth from controller
            applied_fan_percentage=self.fan_controller.applied_percentage, # Source of truth
            theoretical_target_percentage=theoretical_target if theoretical_target is not None else self.auto_temp_controller.get_last_theoretical_target(),
            current_charge_policy=charge_policy if charge_policy is not None else self.battery_controller.current_policy, # Source of truth
            current_charge_threshold=charge_threshold if charge_threshold is not None else self.battery_controller.current_threshold, # Source of truth
            controller_status_message=self._controller_status_message
        )
        if not self._is_in_background:
            self.main_window.update_status_display(status) # MainWindow uses this for StatusInfoPanel and CurveCanvas indicators

    # --- Methods called by UI interaction (now primarily by ViewModels directly or via their signals) ---

    # Removed set_fan_mode_from_ui, set_fixed_speed_from_ui,
    # set_charge_policy_from_ui, set_charge_threshold_from_ui.
    # Panels call ViewModel methods, and ViewModels call AppRunner's set_X_for_hardware methods.

    def set_fan_mode_for_hardware(self, mode: str, desired_fixed_speed: Optional[int] = None):
        """Applies fan mode to hardware and updates config."""
        # Called by FanControlViewModel
        success = False
        if mode == "auto":
            self.auto_temp_controller.stop_auto_mode()
            success = self.fan_controller.set_mode_auto()
            if success: self.auto_temp_controller.start_auto_mode()
        elif mode == "fixed":
            self.auto_temp_controller.stop_auto_mode()
            current_speed = desired_fixed_speed if desired_fixed_speed is not None else self.fan_control_vm.get_current_fixed_speed()
            success = self.fan_controller.set_mode_fixed(current_speed)

        if success:
            self._save_setting_to_active_profile("fan_mode", mode)
            if mode == "fixed":
                self._save_setting_to_active_profile("fixed_fan_speed", current_speed)
            # Hardware state will be reflected in next perform_status_update, which updates VM.
        else:
            self._controller_status_message = tr("wmi_error")
            # Revert VM or let next status update handle it. For now, status update will correct.
        if not self._is_in_background: self.main_window._set_transient_status(tr("applying_settings")) # MainWindow for global transient
        QTimer.singleShot(1000, self._reset_status_message)

    def set_fixed_fan_speed_for_hardware(self, speed: int):
        """Applies fixed fan speed to hardware. Called by FanControlViewModel."""
        if self.fan_control_vm.get_current_fan_mode() == "fixed":
            success = self.fan_controller.set_mode_fixed(speed)
            if success:
                self._save_setting_to_active_profile("fixed_fan_speed", speed)
                # Confirm to ViewModel that the speed was (assumed to be) applied
                self.fan_control_vm.confirm_fixed_speed_applied(speed)
            else:
                self._controller_status_message = tr("wmi_error")
                # If failed, still unlock the UI but potentially with the old/current speed
                # The ViewModel's fixed_speed_updated signal will handle UI update based on internal state.
                # We should ensure the ViewModel's _current_fixed_speed reflects the last known good value.
                # For now, just confirm with the speed that was attempted, or a known "safe" value.
                # Better: Re-fetch current applied speed if possible, or use ViewModel's current value.
                # Simplest: Confirm with the speed that was attempted, UI will snap back if VM's state wasn't updated.
                self.fan_control_vm.confirm_fixed_speed_applied(self.fan_control_vm.get_current_fixed_speed()) # Or self.fan_controller.applied_percentage
            
            if not self._is_in_background: self.main_window._set_transient_status(tr("applying_settings"))
            # The _reset_status_message might happen before or after confirm_fixed_speed_applied fully updates UI.
            # Consider if confirm_fixed_speed_applied should be called after a slight delay or if transient message needs adjustment.
            QTimer.singleShot(1000, self._reset_status_message) # This resets global status, not the lock.
    
    def set_charge_policy_for_hardware(self, policy: str, desired_threshold: Optional[int] = None):
        """Applies charge policy to hardware. Called by BatteryControlViewModel."""
        success = self.battery_controller.set_policy(policy)
        if success:
            self._save_setting_to_active_profile("charge_policy", policy)
            if policy == "custom":
                current_threshold = desired_threshold if desired_threshold is not None else self.battery_control_vm.get_current_charge_threshold()
                self.set_charge_threshold_for_hardware(current_threshold, from_policy_change=True)
        else:
            self._controller_status_message = tr("wmi_error")
        if not self._is_in_background: self.main_window._set_transient_status(tr("applying_settings"))
        QTimer.singleShot(1000, self._reset_status_message)

    def set_charge_threshold_for_hardware(self, threshold: int, from_policy_change: bool = False):
        """Applies charge threshold to hardware. Called by BatteryControlViewModel."""
        if self.battery_control_vm.get_current_charge_policy() == "custom" or from_policy_change:
            success = self.battery_controller.set_threshold(threshold)
            if success:
                self._save_setting_to_active_profile("charge_threshold", threshold)
                # Confirm to ViewModel that the threshold was (assumed to be) applied
                self.battery_control_vm.confirm_charge_threshold_applied(threshold)
            else:
                self._controller_status_message = tr("wmi_error")
                # If failed, still unlock the UI but with the current known threshold
                self.battery_control_vm.confirm_charge_threshold_applied(self.battery_control_vm.get_current_charge_threshold()) # Or self.battery_controller.current_threshold
            
            if not from_policy_change: # Avoid double transient message
                if not self._is_in_background: self.main_window._set_transient_status(tr("applying_settings"))
                # The _reset_status_message might happen before or after confirm_X_applied fully updates UI.
                # Consider if confirm_X_applied should be called after a slight delay or if transient message needs adjustment.
                QTimer.singleShot(1000, self._reset_status_message) # This resets global status, not the lock.


    @pyqtSlot(str, object)
    def handle_curve_change(self, curve_type: str, new_data_obj: object):
        """Handles changes to a fan curve from the CurveCanvas via MainWindow."""
        if not self._is_in_background:
            self.main_window._set_transient_status(tr("saving_config"))
        new_data = new_data_obj if isinstance(new_data_obj, list) else []
        config_key = "cpu_fan_table" if curve_type == 'cpu' else "gpu_fan_table"
        self._save_setting_to_active_profile(config_key, new_data)
        self._update_auto_controller_curves()
        if not self._is_in_background:
            QTimer.singleShot(1500, self._reset_status_message)

    def _update_auto_controller_curves(self):
        """Updates AutoTemperatureController with current profile's curves."""
        cpu_curve = self._current_profile.get("cpu_fan_table", DEFAULT_PROFILE_SETTINGS['cpu_fan_table'])
        gpu_curve = self._current_profile.get("gpu_fan_table", DEFAULT_PROFILE_SETTINGS['gpu_fan_table'])
        self.auto_temp_controller.update_curves(cpu_curve, gpu_curve)

    @pyqtSlot(str)
    def handle_profile_activation(self, profile_name: str, is_initial_load: bool = False):
        """Loads and applies settings from the selected profile."""
        if not is_initial_load and not self._is_in_background:
            self.main_window._set_transient_status(tr("applying_settings"))

        profile_settings = self.config_manager.get_profile(profile_name)
        if not profile_settings:
            if not self._is_in_background:
                self.main_window.show_error_message("Profile Error", f"Could not load profile '{profile_name}'.")
            self._reset_status_message()
            return

        self._current_profile = profile_settings.copy()
        self.config_manager.set_active_profile_name(profile_name)
        
        # Update ViewModels with profile settings
        self.fan_control_vm.apply_profile_settings(self._current_profile)
        self.battery_control_vm.apply_profile_settings(self._current_profile)
        self.curve_control_vm.apply_profile_settings(self._current_profile) # For things like active curve type if stored
        self.curve_control_vm.update_active_profile(profile_name)


        # Apply settings to hardware via direct calls (which also update controllers)
        self.set_fan_mode_for_hardware(
            self.fan_control_vm.get_current_fan_mode(),
            self.fan_control_vm.get_current_fixed_speed()
        )
        self.set_charge_policy_for_hardware(
            self.battery_control_vm.get_current_charge_policy(),
            self.battery_control_vm.get_current_charge_threshold()
        )
        
        self._update_auto_controller_curves()
        self.auto_temp_controller.update_auto_settings(self._current_profile)
        if self.fan_control_vm.get_current_fan_mode() == "auto":
            if not self.auto_temp_controller._adjustment_timer.isActive(): self.auto_temp_controller.start_auto_mode()
        else:
            if self.auto_temp_controller._adjustment_timer.isActive(): self.auto_temp_controller.stop_auto_mode()


        # Update MainWindow UI (for non-VM parts and CurveCanvas)
        if not self._is_in_background:
            self.main_window.apply_profile_to_ui(self._current_profile) 
            # apply_profile_to_ui in MainWindow should now mostly delegate to panels,
            # and panels would get their data from ViewModels or passed settings.
            # For CurveCanvas, it still needs direct data.

        self._configure_and_start_status_timer()

        if not is_initial_load:
            self.config_manager.save_config()
            if not self._is_in_background:
                self.main_window._set_transient_status(tr("profile_activated", name=profile_name))
                QTimer.singleShot(2000, self._reset_status_message)
        else: # Initial load message
            if self.wmi_interface._is_running : self._controller_status_message = tr("ready")
            else: self._controller_status_message = tr("wmi_error")


    @pyqtSlot(str) # Changed signature to match CurveControlViewModel.profile_to_save_signal
    def handle_profile_save(self, profile_name: str):
        """
        Saves the current UI settings (collected from MainWindow, which queries ViewModels and Canvas)
        to the specified profile.
        """
        if not self._is_in_background:
            self.main_window._set_transient_status(tr("saving_config"))
        
        # Get settings from MainWindow, which in turn gets them from ViewModels and CurveCanvas
        settings_to_save = self.main_window._get_current_settings_from_ui()

        if not isinstance(settings_to_save, dict): # Basic check
            print(f"Error: Could not retrieve valid settings for profile save '{profile_name}'.", file=sys.stderr)
            if not self._is_in_background: self._reset_status_message()
            return

        self.config_manager.save_profile(profile_name, settings_to_save)
        self.config_manager.save_config()

        if profile_name == self.config_manager.get_active_profile_name():
            self._current_profile = self.config_manager.get_active_profile() or DEFAULT_PROFILE_SETTINGS.copy()
            # Re-apply to ensure consistency if anything changed during save logic
            self.handle_profile_activation(profile_name, is_initial_load=False) # Re-activates with saved data

        if not self._is_in_background:
            self.main_window._set_transient_status(tr("profile_saved", name=profile_name))
            QTimer.singleShot(2000, self._reset_status_message)


    @pyqtSlot(str, str)
    def handle_profile_rename(self, old_name: str, new_name: str):
        """Renames a profile. Called by MainWindow (relayed from CurveControlViewModel)."""
        if not self._is_in_background:
            self.main_window._set_transient_status(tr("saving_config"))
        success = self.config_manager.rename_profile(old_name, new_name)
        if success:
            self.config_manager.save_config()
            
            # Notify CurveControlViewModel about the rename for UI updates
            self.curve_control_vm.confirm_profile_rename(old_name, new_name)
            
            # Refresh the entire profile list and active profile in the ViewModel
            current_active_profile = self.config_manager.get_active_profile_name() # Get current active after potential rename
            self.curve_control_vm.update_profile_list_and_active(
                self.config_manager.get_profile_names(),
                current_active_profile
            )
            
            if not self._is_in_background:
                # MainWindow's update_profile_button_name is now called by CurveControlPanel via VM signal.
                self.main_window._set_transient_status(tr("profile_renamed", new_name=new_name))
                QTimer.singleShot(2000, self._reset_status_message)
        else:
             if not self._is_in_background:
                 self.main_window.show_error_message(tr("rename_profile_error_title"), f"Failed to rename profile '{old_name}'.")
                 self._reset_status_message()


    @pyqtSlot(str)
    def handle_language_change(self, lang_code: str):
        """Handles language change request from GUI (SettingsPanel via MainWindow)."""
        set_language(lang_code)
        self.config_manager.set("language", lang_code)
        self.config_manager.save_config()
        if not self._is_in_background:
            self.main_window.retranslate_ui() # MainWindow tells all its children (panels, canvas) to retranslate
            self._reset_status_message()

    @pyqtSlot()
    def handle_curve_reset_request(self):
        """Handles request to reset the active curve to its default."""
        active_curve_type = self.curve_control_vm.current_curve_type # VM should provide this
        if not active_curve_type:
            print("Error: Could not determine active curve type for reset.", file=sys.stderr)
            return

        default_table_key = 'cpu_fan_table' if active_curve_type == 'cpu' else 'gpu_fan_table'
        default_table = DEFAULT_PROFILE_SETTINGS.get(default_table_key, [])

        if not default_table:
            print(f"Error: Could not find default data for curve type '{active_curve_type}'.", file=sys.stderr)
            return
        
        # Emit the curve_changed_signal which MainWindow listens to.
        # MainWindow.on_curve_modified will then update CurveCanvas and save the change.
        # This is slightly indirect but keeps the data flow consistent with manual curve changes.
        # Alternatively, AppRunner could directly call a method on CurveCanvas and then save.
        # For now, using existing signal path.
        # MainWindow's on_curve_modified emits self.main_window.curve_changed_signal to self.handle_curve_change
        # We want to trigger self.handle_curve_change directly here.
        
        # Directly update the curve canvas via a MainWindow method
        # And then save this change to the active profile.
        
        formatted_default_table = [list(p) for p in default_table]

        # 1. Update CurveCanvas display
        if self.main_window and self.main_window.curve_canvas:
            self.main_window.curve_canvas.blockSignals(True) # Prevent immediate re-emission of curve_changed
            # Determine which curve to update on the canvas
            if active_curve_type == 'cpu':
                self.main_window.curve_canvas.update_plot(formatted_default_table, None)
            elif active_curve_type == 'gpu':
                self.main_window.curve_canvas.update_plot(None, formatted_default_table)
            self.main_window.curve_canvas.blockSignals(False)
            self.main_window.curve_canvas.draw_idle() # Force redraw

        # 2. Save the reset curve to the active profile
        config_key = "cpu_fan_table" if active_curve_type == 'cpu' else "gpu_fan_table"
        self._save_setting_to_active_profile(config_key, formatted_default_table)
        
        # 3. Update the auto temperature controller with the new curve
        self._update_auto_controller_curves()
        
        if not self._is_in_background:
            self.main_window._set_transient_status(tr("applying_settings"))
            QTimer.singleShot(1500, self._reset_status_message)


    @pyqtSlot(bool)
    def handle_start_on_boot_change(self, enabled: bool):
        """
        Creates or deletes the startup task.
        Called by MainWindow (relayed from CurveControlViewModel/Panel).
        """
        if os.name != 'nt': return
        if not self._is_in_background:
            self.main_window._set_transient_status(tr("applying_settings"))

        success = False
        message = ""
        try:
            if enabled: success, message = create_startup_task()
            else: success, message = delete_startup_task()

            if success:
                self.config_manager.set("start_on_boot", enabled)
                self.config_manager.save_config()
                self.curve_control_vm.update_start_on_boot_status(enabled) # Update VM
                if not self._is_in_background:
                    self.main_window._set_transient_status(message)
                    QTimer.singleShot(3000, self._reset_status_message)
            else:
                self.curve_control_vm.update_start_on_boot_status(not enabled) # Revert VM
                if not self._is_in_background:
                    self.main_window.show_error_message(tr("task_scheduler_error_title"), message)
                    # MainWindow's checkbox state is now driven by CurveControlVM signal
                    self._reset_status_message()
        except Exception as e:
            self.curve_control_vm.update_start_on_boot_status(not enabled) # Revert VM
            if not self._is_in_background:
                self.main_window.show_error_message(tr("task_scheduler_error_title"), str(e))
                self._reset_status_message()


    def _save_setting_to_active_profile(self, key: str, value: Any):
        """Helper to save a single setting to the active profile and config file."""
        active_profile_name = self.config_manager.get_active_profile_name()
        profile_settings = self.config_manager.get_profile(active_profile_name)
        if profile_settings:
            settings_to_save = profile_settings.copy()
            settings_to_save[key] = value
            self.config_manager.save_profile(active_profile_name, settings_to_save)
            self.config_manager.save_config()
            if active_profile_name == self.config_manager.get_active_profile_name(): # Ensure current_profile is updated
                self._current_profile = settings_to_save.copy() # Update AppRunner's copy
            
            if key in ["FAN_ADJUSTMENT_INTERVAL_S", "FAN_HYSTERESIS_PERCENT", "MIN_ADJUSTMENT_STEP", "MAX_ADJUSTMENT_STEP"]:
                self.auto_temp_controller.update_auto_settings(self._current_profile)
            if key == "GUI_UPDATE_INTERVAL_MS":
                self._configure_and_start_status_timer()
        else:
            print(f"Warning: Could not find active profile '{active_profile_name}' to save setting '{key}'.", file=sys.stderr)


    def _reset_status_message(self):
        """Resets the status bar message and clears the transient flag in MainWindow."""
        if self._is_shutting_down or self._is_in_background: return
        if self.main_window:
            self.main_window._is_showing_transient_status = False # Let MainWindow manage this flag
        
        current_controller_message = tr("wmi_error") if not self.wmi_interface._is_running else tr("ready")
        if self._controller_status_message != current_controller_message:
             self._controller_status_message = current_controller_message
        
        # Trigger a status update to StatusInfoPanel via MainWindow
        if not self._is_in_background:
             QTimer.singleShot(0, self.perform_status_update) # perform_status_update will call _emit_status_to_mainwindow

    @pyqtSlot(bool)
    def set_background_state(self, is_background: bool):
        """Handles transitions between foreground and background operation."""
        if self._is_shutting_down or self._is_in_background == is_background:
            return
        self._is_in_background = is_background
        print(f"AppRunner: Entering {'background' if is_background else 'foreground'} state.")
        if is_background:
            print("AppRunner: Stopping status update timer.")
            self.status_update_timer.stop()
        else:
            print("AppRunner: Restarting status update timer.")
            self._configure_and_start_status_timer()
            QTimer.singleShot(50, self.perform_status_update)


    @pyqtSlot()
    def shutdown(self):
        """Performs graceful shutdown of components."""
        if self._is_shutting_down: return
        self._is_shutting_down = True
        print("AppRunner: Initiating shutdown...")
        self.status_update_timer.stop()
        if self.auto_temp_controller: self.auto_temp_controller.stop_auto_mode()
        print("AppRunner: Timers stopped.")

        if self.main_window and not self._is_in_background:
            self.main_window._set_transient_status(tr("shutting_down")) # MainWindow method for its status label
            QCoreApplication.processEvents()

        if self.wmi_interface:
            print("AppRunner: Stopping WMI Interface...")
            self.wmi_interface.stop()
            print("AppRunner: WMI Interface stopped.")

        if self.config_manager:
            print("AppRunner: Saving final configuration...")
            try:
                active_profile_name = self.config_manager.get_active_profile_name()
                if self._current_profile and active_profile_name: # Ensure profile exists
                    # Get settings from ViewModels to reflect user's last intended state
                    if self.fan_control_vm:
                        fan_settings = self.fan_control_vm.get_current_settings_for_profile()
                        self._current_profile["fan_mode"] = fan_settings.get("fan_mode", self.fan_controller.current_mode)
                        self._current_profile["fixed_fan_speed"] = fan_settings.get("fixed_fan_speed", self.fan_controller.applied_percentage)
                    else: # Fallback to controller state if VM not available
                        self._current_profile["fan_mode"] = self.fan_controller.current_mode
                        self._current_profile["fixed_fan_speed"] = self.fan_controller.applied_percentage

                    if self.battery_control_vm:
                        battery_settings = self.battery_control_vm.get_current_settings_for_profile()
                        self._current_profile["charge_policy"] = battery_settings.get("charge_policy", self.battery_controller.current_policy or DEFAULT_PROFILE_SETTINGS["charge_policy"])
                        self._current_profile["charge_threshold"] = battery_settings.get("charge_threshold", self.battery_controller.current_threshold if self.battery_controller.current_threshold != CHARGE_THRESHOLD_READ_ERROR_VALUE else DEFAULT_PROFILE_SETTINGS["charge_threshold"])
                    else: # Fallback
                        self._current_profile["charge_policy"] = self.battery_controller.current_policy or DEFAULT_PROFILE_SETTINGS["charge_policy"]
                        self._current_profile["charge_threshold"] = self.battery_controller.current_threshold if self.battery_controller.current_threshold != CHARGE_THRESHOLD_READ_ERROR_VALUE else DEFAULT_PROFILE_SETTINGS["charge_threshold"]
                    
                    self.config_manager.save_profile(active_profile_name, self._current_profile)
            except Exception as e:
                 print(f"Warning: Failed to update/save final profile settings during shutdown: {e}", file=sys.stderr)
            self.config_manager.save_config()
            print("AppRunner: Configuration saved.")

        print("AppRunner: Shutdown complete.")
        app = QApplication.instance()
        if app:
            print("AppRunner: Quitting QApplication.")
            QTimer.singleShot(0, app.quit)
