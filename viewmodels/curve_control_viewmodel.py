# viewmodels/curve_control_viewmodel.py
# -*- coding: utf-8 -*-
"""
ViewModel for CurveControlPanel.
"""
from gui.qt import QObject, Signal, Slot
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from core.app_services import AppServices
    from tools.config_manager import ProfileSettings

class CurveControlViewModel(QObject):
    """
    Manages state and logic for curve selection, profiles, and startup settings.
    Interacts with AppServices.
    """
    # --- Signals to notify View ---
    active_curve_type_updated = Signal(str)
    profile_list_updated = Signal(list, str)
    active_profile_updated = Signal(str)
    start_on_boot_status_updated = Signal(bool)
    panel_enabled_updated = Signal(bool)
    profile_renamed_locally = Signal(str, str)

    # --- Signals to request actions (some handled by AppRunner, some by AppServices) ---
    profile_to_activate_signal = Signal(str)
    profile_to_save_signal = Signal(str)
    profile_to_rename_signal = Signal(str, str)
    start_on_boot_to_apply_signal = Signal(bool)
    curve_to_reset_signal = Signal(str) # Emits 'cpu' or 'gpu'

    def __init__(self, app_services: 'AppServices', parent: Optional[QObject] = None):
        super().__init__(parent)
        self.app_services = app_services

        self._active_curve_type: str = "cpu"
        self._profile_names: List[str] = []
        self._active_profile_name: Optional[str] = None
        self._is_start_on_boot_enabled: bool = False
        self._is_panel_enabled: bool = True

    # --- Getters for View ---
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

    # --- Slots for View to call ---
    @Slot(str)
    def set_active_curve_type(self, curve_type: str):
        """Called by View when user selects CPU or GPU curve."""
        if curve_type in ["cpu", "gpu"] and self._active_curve_type != curve_type:
            self._active_curve_type = curve_type
            self.active_curve_type_updated.emit(self._active_curve_type)

    @Slot(str)
    def activate_profile(self, profile_name: str):
        """Called by View. Directly calls the service to activate a profile."""
        if profile_name in self._profile_names and self._active_profile_name != profile_name:
            self.app_services.activate_profile(profile_name)

    @Slot(str)
    def request_save_profile(self, profile_name: str):
        """Called by View to request saving settings to a profile."""
        self.profile_to_save_signal.emit(profile_name)

    @Slot(str, str)
    def request_rename_profile(self, old_name: str, new_name: str):
        """Called by View to request renaming a profile."""
        if old_name in self._profile_names and new_name and old_name != new_name:
            self.profile_to_rename_signal.emit(old_name, new_name)

    @Slot(bool)
    def set_start_on_boot(self, enabled: bool):
        """Called by View to request a change to the 'Start on Boot' setting."""
        if self._is_start_on_boot_enabled != enabled:
            self.start_on_boot_to_apply_signal.emit(enabled)

    @Slot()
    def reset_active_curve(self):
        """Called by View to request resetting the currently active curve."""
        self.curve_to_reset_signal.emit(self._active_curve_type)

    @Slot(str, object)
    def handle_curve_change(self, curve_type: str, data: list):
        """
        Called by the View (via MainWindow) when the user modifies a curve.
        This method forwards the change to the service layer.
        """
        self.app_services.set_curve_data(curve_type, data)

    # --- Slots for AppServices/AppRunner to call ---
    @Slot(list, str)
    def update_profile_list_and_active(self, profile_names: List[str], active_profile_name: str):
        """Called by services to update the entire profile list and active profile."""
        list_changed = self._profile_names != profile_names
        active_changed = self._active_profile_name != active_profile_name

        if list_changed:
            self._profile_names = profile_names
        if active_changed:
            self._active_profile_name = active_profile_name

        if list_changed or active_changed:
            self.profile_list_updated.emit(self._profile_names, self._active_profile_name or "")
        
        if active_changed and self._active_profile_name:
            self.active_profile_updated.emit(self._active_profile_name)

    @Slot(bool)
    def update_start_on_boot_status(self, enabled: bool):
        """Called by services with the current startup task registration status."""
        if self._is_start_on_boot_enabled != enabled:
            self._is_start_on_boot_enabled = enabled
            self.start_on_boot_status_updated.emit(self._is_start_on_boot_enabled)

    @Slot(bool)
    def set_panel_enabled(self, enabled: bool):
        """Called to globally enable/disable controls."""
        if self._is_panel_enabled != enabled:
            self._is_panel_enabled = enabled
            self.panel_enabled_updated.emit(self._is_panel_enabled)

    @Slot(dict)
    def apply_profile_settings(self, settings: 'ProfileSettings'):
        """
        This ViewModel doesn't hold profile-specific data itself, but it reflects
        the *name* of the active profile. This is handled by `update_profile_list_and_active`.
        """
        pass

    # get_current_settings_for_profile removed. AppServices is now the source of truth.