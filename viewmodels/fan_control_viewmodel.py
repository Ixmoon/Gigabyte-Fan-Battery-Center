# viewmodels/fan_control_viewmodel.py
# -*- coding: utf-8 -*-
"""
ViewModel for FanControlPanel.
"""
from gui.qt import QObject, Signal, Slot

from typing import Optional, TYPE_CHECKING
if TYPE_CHECKING:
    from run import AppRunner # To interact with core logic
    # from gui.FanControlPanel import FanControlPanel # To update UI (indirectly via signals)

class FanControlViewModel(QObject):
    """
    Manages the state and logic for fan control.
    Communicates changes to AppRunner and updates FanControlPanel via signals.
    """
    # Signals to notify FanControlPanel (View) of state changes
    fan_mode_updated = Signal(str) # 'auto' or 'fixed'
    fixed_speed_updated = Signal(int) # current speed for display
    applied_fixed_speed_updated = Signal(int) # actual applied speed from status
    panel_enabled_changed = Signal(bool) # To enable/disable the panel
    fixed_speed_control_enabled_updated = Signal(bool) # To enable/disable fixed speed slider during apply

    # Signals to AppRunner (or a future service layer) are handled by direct calls for now

    def __init__(self, app_runner: 'AppRunner', parent: Optional[QObject] = None):
        super().__init__(parent)
        self._app_runner = app_runner
        # self._view: Optional['FanControlPanel'] = None # View can connect to signals

        self._current_fan_mode: str = "auto" # Default
        self._current_fixed_speed: int = 50 # Default for slider position
        self._applied_fixed_speed: int = 0 # Actual speed from hardware status
        self._is_panel_enabled: bool = True
        self._is_fixed_speed_applying: bool = False # State for locking fixed speed control

    # --- Getters for View to query initial state or for direct binding (if supported) ---
    def get_current_fan_mode(self) -> str:
        return self._current_fan_mode

    def get_current_fixed_speed(self) -> int:
        return self._current_fixed_speed
    
    def get_applied_fixed_speed(self) -> int:
        return self._applied_fixed_speed

    def is_panel_enabled(self) -> bool:
        return self._is_panel_enabled

    # --- Slots for FanControlPanel (View) to call ---
    @Slot(str)
    def set_fan_mode(self, mode: str):
        """Called by FanControlPanel when user changes fan mode."""
        if mode not in ["auto", "fixed"]:
            # Log error or handle invalid mode
            return
        if self._current_fan_mode != mode:
            self._current_fan_mode = mode
            # Communicate change to AppRunner by calling its hardware-specific method
            self._app_runner.set_fan_mode_for_hardware(self._current_fan_mode, self._current_fixed_speed if self._current_fan_mode == "fixed" else None)
            self.fan_mode_updated.emit(self._current_fan_mode)
            # No need to explicitly call set_fixed_fan_speed here if mode becomes "fixed",
            # as set_fan_mode_for_hardware in AppRunner will handle applying the current fixed speed.

    @Slot(int)
    def set_fixed_speed(self, speed: int):
        """Called by FanControlPanel when user changes fixed fan speed slider."""
        if self._is_fixed_speed_applying:
            # If a speed application is already in progress, ignore this new request
            # Optionally, re-emit the current _applied_fixed_speed to snap slider back
            # self.fixed_speed_updated.emit(self._current_fixed_speed) # or self._applied_fixed_speed
            return

        speed = max(0, min(100, speed)) # Clamp value
        
        # Update internal "desired" speed immediately for responsiveness if needed,
        # but the actual application logic will handle the hardware call.
        # self._current_fixed_speed = speed # Keep this to reflect user's latest intention
        # self.fixed_speed_updated.emit(self._current_fixed_speed) # Update UI slider position

        if self._current_fan_mode == "fixed":
            self._is_fixed_speed_applying = True
            self.fixed_speed_control_enabled_updated.emit(False) # Disable slider
            # Store the speed we are trying to apply, might differ from _current_fixed_speed if user moved slider again quickly
            self._app_runner.set_fixed_fan_speed_for_hardware(speed)
        else:
            # If not in fixed mode, just update the potential fixed speed value
            if self._current_fixed_speed != speed:
                self._current_fixed_speed = speed
                self.fixed_speed_updated.emit(self._current_fixed_speed)


    @Slot(int)
    def confirm_fixed_speed_applied(self, applied_speed: int):
        """Called by AppRunner after fixed speed has been confirmed by hardware."""
        self._current_fixed_speed = applied_speed # Update to the actual applied speed
        self._applied_fixed_speed = applied_speed # Also update applied speed
        
        self.fixed_speed_updated.emit(self._current_fixed_speed) # Update slider display
        self.applied_fixed_speed_updated.emit(self._applied_fixed_speed) # Update applied speed display

        self._is_fixed_speed_applying = False
        self.fixed_speed_control_enabled_updated.emit(True) # Re-enable slider

    # --- Slots for AppRunner (Model/Controller) to call to update ViewModel state ---
    @Slot(str)
    def update_fan_mode_from_status(self, mode: str):
        """Called by AppRunner with current fan mode from hardware/status."""
        if self._current_fan_mode != mode:
            self._current_fan_mode = mode
            self.fan_mode_updated.emit(self._current_fan_mode)

    @Slot(int)
    def update_applied_fixed_speed_from_status(self, speed: int):
        """Called by AppRunner with current applied fixed fan speed from hardware/status."""
        if self._applied_fixed_speed != speed:
            self._applied_fixed_speed = speed
            self.applied_fixed_speed_updated.emit(self._applied_fixed_speed)
            # Also update the _current_fixed_speed if in fixed mode, to keep slider in sync
            # if the change originated from somewhere else (e.g. profile load)
            if self._current_fan_mode == "fixed" and self._current_fixed_speed != speed:
                self._current_fixed_speed = speed
                self.fixed_speed_updated.emit(self._current_fixed_speed)


    @Slot(bool)
    def set_panel_enabled(self, enabled: bool):
        """Called by AppRunner/MainWindow to globally enable/disable controls."""
        if self._is_panel_enabled != enabled:
            self._is_panel_enabled = enabled
            self.panel_enabled_changed.emit(self._is_panel_enabled)

    def apply_profile_settings(self, settings: dict):
        """Applies fan-related settings from a profile."""
        new_mode = settings.get("fan_mode", self._current_fan_mode)
        new_speed = settings.get("fixed_fan_speed", self._current_fixed_speed)

        # Important: Update internal state first, then emit signals if changed.
        # Avoid calling set_fan_mode or set_fixed_speed directly here if they have side effects
        # of immediately calling AppRunner, as AppRunner might be the one initiating this profile apply.
        
        mode_changed = False
        if self._current_fan_mode != new_mode:
            self._current_fan_mode = new_mode
            mode_changed = True

        speed_changed = False
        if self._current_fixed_speed != new_speed:
            self._current_fixed_speed = new_speed
            speed_changed = True
            
        if mode_changed:
            self.fan_mode_updated.emit(self._current_fan_mode)
        
        if speed_changed: # This updates the slider position
            self.fixed_speed_updated.emit(self._current_fixed_speed)
        
        # After applying profile, AppRunner will be told about the new settings
        # (e.g., AppRunner calls its own set_fan_mode, set_fixed_fan_speed based on full profile).
        # Then, status updates from AppRunner will confirm applied values.
        # Or, ViewModel could directly tell AppRunner here if that's the desired flow.
        # For now, assume AppRunner handles applying the full profile to hardware.

    def get_current_settings_for_profile(self) -> dict:
        """Returns current fan settings for saving to a profile."""
        return {
            "fan_mode": self._current_fan_mode,
            "fixed_fan_speed": self._current_fixed_speed
        }