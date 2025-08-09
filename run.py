# run.py
# -*- coding: utf-8 -*-
"""
Contains the AppRunner class which orchestrates the UI components,
connecting them to the AppServices backend.
"""
import os
import sys
from typing import Optional, List, Dict, Any

from gui.qt import QApplication, QObject, QTimer, Slot, QCoreApplication

# Import the service layer
from core.app_services import AppServices

# Import GUI
from gui.main_window import MainWindow, AppStatus

# Import ViewModels
from viewmodels.fan_control_viewmodel import FanControlViewModel
from viewmodels.battery_control_viewmodel import BatteryControlViewModel
from viewmodels.curve_control_viewmodel import CurveControlViewModel

# Import tools for localization
from tools.localization import tr, set_language
from tools.single_instance import write_hwnd_to_shared_memory, is_primary, IsWindow

class AppRunner(QObject):
    """
    Orchestrates the UI layer (MainWindow and ViewModels) and connects it to
    the backend services provided by AppServices.
    """

    def __init__(self, app_services: AppServices, start_minimized: bool):
        super().__init__()
        self.app_services = app_services
        self.start_minimized = start_minimized
        self._is_shutting_down = False
        self._is_in_background = start_minimized

        # --- Instantiate ViewModels (now receive AppServices) ---
        self.fan_control_vm = FanControlViewModel(self.app_services)
        self.battery_control_vm = BatteryControlViewModel(self.app_services)
        self.curve_control_vm = CurveControlViewModel(self.app_services)

        # --- Instantiate GUI (passing ViewModels) ---
        self.main_window = MainWindow(
            app_runner=self, # Still needed for global actions like quit, language
            fan_control_vm=self.fan_control_vm,
            battery_control_vm=self.battery_control_vm,
            curve_control_vm=self.curve_control_vm,
            start_minimized=self.start_minimized
        )

        # --- Connect Signals ---
        self._connect_signals()

        # --- Initial UI State Sync ---
        self._initialize_ui_state()
        self.load_window_geometry()

    def _connect_signals(self):
        """Connect signals between AppServices, ViewModels, and MainWindow."""
        # --- Global UI Actions ---
        self.main_window.quit_requested.connect(self.shutdown)
        self.main_window.language_changed_signal.connect(self.handle_language_change)
        self.main_window.background_state_changed.connect(self.set_background_state)
        self.main_window.window_geometry_changed.connect(self.save_window_geometry)
        self.main_window.window_initialized_signal.connect(self._handle_window_initialized)

        # --- Connect ViewModels to AppServices ---

        # FanControlViewModel -> AppServices
        self.fan_control_vm.fan_mode_set_requested.connect(self.app_services.set_fan_mode)
        self.fan_control_vm.fixed_speed_set_requested.connect(self.app_services.set_fixed_fan_speed)

        # AppServices -> FanControlViewModel
        self.app_services.fan_control_updated.connect(self.fan_control_vm.update_from_service)

        # BatteryControlViewModel -> AppServices
        self.battery_control_vm.charge_policy_set_requested.connect(self.app_services.set_charge_policy)
        self.battery_control_vm.charge_threshold_set_requested.connect(self.app_services.set_charge_threshold)

        # AppServices -> BatteryControlViewModel
        self.app_services.battery_control_updated.connect(self.battery_control_vm.update_from_service)

        # CurveControlViewModel -> AppServices
        # self.curve_control_vm.profile_to_activate_signal.connect(self.app_services.activate_profile) # ViewModel now calls service directly
        self.curve_control_vm.profile_to_save_signal.connect(self.handle_profile_save_request)
        self.curve_control_vm.profile_to_rename_signal.connect(self.app_services.rename_profile)
        self.curve_control_vm.start_on_boot_to_apply_signal.connect(self.app_services.set_start_on_boot)
        self.curve_control_vm.curve_to_reset_signal.connect(self.app_services.reset_active_curve)

        # AppServices -> CurveControlViewModel
        self.app_services.profile_list_changed.connect(self.curve_control_vm.update_profile_list_and_active)
        self.app_services.start_on_boot_changed.connect(self.curve_control_vm.update_start_on_boot_status)

        # --- Connect AppServices to MainWindow for general updates ---
        self.app_services.status_updated.connect(self.main_window.update_status_display)
        self.app_services.controller_status_message_changed.connect(self.main_window.set_transient_status)
        self.app_services.active_profile_applied.connect(self.main_window.apply_profile_to_ui)

        # Curve data changes from CurveCanvas -> ViewModel -> AppServices
        self.main_window.curve_changed_signal.connect(self.curve_control_vm.handle_curve_change)


    def _initialize_ui_state(self):
        """Populates the UI with the initial state from AppServices."""
        # Let ViewModels populate themselves from AppServices signals upon connection
        # or provide initial state methods in AppServices.
        # For example, CurveControlViewModel can get initial lists.
        self.curve_control_vm.update_profile_list_and_active(
            self.app_services.get_all_profile_names(),
            self.app_services.get_active_profile_name()
        )
        # Explicitly apply the full active profile to the UI on startup
        # to ensure all controls, especially the curve canvas, are populated.
        initial_profile_settings = self.app_services.get_initial_ui_profile()
        if initial_profile_settings:
            self.main_window.apply_profile_to_ui(initial_profile_settings)

        # Other VMs will be updated by the first status signals from AppServices.

    @Slot()
    def reload_and_apply_config(self):
        """Forces a reload of the config from disk and applies it to the running application."""
        print("Reloading configuration from disk...")
        # The AppServices layer will handle the logic of reloading and applying
        # the new settings to its internal controllers.
        self.app_services.reload_and_reapply_config()

        # After the service layer has reloaded, we need to update the UI.
        # The `active_profile_applied` signal from AppServices will trigger
        # `main_window.apply_profile_to_ui` to update the visuals.
        # We also need to ensure the profile list and active profile name are
        # up-to-date in the CurveControlViewModel.
        self.curve_control_vm.update_profile_list_and_active(
            self.app_services.get_all_profile_names(),
            self.app_services.get_active_profile_name()
        )
        # We also need to re-check the start on boot status.
        self.curve_control_vm.update_start_on_boot_status(
            self.app_services.is_start_on_boot_enabled()
        )
        # And re-translate the UI in case the language was changed externally.
        new_lang = self.app_services.config_manager.get("language")
        set_language(new_lang)
        self.main_window.retranslate_ui()
        print("Configuration reloaded and applied.")

    @Slot(int)
    def _handle_window_initialized(self, hwnd: int):
        """Handles writing the main window HWND to shared memory for single instance control."""
        if os.name == 'nt' and is_primary():
            if IsWindow(hwnd):
                print(f"Main window HWND obtained via signal: {hwnd}")
                write_hwnd_to_shared_memory(hwnd)
            else:
                print(f"Warning: Received invalid HWND ({hwnd}) from main window.", file=sys.stderr)

    def save_window_geometry(self, geometry_hex: str):
        """Saves the window geometry to the config."""
        self.app_services.config_manager.set("window_geometry", geometry_hex)
        # No need to call save here, it will be saved on graceful shutdown

    def load_window_geometry(self):
        """Loads and applies window geometry from the config."""
        geometry_hex = self.app_services.config_manager.get("window_geometry")
        if geometry_hex:
            self.main_window.restore_geometry_from_hex(geometry_hex)

    @Slot(str)
    def handle_profile_save_request(self, profile_name: str):
        """
        Tells AppServices to gather the current state and save it to a profile.
        The responsibility of gathering settings is now fully within AppServices.
        """
        self.app_services.save_profile(profile_name)

    @Slot(str)
    def handle_language_change(self, lang_code: str):
        """Handles language change, saves it, and retranstales the UI."""
        # This is a UI-specific concern, so AppRunner handles it.
        set_language(lang_code)
        self.app_services.config_manager.set("language", lang_code)
        self.app_services.config_manager.save_config()
        self.main_window.retranslate_ui()

    @Slot(bool)
    def set_background_state(self, is_background: bool):
        """Handles transitions between foreground and background operation."""
        if self._is_shutting_down or self._is_in_background == is_background:
            return
        self._is_in_background = is_background
        # Use the new public method to control the service's update loop
        self.app_services.set_active_updates(not is_background)

    @Slot()
    def shutdown(self):
        """Initiates a graceful shutdown via AppServices and quits the app."""
        if self._is_shutting_down:
            return
        self._is_shutting_down = True
        print("AppRunner: Initiating shutdown...")

        # AppServices handles the core component shutdown
        self.app_services.shutdown()

        # Quit the application
        app = QApplication.instance()
        if app:
            print("AppRunner: Quitting QApplication.")
            QTimer.singleShot(0, app.quit)
