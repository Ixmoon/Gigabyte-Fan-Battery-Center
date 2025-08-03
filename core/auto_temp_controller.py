# core/auto_temp_controller.py
# -*- coding: utf-8 -*-
"""
Contains logic for calculating target fan speeds based on temperature curves
and manages the complete auto-mode control loop, including timing,
temperature reads, and fan speed application.
"""

from typing import List, Optional, Dict
import numpy as np
from scipy.interpolate import PchipInterpolator
import sys

# --- NEW: Import QTimer and dependencies ---
from PyQt6.QtCore import QObject, QTimer, pyqtSlot

# --- MODIFICATION: Import dependencies directly ---
from .wmi_interface import WMIInterface
from .fan_controller import FanController
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

# --- NEW: Inherit from QObject for timer ---
class AutoTemperatureController(QObject):
# --- END NEW ---
    """
    Calculates target fan speed based on temperature and fan curves,
    and manages the complete auto-mode control loop including timing,
    temperature reads, and fan speed application via injected controllers.
    """

    # --- MODIFIED: Add dependencies to __init__ ---
    def __init__(self, wmi_interface: WMIInterface, fan_controller: FanController):
        super().__init__() # Initialize QObject base class
        self._wmi = wmi_interface
        self._fan = fan_controller
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

        # --- NEW: Internal Timer ---
        self._adjustment_timer = QTimer(self)
        self._adjustment_timer.timeout.connect(self._perform_adjustment_step)
        # --- END NEW ---

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


    def update_auto_settings(self, profile_settings: Dict[str, any]):
        """Updates the auto-mode control parameters from a profile."""
        new_interval_s = profile_settings.get(
            "FAN_ADJUSTMENT_INTERVAL_S", DEFAULT_PROFILE_SETTINGS['FAN_ADJUSTMENT_INTERVAL_S']
        )
        self._hysteresis_percent = profile_settings.get(
            "FAN_HYSTERESIS_PERCENT", DEFAULT_PROFILE_SETTINGS['FAN_HYSTERESIS_PERCENT']
        )
        self._min_step = profile_settings.get(
            "MIN_ADJUSTMENT_STEP", DEFAULT_PROFILE_SETTINGS['MIN_ADJUSTMENT_STEP']
        )
        self._max_step = profile_settings.get(
            "MAX_ADJUSTMENT_STEP", DEFAULT_PROFILE_SETTINGS['MAX_ADJUSTMENT_STEP']
        )
        self._min_step = max(0, self._min_step)
        self._max_step = max(self._min_step, self._max_step)

        # Reconfigure timer if interval changed
        if new_interval_s != self._adjustment_interval_s:
            self._adjustment_interval_s = new_interval_s
            if self._adjustment_timer.isActive():
                self._adjustment_timer.stop()
                interval_ms = max(100, int(self._adjustment_interval_s * 1000))
                self._adjustment_timer.start(interval_ms)

        # Reset step size when settings change
        self._current_adjustment_step_size = None


    def reset_state(self):
        """Resets internal auto-mode state variables."""
        self._active_target_percentage = INIT_APPLIED_PERCENTAGE
        self._last_theoretical_target = INIT_APPLIED_PERCENTAGE
        self._current_adjustment_step_size = None
        self._speed_at_target_set = INIT_APPLIED_PERCENTAGE


    # --- NEW: Start/Stop methods for the auto control loop ---
    def start_auto_mode(self):
        """Starts the internal timer for automatic fan adjustments."""
        if not self._adjustment_timer.isActive():
            self.reset_state() # Reset state when starting
            interval_ms = max(100, int(self._adjustment_interval_s * 1000))
            self._adjustment_timer.start(interval_ms)
            print("AutoTemperatureController: Started adjustment timer.") # Debug
            # Perform an initial step immediately? Optional.
            # self._perform_adjustment_step()

    def stop_auto_mode(self):
        """Stops the internal timer for automatic fan adjustments."""
        if self._adjustment_timer.isActive():
            self._adjustment_timer.stop()
            print("AutoTemperatureController: Stopped adjustment timer.") # Debug
        self.reset_state() # Reset state when stopping
    # --- END NEW ---


    def _validate_and_sort(self, table: FanTable) -> FanTable:
        """Sorts table by temperature and ensures basic validity."""
        if not isinstance(table, list): return []
        valid_points = [p for p in table if isinstance(p, list) and len(p) == 2 and all(isinstance(x, (int, float)) for x in p)]
        return sorted(valid_points, key=lambda x: x[0])

    def _create_interpolator(self, table: FanTable, curve_name: str) -> Optional[PchipInterpolator]:
        """Creates a PchipInterpolator from a fan table."""
        if len(table) < MIN_POINTS_FOR_INTERPOLATION: return None
        temps = np.array([p[0] for p in table])
        speeds = np.array([p[1] for p in table])
        unique_temps_map: Dict[float, float] = {}
        for t, s in zip(temps, speeds):
            if t not in unique_temps_map or s > unique_temps_map[t]: unique_temps_map[t] = s
        unique_temps = np.array(sorted(unique_temps_map.keys()))
        unique_speeds = np.array([unique_temps_map[t] for t in unique_temps])
        if len(unique_temps) < MIN_POINTS_FOR_INTERPOLATION: return None
        try:
            return PchipInterpolator(unique_temps, unique_speeds, extrapolate=False)
        except Exception as e:
            print(f"Error creating {curve_name} PCHIP interpolator: {e}", file=sys.stderr)
            return None

    def _interpolate_single_curve(self, temperature: float, table: FanTable, interpolator: Optional[PchipInterpolator]) -> int:
        """Calculates target speed for a single curve using interpolation or linear fallback."""
        if not table: return MIN_FAN_PERCENT
        if temperature == TEMP_READ_ERROR_VALUE: return MIN_FAN_PERCENT
        min_temp_curve, min_speed_curve = table[0]
        max_temp_curve, max_speed_curve = table[-1]
        if temperature <= min_temp_curve: return int(min_speed_curve)
        if temperature >= max_temp_curve: return int(max_speed_curve)
        if interpolator:
            try:
                interp_speed = interpolator(temperature)
                if np.isnan(interp_speed): return self._linear_interpolate(temperature, table)
                return int(max(MIN_FAN_PERCENT, min(MAX_FAN_PERCENT, round(float(interp_speed)))))
            except Exception: return self._linear_interpolate(temperature, table)
        else: return self._linear_interpolate(temperature, table)

    def _linear_interpolate(self, temperature: float, table: FanTable) -> int:
        """Performs simple linear interpolation between points."""
        for i in range(len(table) - 1):
            temp1, speed1 = table[i]
            temp2, speed2 = table[i+1]
            if temp1 <= temperature < temp2:
                if temp2 == temp1: return int(speed1)
                interp_speed = speed1 + (temperature - temp1) * (speed2 - speed1) / (temp2 - temp1)
                return int(max(MIN_FAN_PERCENT, min(MAX_FAN_PERCENT, round(interp_speed))))
        return int(table[-1][1])

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

    @pyqtSlot()
    def _perform_adjustment_step(self):
        """
        Internal slot called by the timer. Reads temps, determines target,
        calculates step, and applies speed via FanController.
        """
        # Ensure WMI is running before proceeding
        if not self._wmi._is_running:
             # print("AutoTemperatureController: WMI not running, skipping adjustment step.") # Debug
             self.stop_auto_mode() # Stop auto mode if WMI fails
             return

        # 1. Read current data
        cpu_temp = self._wmi.get_cpu_temperature()
        gpu_temp = self._wmi.get_gpu_temperature()
        # --- MODIFICATION: Get current speed directly from FanController ---
        current_applied_speed = self._fan.applied_percentage
        # --- END MODIFICATION ---

        # 2. Calculate theoretical target
        theoretical_target = self._calculate_theoretical_target(cpu_temp, gpu_temp)
        self._last_theoretical_target = theoretical_target # Store for external query

        # 3. Apply Hysteresis & Calculate Step Size if Target Changes
        target_changed = False
        if self._active_target_percentage == INIT_APPLIED_PERCENTAGE or \
           abs(theoretical_target - self._active_target_percentage) > self._hysteresis_percent:
            if self._active_target_percentage != theoretical_target:
                # print(f"AutoTempController: New target {theoretical_target} (Old: {self._active_target_percentage}, Hys: {self._hysteresis_percent})") # Debug
                self._active_target_percentage = theoretical_target
                target_changed = True
                # Calculate and store step size based on the difference *now*
                initial_delta = abs(self._active_target_percentage - current_applied_speed)
                self._current_adjustment_step_size = self._calculate_adjustment_step_size(initial_delta)
                self._speed_at_target_set = current_applied_speed
                # print(f"AutoTempController: Target changed. Initial Delta: {initial_delta}, New Step: {self._current_adjustment_step_size}") # Debug


        # 4. Determine Next Speed Step
        target_for_adjustment = self._active_target_percentage
        speed_to_apply: Optional[int] = None

        if target_for_adjustment != INIT_APPLIED_PERCENTAGE and current_applied_speed != target_for_adjustment:
            step_size = self._current_adjustment_step_size
            if step_size is None: # Should only happen on first run after target set or mode switch
                initial_delta = abs(target_for_adjustment - current_applied_speed)
                step_size = self._calculate_adjustment_step_size(initial_delta)
                self._current_adjustment_step_size = step_size
                # print(f"AutoTempController: Step size was None, calculated: {step_size}") # Debug


            # Ensure step_size is valid
            step_size = max(1, step_size) if target_for_adjustment != current_applied_speed else 0

            # Calculate next speed
            next_speed = current_applied_speed
            if target_for_adjustment > current_applied_speed:
                next_speed = min(target_for_adjustment, current_applied_speed + step_size)
            elif target_for_adjustment < current_applied_speed:
                next_speed = max(target_for_adjustment, current_applied_speed - step_size)

            # Set speed_to_apply if different
            if next_speed != current_applied_speed:
                speed_to_apply = next_speed

            # Reset step size if target is reached
            if next_speed == target_for_adjustment:
                # print(f"AutoTempController: Target {target_for_adjustment} reached.") # Debug
                self._current_adjustment_step_size = None
                self._speed_at_target_set = INIT_APPLIED_PERCENTAGE
        else:
             # Target reached or no target set, ensure step size is reset
             if self._current_adjustment_step_size is not None:
                 # print(f"AutoTempController: Target {target_for_adjustment} already met or invalid. Resetting step.") # Debug
                 self._current_adjustment_step_size = None
                 self._speed_at_target_set = INIT_APPLIED_PERCENTAGE

        # 5. Apply Speed using FanController
        if speed_to_apply is not None:
            # print(f"AutoTempController: Applying speed {speed_to_apply}") # Debug
            self._fan.apply_speed_percent(speed_to_apply)
            # FanController updates its internal state. AppRunner's status update
            # will pick up the new applied speed next time it runs.

