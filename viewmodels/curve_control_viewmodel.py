# viewmodels/curve_control_viewmodel.py
# -*- coding: utf-8 -*-
"""
ViewModel for CurveControlPanel.
"""
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot
from typing import List, Optional, TYPE_CHECKING

from tools.task_scheduler import is_startup_task_registered # Import directly

if TYPE_CHECKING:
    from run import AppRunner
    from tools.config_manager import ProfileSettings # For type hinting curve data

class CurveControlViewModel(QObject):
    """
    Manages state and logic for curve selection, profiles, and startup settings.
    """
    # --- Signals to notify CurveControlPanel (View) ---
    active_curve_type_updated = pyqtSignal(str) # 'cpu' or 'gpu'
    profile_list_updated = pyqtSignal(list, str) # List of profile names, active profile name
    active_profile_updated = pyqtSignal(str) # Name of the new active profile
    start_on_boot_status_updated = pyqtSignal(bool) # True if enabled
    panel_enabled_updated = pyqtSignal(bool)
    # This signal is for the panel to update a specific button's text after AppRunner confirms rename
    profile_renamed_locally = pyqtSignal(str, str) # old_name, new_name

    # --- Signals to AppRunner ---
    profile_to_activate_signal = pyqtSignal(str)
    profile_to_save_signal = pyqtSignal(str) # Emits profile_name, AppRunner gathers settings
    profile_to_rename_signal = pyqtSignal(str, str) # old_name, new_name
    start_on_boot_to_apply_signal = pyqtSignal(bool)
    curve_to_reset_signal = pyqtSignal() # AppRunner knows active curve from this VM's state

    def __init__(self, app_runner: 'AppRunner', parent: Optional[QObject] = None):
        super().__init__(parent)
        self._app_runner = app_runner
        
        self._active_curve_type: str = "cpu" # Default
        self._profile_names: List[str] = []
        self._active_profile_name: Optional[str] = None
        self._is_start_on_boot_enabled: bool = False
        self._is_panel_enabled: bool = True

        # Initialize from AppRunner/ConfigManager
        self._load_initial_data()

    def _load_initial_data(self):
        """Loads initial profile names, active profile, and startup status."""
        self._profile_names = self._app_runner.config_manager.get_profile_names()
        self._active_profile_name = self._app_runner.config_manager.get_active_profile_name()
        self._is_start_on_boot_enabled = is_startup_task_registered() # Direct call for initial state
        
        # Emit initial states for the view
        self.profile_list_updated.emit(self._profile_names, self._active_profile_name or "")
        if self._active_profile_name:
             self.active_profile_updated.emit(self._active_profile_name)
        self.start_on_boot_status_updated.emit(self._is_start_on_boot_enabled)
        self.active_curve_type_updated.emit(self._active_curve_type)

    # --- Getters for View (used by panel for initial setup) ---
    @property
    def current_curve_type(self) -> str:
        return self._active_curve_type

    @property
    def profile_names(self) -> List[str]:
        return self._profile_names

    @property
    def active_profile_name(self) -> Optional[str]:
        return self._active_profile_name

    @property
    def is_start_on_boot_enabled(self) -> bool:
        return self._is_start_on_boot_enabled

    @property
    def panel_enabled(self) -> bool:
        return self._is_panel_enabled

    # --- Slots for CurveControlPanel (View) to call ---
    @pyqtSlot(str)
    def set_active_curve_type(self, curve_type: str):
        """Called by View when user selects CPU or GPU curve."""
        if curve_type not in ["cpu", "gpu"]: return
        if self._active_curve_type != curve_type:
            self._active_curve_type = curve_type
            self.active_curve_type_updated.emit(self._active_curve_type)
            # AppRunner might listen to this if it needs to do something specific beyond UI update.
            # For now, CurveCanvas listens via MainWindow.

    @pyqtSlot(str)
    def activate_profile(self, profile_name: str):
        """Called by View when user clicks a profile button. Emits signal to AppRunner."""
        if profile_name in self._profile_names and self._active_profile_name != profile_name:
            self.profile_to_activate_signal.emit(profile_name)
            # AppRunner will handle logic and then call self.update_active_profile
            
    @pyqtSlot(str) # profile_name for which to save current settings
    def request_save_profile(self, profile_name: str):
        """Called by View to save current UI settings to a specific profile. Emits signal to AppRunner."""
        self.profile_to_save_signal.emit(profile_name)
        # AppRunner will gather settings and save, then might update profile list if names changed (unlikely for save).

    @pyqtSlot(str, str) # old_name, new_name
    def request_rename_profile(self, old_name: str, new_name: str):
        """Called by View to rename a profile. Emits signal to AppRunner."""
        if old_name in self._profile_names and new_name and old_name != new_name:
            # Basic client-side validation, AppRunner might do more (e.g. check for actual duplicates in FS)
            self.profile_to_rename_signal.emit(old_name, new_name)
            # AppRunner will handle logic and then call self.confirm_profile_rename and self.update_profile_list

    @pyqtSlot(bool)
    def set_start_on_boot(self, enabled: bool):
        """Called by View when 'Start on Boot' checkbox changes. Emits signal to AppRunner."""
        if self._is_start_on_boot_enabled != enabled: # Only emit if state actually changes from user input
            self.start_on_boot_to_apply_signal.emit(enabled)
            # AppRunner will handle logic and then call self.update_start_on_boot_status

    @pyqtSlot() # No parameter needed, VM knows active curve type
    def request_reset_active_curve(self):
        """Called by View to reset the active curve to default. Emits signal to AppRunner."""
        self.curve_to_reset_signal.emit()
        # AppRunner will handle logic (using self._active_curve_type) and trigger curve update.

    # --- Slots for AppRunner (Model/Controller) to call to update ViewModel state ---
    @pyqtSlot(list, str) # profile_names, active_profile_name
    def update_profile_list_and_active(self, profile_names: List[str], active_profile_name: str):
        """Called by AppRunner when the list of profiles or active profile changes."""
        self._profile_names = profile_names
        self._active_profile_name = active_profile_name
        self.profile_list_updated.emit(self._profile_names, self._active_profile_name or "")
        if self._active_profile_name: # Ensure active_profile_updated is also emitted
            self.active_profile_updated.emit(self._active_profile_name)


    @pyqtSlot(str) # Only updates active profile name, assumes list is current
    def update_active_profile(self, active_profile_name: str):
        """Called by AppRunner when only the active profile name changes."""
        if self._active_profile_name != active_profile_name:
            self._active_profile_name = active_profile_name
            self.active_profile_updated.emit(self._active_profile_name)

    @pyqtSlot(str, str)
    def confirm_profile_rename(self, old_name: str, new_name: str):
        """Called by AppRunner after successfully renaming a profile in ConfigManager."""
        # Update internal list if AppRunner doesn't send a full new list immediately
        try:
            idx = self._profile_names.index(old_name)
            self._profile_names[idx] = new_name
        except ValueError:
            pass # Should not happen if AppRunner sends full list via update_profile_list_and_active
        
        if self._active_profile_name == old_name:
            self._active_profile_name = new_name
        
        self.profile_renamed_locally.emit(old_name, new_name) # For panel to update button text
        # AppRunner should also call update_profile_list_and_active to refresh the whole list in UI.

    @pyqtSlot(bool)
    def update_start_on_boot_status(self, enabled: bool):
        """Called by AppRunner with the current startup task registration status."""
        if self._is_start_on_boot_enabled != enabled:
            self._is_start_on_boot_enabled = enabled
            self.start_on_boot_status_updated.emit(self._is_start_on_boot_enabled)
            
    @pyqtSlot(bool)
    def set_panel_enabled(self, enabled: bool): # Renamed for consistency
        """Called by AppRunner/MainWindow to globally enable/disable controls."""
        if self._is_panel_enabled != enabled:
            self._is_panel_enabled = enabled
            self.panel_enabled_updated.emit(self._is_panel_enabled)

    def apply_profile_settings(self, settings: 'ProfileSettings'):
        """
        Applies curve/profile related settings from a profile.
        Primarily, this means ensuring the active curve type display is correct if
        the profile specifies a preferred one (though not standard).
        The actual profile activation and curve data loading is handled by AppRunner
        and directly by CurveCanvas. This ViewModel mainly reflects the *name* of the
        active profile and the list of available profiles.
        """
        # Example: if profile has a "default_active_curve_type"
        # new_curve_type = settings.get("default_active_curve_type", self._active_curve_type)
        # if self._active_curve_type != new_curve_type:
        #     self._active_curve_type = new_curve_type
        #     self.active_curve_type_changed.emit(self._active_curve_type)
        pass # Most profile data is handled by AppRunner causing updates to specific parts.

    def get_current_settings_for_profile(self) -> dict:
        """
        Returns settings managed by this ViewModel for saving.
        Currently, this ViewModel doesn't directly manage data points that are saved
        into a profile (like curve points or specific profile names).
        It reflects the *existence* and *selection* of profiles.
        The actual curve data is fetched from CurveCanvas by MainWindow/AppRunner.
        'start_on_boot' is a global setting, not per-profile.
        """
        # This ViewModel primarily manages UI state related to profile selection,
        # not the content of the profiles themselves.
        return {
            # "active_curve_type": self._active_curve_type # If this were a per-profile setting
        }