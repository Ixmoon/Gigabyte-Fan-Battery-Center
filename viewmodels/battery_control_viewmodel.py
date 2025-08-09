# viewmodels/battery_control_viewmodel.py
# -*- coding: utf-8 -*-
"""
ViewModel for BatteryControlPanel.
"""
from gui.qt import QObject, Signal, Slot
from .base_viewmodel import BaseViewModel
from config.settings import CHARGE_POLICY_STANDARD_STR, CHARGE_POLICY_CUSTOM_STR

from typing import Optional, TYPE_CHECKING
if TYPE_CHECKING:
    from core.app_services import AppServices

class BatteryControlViewModel(BaseViewModel):
    """
    Manages the state and logic for battery control.
    Communicates with AppServices and updates BatteryControlPanel via signals.
    """
    # --- Signals to notify View ---
    charge_policy_updated = Signal(str)
    charge_threshold_updated = Signal(int)
    applied_charge_threshold_updated = Signal(int)
    charge_limit_control_enabled_updated = Signal(bool)
    threshold_slider_lock_updated = Signal(bool)

    # --- Signals to AppServices ---
    charge_policy_set_requested = Signal(str, int)
    charge_threshold_set_requested = Signal(int)

    def __init__(self, app_services: 'AppServices', parent: Optional[QObject] = None):
        super().__init__(parent)
        self.app_services = app_services

        self._current_charge_policy: str = CHARGE_POLICY_STANDARD_STR
        self._current_charge_threshold: int = 80
        self._applied_charge_threshold: int = 0
        self._is_threshold_applying: bool = False

    # --- Getters for View ---
    def get_current_charge_policy(self) -> str:
        return self._current_charge_policy

    def get_current_charge_threshold(self) -> int:
        return self._current_charge_threshold

    def get_applied_charge_threshold(self) -> int:
        return self._applied_charge_threshold

    # --- Slots for View to call ---
    @Slot(str)
    def set_charge_policy(self, policy: str):
        """Called by View. Emits a signal to request a policy change from AppServices."""
        if policy not in [CHARGE_POLICY_STANDARD_STR, CHARGE_POLICY_CUSTOM_STR] or self._current_charge_policy == policy:
            return
        # Optimistically update UI
        self._current_charge_policy = policy
        self.charge_policy_updated.emit(policy)
        self.charge_limit_control_enabled_updated.emit(policy == CHARGE_POLICY_CUSTOM_STR)
        # Request change from the service layer
        self.charge_policy_set_requested.emit(policy, self._current_charge_threshold)

    @Slot(int)
    def set_charge_threshold(self, threshold: int):
        """Called by View. Emits a signal to request a threshold change from AppServices."""
        if self._is_threshold_applying:
            return

        threshold = max(0, min(100, threshold))
        self._current_charge_threshold = threshold
        self.charge_threshold_updated.emit(threshold)

        if self._current_charge_policy == CHARGE_POLICY_CUSTOM_STR:
            self._is_threshold_applying = True
            self.threshold_slider_lock_updated.emit(False) # Lock slider
            self.charge_threshold_set_requested.emit(threshold)

    # --- Slots for AppServices to call ---
    @Slot(str, int)
    def update_from_service(self, policy: Optional[str], threshold: int):
        """Called by AppServices with the current, confirmed hardware state."""
        effective_policy = policy if policy in [CHARGE_POLICY_STANDARD_STR, CHARGE_POLICY_CUSTOM_STR] else CHARGE_POLICY_STANDARD_STR

        if self._current_charge_policy != effective_policy:
            self._current_charge_policy = effective_policy
            self.charge_policy_updated.emit(effective_policy)
            self.charge_limit_control_enabled_updated.emit(effective_policy == CHARGE_POLICY_CUSTOM_STR)

        if self._applied_charge_threshold != threshold:
            self._applied_charge_threshold = threshold
            self.applied_charge_threshold_updated.emit(threshold)

        if effective_policy == CHARGE_POLICY_CUSTOM_STR and self._current_charge_threshold != threshold:
            self._current_charge_threshold = threshold
            self.charge_threshold_updated.emit(threshold)

        if self._is_threshold_applying:
            self._is_threshold_applying = False
            self.threshold_slider_lock_updated.emit(True) # Unlock slider

    @Slot(dict)
    def apply_profile_settings(self, settings: dict):
        """Applies battery-related settings from a profile provided by AppServices."""
        new_policy = settings.get("charge_policy", self._current_charge_policy)
        new_threshold = settings.get("charge_threshold", self._current_charge_threshold)

        if self._current_charge_policy != new_policy:
            self._current_charge_policy = new_policy
            self.charge_policy_updated.emit(new_policy)
            self.charge_limit_control_enabled_updated.emit(new_policy == "custom")

        if self._current_charge_threshold != new_threshold:
            self._current_charge_threshold = new_threshold
            self.charge_threshold_updated.emit(new_threshold)

    # get_current_settings_for_profile removed. AppServices is now the source of truth.