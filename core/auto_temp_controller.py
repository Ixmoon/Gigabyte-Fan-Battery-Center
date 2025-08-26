# core/auto_temp_controller.py
# -*- coding: utf-8 -*-
"""
Contains logic for calculating target fan speeds based on temperature curves
and manages the complete auto-mode control loop, including timing,
temperature reads, and fan speed application.
"""

from typing import List, Optional, Dict, cast
import sys
import time

from gui.qt import QObject, Slot, Signal

# --- MODIFICATION: Import dependencies directly ---
from .wmi_interface import WMIInterface
from .hardware_manager import FanManager
from .interpolation import PchipInterpolator, clip, interp
from .state import ProfileState
# --- END MODIFICATION ---

# Import settings for curve validation, limits, and auto-mode defaults
from config.settings import (
    MIN_FAN_PERCENT, MAX_FAN_PERCENT,
    MIN_POINTS_FOR_INTERPOLATION,
    TEMP_READ_ERROR_VALUE, INIT_APPLIED_PERCENTAGE,
    DEFAULT_PROFILE_SETTINGS # For default auto-mode parameters
)

# Type Hinting
FanTable = List[List[int]] # List of [temp, speed] pairs

class AutoTemperatureController(QObject):
    """
    Calculates target fan speed based on temperature and fan curves,
    and manages the complete auto-mode control loop including timing,
    temperature reads, and fan speed application via injected controllers.
    """
    # Signal to broadcast fresh sensor data after an update cycle.
    # The dict will contain keys like 'cpu_temp', 'gpu_temp', etc.
    sensors_updated = Signal(dict)

    # --- MODIFIED: Add dependencies to __init__ ---
    def __init__(self, wmi_interface: WMIInterface, fan_manager: FanManager):
        super().__init__()  # Initialize QObject base class
        self._wmi = wmi_interface
        self._fan = fan_manager
    # --- END MODIFIED ---

        # Curve data and interpolators
        self._cpu_interpolator: Optional[PchipInterpolator] = None
        self._gpu_interpolator: Optional[PchipInterpolator] = None
        self._cpu_curve_data: FanTable = []
        self._gpu_curve_data: FanTable = []

        # Auto-mode settings (loaded from profile)
        self._adjustment_interval_s: float = DEFAULT_PROFILE_SETTINGS['FAN_ADJUSTMENT_INTERVAL_S']
        self._hysteresis_percent: int = DEFAULT_PROFILE_SETTINGS['FAN_HYSTERESIS_PERCENT']
        self._min_step: int = DEFAULT_PROFILE_SETTINGS['MIN_ADJUSTMENT_STEP']
        self._max_step: int = DEFAULT_PROFILE_SETTINGS['MAX_ADJUSTMENT_STEP']

        # Auto-mode internal state
        self._active_target_percentage: int = INIT_APPLIED_PERCENTAGE
        self._last_theoretical_target: int = INIT_APPLIED_PERCENTAGE
        self._current_adjustment_step_size: Optional[int] = None
        self._speed_at_target_set: int = INIT_APPLIED_PERCENTAGE

    # --- NEW: Public method to get last calculated target ---
    def get_last_theoretical_target(self) -> int:
        """Returns the last calculated theoretical target speed for display."""
        # Ensure it returns a valid percentage, even if not calculated yet
        return self._last_theoretical_target if self._last_theoretical_target != INIT_APPLIED_PERCENTAGE else 0
    # --- END NEW ---

    def update_curves(self, cpu_curve: FanTable, gpu_curve: FanTable):
        """Updates the fan curves used for interpolation."""
        self._cpu_curve_data = self._validate_and_sort(cpu_curve)
        self._gpu_curve_data = self._validate_and_sort(gpu_curve)
        self._cpu_interpolator = self._create_interpolator(self._cpu_curve_data, "CPU")
        self._gpu_interpolator = self._create_interpolator(self._gpu_curve_data, "GPU")
        self.reset_state()


    def update_auto_settings(self, profile: 'ProfileState'):
        """Updates the auto-mode control parameters from a profile."""
        # The type hint 'ProfileState' is for clarity, not enforced at runtime
        new_interval_s = profile.fan_adjustment_interval_s
        self._hysteresis_percent = profile.fan_hysteresis_percent
        self._min_step = profile.min_adjustment_step
        self._max_step = profile.max_adjustment_step
        self._min_step = max(0, self._min_step)
        self._max_step = max(self._min_step, self._max_step)

        self._adjustment_interval_s = new_interval_s
        # Reset step size when settings change
        self._current_adjustment_step_size = None


    def reset_state(self):
        """Resets internal auto-mode state variables."""
        self._active_target_percentage = INIT_APPLIED_PERCENTAGE
        self._last_theoretical_target = INIT_APPLIED_PERCENTAGE
        self._current_adjustment_step_size = None
        self._speed_at_target_set = INIT_APPLIED_PERCENTAGE


    def _validate_and_sort(self, table: FanTable) -> FanTable:
        """Sorts table by temperature and ensures basic validity."""
        if not isinstance(table, list): return []
        valid_points = [p for p in table if isinstance(p, list) and len(p) == 2 and all(isinstance(x, (int, float)) for x in p)]
        return sorted(valid_points, key=lambda x: x[0])

    def _create_interpolator(self, table: FanTable, curve_name: str) -> Optional[PchipInterpolator]:
        """Creates a PchipInterpolator from a fan table using the local implementation."""
        if len(table) < MIN_POINTS_FOR_INTERPOLATION: return None
        
        # Ensure unique temperature points for the interpolator
        unique_temps_map: Dict[float, float] = {}
        for t, s in table:
            if t not in unique_temps_map or s > unique_temps_map[t]:
                unique_temps_map[t] = s
        
        if len(unique_temps_map) < MIN_POINTS_FOR_INTERPOLATION: return None
        
        unique_temps = sorted(unique_temps_map.keys())
        unique_speeds = [unique_temps_map[t] for t in unique_temps]
        
        try:
            # Use the local, dependency-free PchipInterpolator
            return PchipInterpolator(unique_temps, unique_speeds, extrapolate=False)
        except Exception as e:
            print(f"Error creating {curve_name} PCHIP interpolator: {e}", file=sys.stderr)
            return None

    def _linear_interpolate(self, temperature: float, table: FanTable) -> float:
        """Performs simple linear interpolation as a fallback."""
        temps = [float(p[0]) for p in table]
        speeds = [float(p[1]) for p in table]
        return interp(temperature, temps, speeds)

    def _interpolate_single_curve(self, temperature: float, table: FanTable, interpolator: Optional[PchipInterpolator]) -> int:
        """
        Calculates target speed for a single curve using PCHIP interpolation
        with a robust fallback to linear interpolation.
        """
        if not table: return MIN_FAN_PERCENT
        if temperature == TEMP_READ_ERROR_VALUE: return MIN_FAN_PERCENT

        min_temp_curve, min_speed_curve = table[0]
        max_temp_curve, max_speed_curve = table[-1]

        if temperature <= min_temp_curve: return int(min_speed_curve)
        if temperature >= max_temp_curve: return int(max_speed_curve)

        interp_speed = 0.0
        if interpolator:
            try:
                interp_speed = interpolator(temperature)
            except Exception:
                interp_speed = self._linear_interpolate(temperature, table)
        else:
            interp_speed = self._linear_interpolate(temperature, table)

        # To satisfy the linter, explicitly cast the result to float.
        # In this context, with a float input, the output is always a float.
        final_speed = cast(float, interp_speed)
        clipped_speed = cast(float, clip(final_speed, MIN_FAN_PERCENT, MAX_FAN_PERCENT))
        return int(round(clipped_speed))

    def _calculate_theoretical_target(self, cpu_temp: float, gpu_temp: float) -> int:
        """Calculates the raw target speed based on temps and curves."""
        cpu_target = self._interpolate_single_curve(cpu_temp, self._cpu_curve_data, self._cpu_interpolator)
        gpu_target = self._interpolate_single_curve(gpu_temp, self._gpu_curve_data, self._gpu_interpolator)
        return max(cpu_target, gpu_target)

    def _calculate_adjustment_step_size(self, initial_delta: int) -> int:
        """Calculates step size based on initial difference."""
        if initial_delta <= 0: return 0
        step_range = self._max_step - self._min_step
        if step_range > 0:
            scale_factor = min(1.0, initial_delta / 100.0)
            calculated_step = self._min_step + (step_range * scale_factor)
            step_size = int(round(calculated_step))
        else: step_size = self._min_step
        step_size = max(self._min_step, min(self._max_step, step_size))
        return max(1, step_size)

    def _update_active_target(self, current_applied_speed: int, cpu_temp: float, gpu_temp: float) -> bool:
        """
        Calculates the theoretical target from pre-read temperatures, applies hysteresis,
        and updates the internal active target speed if necessary.

        Returns:
            bool: True if the active target was changed, False otherwise.
        """
        theoretical_target = self._calculate_theoretical_target(cpu_temp, gpu_temp)
        self._last_theoretical_target = theoretical_target

        if self._active_target_percentage == INIT_APPLIED_PERCENTAGE or \
           abs(theoretical_target - self._active_target_percentage) > self._hysteresis_percent:
            if self._active_target_percentage != theoretical_target:
                self._active_target_percentage = theoretical_target
                initial_delta = abs(self._active_target_percentage - current_applied_speed)
                self._current_adjustment_step_size = self._calculate_adjustment_step_size(initial_delta)
                self._speed_at_target_set = current_applied_speed
                return True
        return False

    def _calculate_next_speed(self, current_applied_speed: int) -> Optional[int]:
        """
        Determines the next fan speed to apply based on the active target.

        Returns:
            Optional[int]: The new speed to apply, or None if no change is needed.
        """
        target = self._active_target_percentage
        if target == INIT_APPLIED_PERCENTAGE or current_applied_speed == target:
            if self._current_adjustment_step_size is not None:
                self._current_adjustment_step_size = None
                self._speed_at_target_set = INIT_APPLIED_PERCENTAGE
            return None

        step_size = self._current_adjustment_step_size
        if step_size is None:
            initial_delta = abs(target - current_applied_speed)
            step_size = self._calculate_adjustment_step_size(initial_delta)
            self._current_adjustment_step_size = step_size

        step_size = max(1, step_size)

        next_speed = current_applied_speed
        if target > current_applied_speed:
            next_speed = min(target, current_applied_speed + step_size)
        elif target < current_applied_speed:
            next_speed = max(target, current_applied_speed - step_size)

        if next_speed == target:
            self._current_adjustment_step_size = None
            self._speed_at_target_set = INIT_APPLIED_PERCENTAGE

        return next_speed if next_speed != current_applied_speed else None

    @Slot()
    def perform_adjustment_step(self):
        """
        Internal slot called by the timer. Orchestrates the fan adjustment logic.
        """
        # Use the public property of the WMI interface
        if not self._wmi.is_running:
            return

        # --- Read only temperature data ---
        cpu_temp = self._wmi.get_cpu_temperature()
        gpu_temp = self._wmi.get_gpu_temperature()
        
        # Broadcast the fresh sensor data for the UI or other services to use
        self.sensors_updated.emit({
            'cpu_temp': cpu_temp,
            'gpu_temp': gpu_temp
        })

        current_applied_speed = self._fan.applied_percentage

        # 1. Update the active target based on current temperatures and hysteresis.
        self._update_active_target(current_applied_speed, cpu_temp, gpu_temp)

        # 2. Calculate the next speed step towards the active target.
        speed_to_apply = self._calculate_next_speed(current_applied_speed)

        # 3. Apply the new speed if a change is required.
        if speed_to_apply is not None:
            self._fan.apply_speed_percent(speed_to_apply)

