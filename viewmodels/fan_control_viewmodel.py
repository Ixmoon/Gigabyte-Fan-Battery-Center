# viewmodels/fan_control_viewmodel.py
# -*- coding: utf-8 -*-
"""
ViewModel for FanControlPanel.
"""
from gui.qt import QObject, Signal, Slot
from .base_viewmodel import BaseViewModel
from config.settings import FAN_MODE_AUTO, FAN_MODE_FIXED

from typing import Optional, TYPE_CHECKING
if TYPE_CHECKING:
    from core.app_services import AppServices

class FanControlViewModel(BaseViewModel):
    """
    Manages the state and logic for fan control.
    Communicates with AppServices and updates FanControlPanel via signals.
    """
    # --- Signals to notify FanControlPanel (View) ---
    fan_mode_updated = Signal(str)
    fixed_speed_updated = Signal(int)
    applied_fixed_speed_updated = Signal(int)
    fixed_speed_control_enabled_updated = Signal(bool)

    # --- Signals to AppServices ---
    fan_mode_set_requested = Signal(str, int)
    fixed_speed_set_requested = Signal(int)

    def __init__(self, app_services: 'AppServices', parent: Optional[QObject] = None):
        super().__init__(parent)
        self.app_services = app_services

        self._current_fan_mode: str = FAN_MODE_AUTO
        self._current_fixed_speed: int = 50
        self._applied_fixed_speed: int = 0
        self._is_fixed_speed_applying: bool = False

    # --- Getters for View ---
    def get_current_fan_mode(self) -> str:
        return self._current_fan_mode

    def get_current_fixed_speed(self) -> int:
        return self._current_fixed_speed

    def get_applied_fixed_speed(self) -> int:
        return self._applied_fixed_speed

    # --- Slots for View to call ---
    @Slot(str)
    def set_fan_mode(self, mode: str):
        """Called by View. Emits a signal to request a fan mode change from AppServices."""
        if mode not in [FAN_MODE_AUTO, FAN_MODE_FIXED] or self._current_fan_mode == mode:
            return
        # Optimistically update UI state
        self._current_fan_mode = mode
        self.fan_mode_updated.emit(mode)
        # Request change from the service layer
        self.fan_mode_set_requested.emit(mode, self._current_fixed_speed)

    @Slot(int)
    def set_fixed_speed(self, speed: int):
        """Called by View. Emits a signal to request a fixed speed change from AppServices."""
        if self._is_fixed_speed_applying:
            return

        speed = max(0, min(100, speed))
        self._current_fixed_speed = speed # Update desired speed
        self.fixed_speed_updated.emit(speed) # Update slider immediately

        if self._current_fan_mode == FAN_MODE_FIXED:
            self._is_fixed_speed_applying = True
            self.fixed_speed_control_enabled_updated.emit(False)
            self.fixed_speed_set_requested.emit(speed)

    # --- Slots for AppServices to call ---
    @Slot(str, int)
    def update_from_service(self, mode: str, applied_speed: int):
        """Called by AppServices with the current, confirmed hardware state."""
        if self._current_fan_mode != mode:
            self._current_fan_mode = mode
            self.fan_mode_updated.emit(mode)

        if self._applied_fixed_speed != applied_speed:
            self._applied_fixed_speed = applied_speed
            self.applied_fixed_speed_updated.emit(applied_speed)

        # If in fixed mode, ensure the slider position matches the actual applied speed
        if mode == FAN_MODE_FIXED and self._current_fixed_speed != applied_speed:
            self._current_fixed_speed = applied_speed
            self.fixed_speed_updated.emit(applied_speed)

        # Re-enable controls now that the update is confirmed
        if self._is_fixed_speed_applying:
            self._is_fixed_speed_applying = False
            self.fixed_speed_control_enabled_updated.emit(True)

    @Slot(dict)
    def apply_profile_settings(self, settings: dict):
        """Applies fan-related settings from a profile provided by AppServices."""
        new_mode = settings.get("fan_mode", self._current_fan_mode)
        new_speed = settings.get("fixed_fan_speed", self._current_fixed_speed)

        if self._current_fan_mode != new_mode:
            self._current_fan_mode = new_mode
            self.fan_mode_updated.emit(new_mode)

        if self._current_fixed_speed != new_speed:
            self._current_fixed_speed = new_speed
            self.fixed_speed_updated.emit(new_speed)

    # get_current_settings_for_profile removed. AppServices is now the source of truth.