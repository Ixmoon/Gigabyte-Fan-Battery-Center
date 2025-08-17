import math
import sys
from typing import Optional, Dict, Any

from .wmi_interface import WMIInterface
from config.settings import (
    MIN_FAN_PERCENT, MAX_FAN_PERCENT, INIT_APPLIED_PERCENTAGE,
    FAN_MODE_BIOS, FAN_MODE_AUTO, FAN_MODE_CUSTOM, FAN_MODE_UNKNOWN
)

# --- Fan Control Constants ---
MIN_EFFECTIVE_FAN_PERCENT_MANUAL = 10

# --- Battery Control Constants ---
# Conversion map from abstract policy names to hardware-specific integer codes.
# This logic is now properly encapsulated and hidden from the rest of the application.
BATTERY_POLICY_CODES: Dict[str, int] = {
    "bios": 0,
    "custom": 4,
}
# Create a reverse map for converting integer codes back to string names.
BATTERY_CODE_POLICIES: Dict[int, str] = {v: k for k, v in BATTERY_POLICY_CODES.items()}

class BatteryManager:
    """
    Manages all direct interactions with the battery hardware via WMI.
    This class provides a high-level abstraction for battery operations,
    hiding the underlying implementation details (e.g., hardware codes).
    """

    def __init__(self, wmi_interface: WMIInterface):
        """
        Initializes the BatteryManager.

        Args:
            wmi_interface: An instance of the WMIInterface for hardware communication.
        """
        self.wmi = wmi_interface

    def set_policy(self, policy_name: str) -> bool:
        """
        Sets the battery charge policy.

        Args:
            policy_name: The desired policy, e.g., "bios" or "custom".

        Returns:
            True if the policy was set successfully, False otherwise.
        """
        policy_code = BATTERY_POLICY_CODES.get(policy_name)
        if policy_code is None:
            # Invalid policy name provided
            return False
        return self.wmi.set_battery_charge_policy(policy_code)

    def set_charge_threshold(self, threshold: int) -> bool:
        """
        Sets the custom battery charge threshold.

        Args:
            threshold: The charge limit, e.g., 80 for 80%.

        Returns:
            True if the threshold was set successfully, False otherwise.
        """
        return self.wmi.set_battery_charge_threshold(threshold)

    def get_status(self) -> Optional[Dict[str, Any]]:
        """
        Retrieves the current battery status from the hardware and translates it
        into an application-friendly format.

        Returns:
            A dictionary with status information (e.g., 'charge_policy': "bios",
            'charge_threshold': 80) or None if the query fails.
        """
        try:
            policy_code = self.wmi.get_battery_charge_policy()
            threshold = self.wmi.get_battery_charge_threshold()

            status = {
                'charge_policy': BATTERY_CODE_POLICIES.get(policy_code, "err"),
                'charge_threshold': threshold
            }
            return status
        except Exception as e:
            print(f"Failed to get battery status: {e}", file=sys.stderr)
            return None


class FanManager:
    """Manages all direct fan control operations via WMI."""

    def __init__(self, wmi_interface: WMIInterface):
        """
        Initializes the FanManager.

        Args:
            wmi_interface: An instance of WMIInterface for hardware communication.
        """
        self.wmi = wmi_interface
        self._current_mode: str = FAN_MODE_UNKNOWN
        self._applied_percentage: int = INIT_APPLIED_PERCENTAGE

    @property
    def current_mode(self) -> str:
        """Returns the last requested fan mode ('bios', 'auto', or 'custom')."""
        return self._current_mode

    @property
    def applied_percentage(self) -> int:
        """Returns the last successfully applied fan speed percentage sent to WMI."""
        return self._applied_percentage

    def _percent_to_raw(self, percent: int) -> float:
        """Converts fan speed percentage to the raw WMI value (0-229)."""
        percent = max(MIN_FAN_PERCENT, min(MAX_FAN_PERCENT, percent))
        raw_value = math.ceil((percent / 100.0) * 229.0)
        return float(raw_value)

    def _get_effective_custom_percentage(self, requested_percentage: int) -> int:
        """Applies the minimum threshold rule (below 10% becomes 0%) for custom mode."""
        requested_percentage = max(MIN_FAN_PERCENT, min(MAX_FAN_PERCENT, requested_percentage))
        if 0 < requested_percentage < MIN_EFFECTIVE_FAN_PERCENT_MANUAL:
            return 0
        else:
            return requested_percentage

    def set_mode_custom(self, percentage: int) -> bool:
        """
        Sets the fan mode to custom (custom speed) and applies the specified speed percentage.
        Speeds below 10% (but > 0) are treated as 0% for custom setting.
        """
        effective_percentage = self._get_effective_custom_percentage(percentage)
        raw_speed = self._percent_to_raw(effective_percentage)

        if not self.wmi.configure_custom_fan_control():
            print("Error: Failed to configure WMI for custom fan control.", file=sys.stderr)
            self._current_mode = FAN_MODE_UNKNOWN
            self._applied_percentage = INIT_APPLIED_PERCENTAGE
            return False

        if self.wmi.set_fan_speed_raw(raw_speed):
            self._current_mode = FAN_MODE_CUSTOM
            self._applied_percentage = effective_percentage
            return True
        else:
            print(f"Error: Failed to set custom fan speed to {percentage}% (Effective: {effective_percentage}%, Raw: {raw_speed}).", file=sys.stderr)
            self._current_mode = FAN_MODE_UNKNOWN
            self._applied_percentage = INIT_APPLIED_PERCENTAGE
            return False

    def set_mode_auto(self) -> bool:
        """
        Sets the fan mode to 'auto' for application-driven control.
        This ensures WMI is ready for the application to send speed commands.
        """
        if self.wmi.configure_custom_fan_control():
            self._current_mode = FAN_MODE_AUTO
            self._applied_percentage = INIT_APPLIED_PERCENTAGE
            return True
        else:
            print("Error: Failed to configure WMI for app-controlled auto mode.", file=sys.stderr)
            self._current_mode = FAN_MODE_UNKNOWN
            self._applied_percentage = INIT_APPLIED_PERCENTAGE
            return False

    def set_mode_bios(self) -> bool:
        """
        Sets the fan mode to 'bios', returning control to the hardware.
        """
        if self.wmi.configure_bios_fan_control():
            self._current_mode = FAN_MODE_BIOS
            self._applied_percentage = INIT_APPLIED_PERCENTAGE # No speed applied by us
            return True
        else:
            print("Error: Failed to configure WMI for bios/hardware fan mode.", file=sys.stderr)
            self._current_mode = FAN_MODE_UNKNOWN
            self._applied_percentage = INIT_APPLIED_PERCENTAGE
            return False

    def apply_speed_percent(self, percentage: int) -> bool:
        """
        Applies a fan speed percentage. Used by the auto-temperature controller.
        Does NOT apply the "below 10% is 0%" rule.
        """
        percentage_clamped = max(MIN_FAN_PERCENT, min(MAX_FAN_PERCENT, percentage))
        raw_speed = self._percent_to_raw(percentage_clamped)

        if self.wmi.set_fan_speed_raw(raw_speed):
            self._applied_percentage = percentage_clamped
            return True
        else:
            print(f"Error: Failed to apply fan speed {percentage_clamped}% (Raw: {raw_speed}) during auto-logic.", file=sys.stderr)
            return False
