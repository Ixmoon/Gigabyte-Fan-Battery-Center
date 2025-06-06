# viewmodels/battery_control_viewmodel.py
# -*- coding: utf-8 -*-
"""
ViewModel for BatteryControlPanel.
"""
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

from typing import Optional, TYPE_CHECKING
if TYPE_CHECKING:
    from run import AppRunner

class BatteryControlViewModel(QObject):
    """
    Manages the state and logic for battery control.
    Communicates changes to AppRunner and updates BatteryControlPanel via signals.
    """
    # Signals to notify BatteryControlPanel (View) of state changes
    charge_policy_updated = pyqtSignal(str) # 'standard' or 'custom'
    charge_threshold_updated = pyqtSignal(int) # current threshold for display
    applied_charge_threshold_updated = pyqtSignal(int) # actual applied threshold from status
    panel_enabled_changed = pyqtSignal(bool) # To enable/disable the panel
    charge_limit_control_enabled_updated = pyqtSignal(bool) # True if custom policy, False otherwise
    threshold_slider_lock_updated = pyqtSignal(bool) # True to lock slider, False to unlock

    def __init__(self, app_runner: 'AppRunner', parent: Optional[QObject] = None):
        super().__init__(parent)
        self._app_runner = app_runner

        self._current_charge_policy: str = "standard" # Default
        self._current_charge_threshold: int = 80 # Default for slider position
        self._applied_charge_threshold: int = 0 # Actual threshold from hardware status
        self._is_panel_enabled: bool = True
        self._is_threshold_applying: bool = False # State for locking threshold slider

    # --- Getters for View ---
    def get_current_charge_policy(self) -> str:
        return self._current_charge_policy

    def get_current_charge_threshold(self) -> int:
        return self._current_charge_threshold
        
    def get_applied_charge_threshold(self) -> int:
        return self._applied_charge_threshold

    def is_panel_enabled(self) -> bool:
        return self._is_panel_enabled

    # --- Slots for BatteryControlPanel (View) to call ---
    @pyqtSlot(str)
    def set_charge_policy(self, policy: str):
        """Called by BatteryControlPanel when user changes charge policy."""
        if policy not in ["standard", "custom"]:
            return
        if self._current_charge_policy != policy:
            self._current_charge_policy = policy
            # Communicate change to AppRunner by calling its hardware-specific method
            self._app_runner.set_charge_policy_for_hardware(
                self._current_charge_policy,
                self._current_charge_threshold if self._current_charge_policy == "custom" else None
            )
            self.charge_policy_updated.emit(self._current_charge_policy)
            self.charge_limit_control_enabled_updated.emit(self._current_charge_policy == "custom")
            # No need to explicitly call set_charge_threshold here if policy becomes "custom",
            # as set_charge_policy_for_hardware in AppRunner will handle applying the current threshold.

    @pyqtSlot(int)
    def set_charge_threshold(self, threshold: int):
        """Called by BatteryControlPanel when user changes charge threshold slider."""
        if self._is_threshold_applying:
            return # Ignore if already applying

        threshold = max(0, min(100, threshold)) # Clamp value
        
        # self._current_charge_threshold = threshold # Update desired value
        # self.charge_threshold_updated.emit(self._current_charge_threshold) # Update UI slider position

        if self._current_charge_policy == "custom":
            self._is_threshold_applying = True
            self.threshold_slider_lock_updated.emit(False) # Disable slider (lock)
            self._app_runner.set_charge_threshold_for_hardware(threshold)
        else:
            # If not in custom mode, just update the potential threshold value
            if self._current_charge_threshold != threshold:
                self._current_charge_threshold = threshold
                self.charge_threshold_updated.emit(self._current_charge_threshold)


    @pyqtSlot(int)
    def confirm_charge_threshold_applied(self, applied_threshold: int):
        """Called by AppRunner after charge threshold has been confirmed by hardware."""
        self._current_charge_threshold = applied_threshold
        self._applied_charge_threshold = applied_threshold
        
        self.charge_threshold_updated.emit(self._current_charge_threshold)
        self.applied_charge_threshold_updated.emit(self._applied_charge_threshold)
        
        self._is_threshold_applying = False
        self.threshold_slider_lock_updated.emit(True) # Re-enable slider (unlock)

    # --- Slots for AppRunner (Model/Controller) to call ---
    @pyqtSlot(str)
    def update_charge_policy_from_status(self, policy: Optional[str]):
        """Called by AppRunner with current charge policy from hardware/status."""
        # Handle cases where policy might be None from status if unknown
        effective_policy = policy if policy in ["standard", "custom"] else "standard"
        if self._current_charge_policy != effective_policy:
            self._current_charge_policy = effective_policy
            self.charge_policy_updated.emit(self._current_charge_policy)
            self.charge_limit_control_enabled_updated.emit(self._current_charge_policy == "custom")

    @pyqtSlot(int)
    def update_applied_charge_threshold_from_status(self, threshold: int):
        """Called by AppRunner with current applied charge threshold from hardware/status."""
        if self._applied_charge_threshold != threshold:
            self._applied_charge_threshold = threshold
            self.applied_charge_threshold_updated.emit(self._applied_charge_threshold)
            # Also update the _current_charge_threshold if in custom mode
            if self._current_charge_policy == "custom" and self._current_charge_threshold != threshold:
                self._current_charge_threshold = threshold
                self.charge_threshold_updated.emit(self._current_charge_threshold)

    @pyqtSlot(bool)
    def set_panel_enabled(self, enabled: bool):
        """Called by AppRunner/MainWindow to globally enable/disable controls."""
        if self._is_panel_enabled != enabled:
            self._is_panel_enabled = enabled
            self.panel_enabled_changed.emit(self._is_panel_enabled)

    def apply_profile_settings(self, settings: dict):
        """Applies battery-related settings from a profile."""
        new_policy = settings.get("charge_policy", self._current_charge_policy)
        new_threshold = settings.get("charge_threshold", self._current_charge_threshold)

        policy_changed = False
        if self._current_charge_policy != new_policy:
            self._current_charge_policy = new_policy
            policy_changed = True

        threshold_changed = False
        if self._current_charge_threshold != new_threshold:
            self._current_charge_threshold = new_threshold
            threshold_changed = True
            
        if policy_changed:
            self.charge_policy_updated.emit(self._current_charge_policy)
            self.charge_limit_control_enabled_updated.emit(self._current_charge_policy == "custom")
        
        if threshold_changed: # This updates the slider position
            self.charge_threshold_updated.emit(self._current_charge_threshold)
        
        # AppRunner will handle applying the full profile to hardware.

    def get_current_settings_for_profile(self) -> dict:
        """Returns current battery settings for saving to a profile."""
        return {
            "charge_policy": self._current_charge_policy,
            "charge_threshold": self._current_charge_threshold
        }