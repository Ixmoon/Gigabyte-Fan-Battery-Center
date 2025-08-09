# File: 6 core/fan_controller.py (Corrected)
# core/fan_controller.py
# -*- coding: utf-8 -*-
"""
Controls the system fans via the WMI interface.
Handles setting fan mode (auto/fixed) and applying speeds.
Includes logic to treat speeds below 10% as 0% ONLY for manual mode.
"""

import math
import sys

from .wmi_interface import WMIInterface
from config.settings import (
    MIN_FAN_PERCENT, MAX_FAN_PERCENT, INIT_APPLIED_PERCENTAGE,
    FAN_MODE_AUTO, FAN_MODE_FIXED, FAN_MODE_UNKNOWN, FAN_MODE_AUTO_EQUIVALENT_SPEED
)

# --- Define the minimum threshold for manual mode ---
MIN_EFFECTIVE_FAN_PERCENT_MANUAL = 10
# --- END ---

class FanController:
    """Manages fan control operations."""

    def __init__(self, wmi_interface: WMIInterface):
        """
        Initializes the FanController.

        Args:
            wmi_interface: An instance of WMIInterface for hardware communication.
        """
        self._wmi = wmi_interface
        self._current_mode: str = FAN_MODE_UNKNOWN
        # _applied_percentage stores the last percentage value successfully *sent* to WMI
        self._applied_percentage: int = INIT_APPLIED_PERCENTAGE

    @property
    def current_mode(self) -> str:
        """Returns the last requested fan mode ('auto' or 'fixed')."""
        return self._current_mode

    @property
    def applied_percentage(self) -> int:
        """Returns the last successfully applied fan speed percentage sent to WMI."""
        return self._applied_percentage

    def _percent_to_raw(self, percent: int) -> float:
        """Converts fan speed percentage to the raw WMI value (0-229)."""
        # Clamp here ensures input to calculation is valid
        percent = max(MIN_FAN_PERCENT, min(MAX_FAN_PERCENT, percent))
        # Use float for calculation and return, as WMI methods expect float
        raw_value = math.ceil((percent / 100.0) * 229.0)
        return float(raw_value)

    def _get_effective_manual_percentage(self, requested_percentage: int) -> int:
        """Applies the minimum threshold rule (below 10% becomes 0%) for manual mode."""
        requested_percentage = max(MIN_FAN_PERCENT, min(MAX_FAN_PERCENT, requested_percentage))
        if 0 < requested_percentage < MIN_EFFECTIVE_FAN_PERCENT_MANUAL:
            return 0
        else:
            return requested_percentage

    def set_mode_fixed(self, percentage: int) -> bool:
        """
        Sets the fan mode to fixed and applies the specified speed percentage.
        Speeds below 10% (but > 0) are treated as 0% for manual setting.

        Args:
            percentage: The desired fan speed percentage (0-100).

        Returns:
            True if the mode and speed were set successfully, False otherwise.
        """
        # --- MODIFICATION: Apply threshold rule ONLY for manual mode setting ---
        effective_percentage = self._get_effective_manual_percentage(percentage)
        # --- END MODIFICATION ---

        raw_speed = self._percent_to_raw(effective_percentage)

        # 1. Ensure WMI is configured for manual control
        if not self._wmi.configure_manual_fan_control():
            print("Error: Failed to configure WMI for manual fan control.", file=sys.stderr)
            self._current_mode = FAN_MODE_UNKNOWN
            self._applied_percentage = INIT_APPLIED_PERCENTAGE
            return False

        # 2. Set the desired speed
        if self._wmi.set_fan_speed_raw(raw_speed):
            self._current_mode = FAN_MODE_FIXED
            # Store the effective percentage that was actually sent
            self._applied_percentage = effective_percentage
            return True
        else:
            # Use original requested percentage in error message for clarity
            print(f"Error: Failed to set fixed fan speed to {percentage}% (Effective: {effective_percentage}%, Raw: {raw_speed}).", file=sys.stderr)
            self._current_mode = FAN_MODE_UNKNOWN # Revert state on failure
            self._applied_percentage = INIT_APPLIED_PERCENTAGE
            return False

    def set_mode_auto(self) -> bool:
        """
        Sets the fan mode back to automatic (BIOS/EC control).

        Note: This implementation assumes setting a low fixed speed effectively
              yields control back, as there isn't a direct "SetAuto" WMI call
              that reliably works across all Gigabyte models for *both* fans
              simultaneously after manual override. Setting 0% is a common way
              to let the EC take over again.

        Returns:
            True if the operation likely succeeded, False otherwise.
        """
        # Use set_mode_fixed with the defined equivalent speed for auto mode.
        if self.set_mode_fixed(FAN_MODE_AUTO_EQUIVALENT_SPEED):
             self._current_mode = FAN_MODE_AUTO # Logically, we requested auto mode
             # _applied_percentage is already set by set_mode_fixed()
             return True
        else:
             print("Error: Failed to set fans to 0% to attempt enabling auto mode.", file=sys.stderr)
             self._current_mode = FAN_MODE_UNKNOWN
             self._applied_percentage = INIT_APPLIED_PERCENTAGE
             return False

    def apply_speed_percent(self, percentage: int) -> bool:
        """
        Applies a fan speed percentage. Used internally by the auto-mode logic.
        Does NOT apply the "below 10% is 0%" rule here.

        Args:
            percentage: The desired fan speed percentage (0-100).

        Returns:
            True if the speed was applied successfully, False otherwise.
        """
        # Clamp the requested percentage to valid range 0-100
        percentage_clamped = max(MIN_FAN_PERCENT, min(MAX_FAN_PERCENT, percentage))

        # --- MODIFICATION: Removed the effective percentage calculation here ---
        # effective_percentage = self._get_effective_percentage(percentage) # NO LONGER NEEDED HERE
        # --- END MODIFICATION ---

        raw_speed = self._percent_to_raw(percentage_clamped)

        # We assume configure_manual_fan_control() was called when switching to app-managed auto mode.
        if self._wmi.set_fan_speed_raw(raw_speed):
            # Update applied percentage with the value actually sent to WMI
            self._applied_percentage = percentage_clamped
            return True
        else:
            # Don't change _current_mode here, just report failure
            print(f"Error: Failed to apply fan speed {percentage_clamped}% (Raw: {raw_speed}) during auto-logic.", file=sys.stderr)
            # Optionally reset applied percentage on error? Depends on desired behavior.
            # self._applied_percentage = INIT_APPLIED_PERCENTAGE
            return False
