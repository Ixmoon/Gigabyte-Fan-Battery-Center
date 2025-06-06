# core/battery_controller.py
# -*- coding: utf-8 -*-
"""
Controls the system battery charging policy and threshold via the WMI interface.
"""

import sys
from typing import Optional, Tuple

from .wmi_interface import WMIInterface
from config.settings import (
    CHARGE_POLICY_STANDARD, CHARGE_POLICY_CUSTOM,
    CHARGE_POLICY_READ_ERROR_VALUE, CHARGE_THRESHOLD_READ_ERROR_VALUE,
    MIN_CHARGE_PERCENT, MAX_CHARGE_PERCENT
)

class BatteryController:
    """Manages battery control operations."""

    def __init__(self, wmi_interface: WMIInterface):
        """
        Initializes the BatteryController.

        Args:
            wmi_interface: An instance of WMIInterface for hardware communication.
        """
        self._wmi = wmi_interface
        self._current_policy: Optional[str] = None # "standard", "custom", or None if unknown
        self._current_threshold: int = CHARGE_THRESHOLD_READ_ERROR_VALUE

    @property
    def current_policy(self) -> Optional[str]:
        """Returns the last known battery policy ('standard', 'custom', or None)."""
        return self._current_policy

    @property
    def current_threshold(self) -> int:
        """Returns the last known battery charge threshold percentage."""
        return self._current_threshold

    def _policy_code_to_str(self, code: int) -> Optional[str]:
        """Converts WMI policy code to string representation."""
        if code == CHARGE_POLICY_STANDARD:
            return "standard"
        elif code == CHARGE_POLICY_CUSTOM:
            return "custom"
        else:
            return None # Unknown code

    def _policy_str_to_code(self, policy: str) -> Optional[int]:
        """Converts string representation to WMI policy code."""
        if policy == "standard":
            return CHARGE_POLICY_STANDARD
        elif policy == "custom":
            return CHARGE_POLICY_CUSTOM
        else:
            return None

    def refresh_status(self) -> Tuple[Optional[str], int]:
        """
        Reads the current battery policy and threshold from WMI and updates internal state.

        Returns:
            A tuple containing the current policy string ('standard', 'custom', or None)
            and the current threshold percentage (or error value).
        """
        policy_code = self._wmi.get_battery_charge_policy()
        threshold = self._wmi.get_battery_charge_threshold()

        self._current_policy = self._policy_code_to_str(policy_code)
        self._current_threshold = threshold if threshold != CHARGE_THRESHOLD_READ_ERROR_VALUE else self._current_threshold

        # Clamp threshold read from WMI just in case it returns out-of-range values
        if self._current_threshold != CHARGE_THRESHOLD_READ_ERROR_VALUE:
             self._current_threshold = max(MIN_CHARGE_PERCENT, min(MAX_CHARGE_PERCENT, self._current_threshold))

        return self._current_policy, self._current_threshold

    def set_policy(self, policy: str) -> bool:
        """
        Sets the battery charging policy.

        Args:
            policy: The desired policy ("standard" or "custom").

        Returns:
            True if successful, False otherwise.
        """
        policy_code = self._policy_str_to_code(policy)
        if policy_code is None:
            print(f"Error: Invalid battery policy specified: {policy}", file=sys.stderr)
            return False

        if self._wmi.set_battery_charge_policy(policy_code):
            self._current_policy = policy # Update internal state on success
            return True
        else:
            print(f"Error: Failed to set battery policy to {policy} (Code: {policy_code}).", file=sys.stderr)
            # Don't change internal state on failure
            return False

    def set_threshold(self, threshold: int) -> bool:
        """
        Sets the battery charge stop threshold percentage.
        Note: This typically only has an effect if the policy is set to "custom".

        Args:
            threshold: The desired charge limit percentage (e.g., 80).

        Returns:
            True if successful, False otherwise.
        """
        # Clamp the value before sending
        threshold = max(MIN_CHARGE_PERCENT, min(MAX_CHARGE_PERCENT, threshold))

        if self._wmi.set_battery_charge_threshold(threshold):
            self._current_threshold = threshold # Update internal state on success
            return True
        else:
            print(f"Error: Failed to set battery threshold to {threshold}%.", file=sys.stderr)
            # Don't change internal state on failure
            return False