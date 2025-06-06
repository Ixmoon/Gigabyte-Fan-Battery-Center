# config/settings.py
# -*- coding: utf-8 -*-
"""
Global constants and default settings for the Fan & Battery Control application.
"""

import os
import sys
from typing import List, Dict

# ==============================================================================
# Base Directory Determination
# ==============================================================================
# Determine the base directory of the application, whether running as script or frozen executable
try:
    if getattr(sys, 'frozen', False):
        # Running as a PyInstaller bundle
        BASE_DIR = os.path.dirname(sys.executable)
    else:
        # Running as a normal script
        # Assumes settings.py is in FanBatteryControl/config/
        BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
except NameError:
    # Fallback if __file__ is not defined (e.g., interactive interpreter)
    BASE_DIR = os.getcwd()

# ==============================================================================
# Application Info
# ==============================================================================
APP_NAME: str = "FanBatteryControl"
APP_ORGANIZATION_NAME: str = "FanBatteryControl" # Used by Qt for settings path
APP_INTERNAL_NAME: str = "FanBatteryControl" # Used for mutex, task name
APP_VERSION: str = "1.0.0"

# ==============================================================================
# File Paths (Relative to BASE_DIR)
# ==============================================================================
CONFIG_FILE_REL_PATH: str = "control_config.json"
LANGUAGES_JSON_REL_PATH: str = "languages.json"
APP_ICON_REL_PATH: str = "app_icon.png"
CONFIG_FILE_PATH: str = os.path.join(BASE_DIR, CONFIG_FILE_REL_PATH)
LANGUAGES_JSON_PATH: str = os.path.join(BASE_DIR, LANGUAGES_JSON_REL_PATH)
APP_ICON_PATH: str = os.path.join(BASE_DIR, APP_ICON_REL_PATH)

# ==============================================================================
# Default Configuration Values
# ==============================================================================
NUM_PROFILES: int = 6
DEFAULT_PROFILE_PREFIX: str = "Config" # Base name for default profiles, number added later
DEFAULT_LANGUAGE: str = "en" # Default language code (ISO 639-1)
DEFAULT_START_ON_BOOT: bool = False
DEFAULT_START_MINIMIZED: bool = False # Default for when launched via auto-start task

# --- Default Profile Settings ---
# These define the structure and default values for *each* profile
DEFAULT_CPU_FAN_TABLE: List[List[int]] = [[50, 0], [60, 15], [70, 25], [80, 40], [85, 60], [90, 80], [95, 100]]
DEFAULT_GPU_FAN_TABLE: List[List[int]] = [[40, 0], [55, 15], [65, 25], [70, 40], [75, 60], [80, 80], [85, 100]]
DEFAULT_FAN_MODE: str = "auto" # "auto" or "fixed"
DEFAULT_FIXED_FAN_SPEED: int = 30 # Percentage
DEFAULT_CHARGE_POLICY: str = "custom" # "standard" or "custom"
DEFAULT_CHARGE_THRESHOLD: int = 80 # Percentage

# --- Default Control Logic & Timing (per profile) ---
DEFAULT_AUTO_MODE_CYCLE_DURATION_S: float = 3.0 # How often to recalculate target speed
DEFAULT_GUI_UPDATE_INTERVAL_MS: int = 1000 # How often the GUI refreshes status
DEFAULT_FAN_ADJUSTMENT_INTERVAL_S: float = 1.5 # How often to adjust fan speed towards target in auto mode
DEFAULT_FAN_HYSTERESIS_PERCENT: int = 5 # Temp change needed to trigger target recalculation
DEFAULT_MIN_ADJUSTMENT_STEP: int = 1 # Smallest fan speed change per adjustment interval
DEFAULT_MAX_ADJUSTMENT_STEP: int = 5 # Largest fan speed change per adjustment interval

# --- Default Curve Plotting & UI Appearance (per profile) ---
DEFAULT_CURVE_POINT_PICKER_RADIUS: float = 8.0 # Click radius for points on graph
DEFAULT_SPLINE_POINTS: int = 100 # Number of points for smooth curve interpolation line
DEFAULT_CPU_CURVE_COLOR: str = '#00AEEF'
DEFAULT_GPU_CURVE_COLOR: str = '#7AC143'
DEFAULT_POINT_COLOR_ACTIVE: str = '#FFFFFF'
DEFAULT_POINT_SIZE_ACTIVE: int = 7
DEFAULT_CPU_TEMP_INDICATOR_COLOR: str = '#FF6347' # Tomato
DEFAULT_GPU_TEMP_INDICATOR_COLOR: str = '#90EE90' # LightGreen
DEFAULT_CPU_SPEED_INDICATOR_COLOR: str = '#FFB3A7' # Lighter Tomato
DEFAULT_GPU_SPEED_INDICATOR_COLOR: str = '#C1F0C1' # Lighter LightGreen
DEFAULT_LINE_WIDTH_ACTIVE: float = 2.0
DEFAULT_LINE_WIDTH_INACTIVE: float = 1.0
DEFAULT_ALPHA_ACTIVE: float = 1.0
DEFAULT_ALPHA_INACTIVE: float = 0.4

# --- Combine all default profile settings into one dictionary ---
DEFAULT_PROFILE_SETTINGS: Dict[str, any] = {
    "cpu_fan_table": [list(p) for p in DEFAULT_CPU_FAN_TABLE],
    "gpu_fan_table": [list(p) for p in DEFAULT_GPU_FAN_TABLE],
    "fan_mode": DEFAULT_FAN_MODE,
    "fixed_fan_speed": DEFAULT_FIXED_FAN_SPEED,
    "charge_policy": DEFAULT_CHARGE_POLICY,
    "charge_threshold": DEFAULT_CHARGE_THRESHOLD,
    "AUTO_MODE_CYCLE_DURATION_S": DEFAULT_AUTO_MODE_CYCLE_DURATION_S,
    "GUI_UPDATE_INTERVAL_MS": DEFAULT_GUI_UPDATE_INTERVAL_MS,
    "FAN_ADJUSTMENT_INTERVAL_S": DEFAULT_FAN_ADJUSTMENT_INTERVAL_S,
    "FAN_HYSTERESIS_PERCENT": DEFAULT_FAN_HYSTERESIS_PERCENT,
    "MIN_ADJUSTMENT_STEP": DEFAULT_MIN_ADJUSTMENT_STEP,
    "MAX_ADJUSTMENT_STEP": DEFAULT_MAX_ADJUSTMENT_STEP,
    "CURVE_POINT_PICKER_RADIUS": DEFAULT_CURVE_POINT_PICKER_RADIUS,
    "SPLINE_POINTS": DEFAULT_SPLINE_POINTS,
    "CPU_CURVE_COLOR": DEFAULT_CPU_CURVE_COLOR,
    "GPU_CURVE_COLOR": DEFAULT_GPU_CURVE_COLOR,
    "POINT_COLOR_ACTIVE": DEFAULT_POINT_COLOR_ACTIVE,
    "POINT_SIZE_ACTIVE": DEFAULT_POINT_SIZE_ACTIVE,
    "CPU_TEMP_INDICATOR_COLOR": DEFAULT_CPU_TEMP_INDICATOR_COLOR,
    "GPU_TEMP_INDICATOR_COLOR": DEFAULT_GPU_TEMP_INDICATOR_COLOR,
    "CPU_SPEED_INDICATOR_COLOR": DEFAULT_CPU_SPEED_INDICATOR_COLOR,
    "GPU_SPEED_INDICATOR_COLOR": DEFAULT_GPU_SPEED_INDICATOR_COLOR,
    "LINE_WIDTH_ACTIVE": DEFAULT_LINE_WIDTH_ACTIVE,
    "LINE_WIDTH_INACTIVE": DEFAULT_LINE_WIDTH_INACTIVE,
    "ALPHA_ACTIVE": DEFAULT_ALPHA_ACTIVE,
    "ALPHA_INACTIVE": DEFAULT_ALPHA_INACTIVE,
}

# ==============================================================================
# WMI Configuration
# ==============================================================================
WMI_NAMESPACE: str = "root\\WMI"
DEFAULT_WMI_GET_CLASS: str = "GB_WMIACPI_Get"
DEFAULT_WMI_SET_CLASS: str = "GB_WMIACPI_Set"

# --- WMI Method Names ---
# Getters
WMI_GET_CPU_TEMP: str = "getCpuTemp"
WMI_GET_GPU_TEMP1: str = "getGpuTemp1" # Primary GPU temp method
WMI_GET_GPU_TEMP2: str = "getGpuTemp2" # Secondary GPU temp method (often unused or same as 1)
WMI_GET_RPM1: str = "getRpm1" # Fan 1 (often CPU)
WMI_GET_RPM2: str = "getRpm2" # Fan 2 (often GPU/System)
WMI_GET_CHARGE_POLICY: str = "GetChargePolicy"
WMI_GET_CHARGE_STOP: str = "GetChargeStop"
# Setters
WMI_SET_FIXED_FAN_STATUS: str = "SetFixedFanStatus" # Enable fixed fan mode (Data=1.0)
WMI_SET_SUPER_QUIET: str = "SetSuperQuiet" # Disable super quiet mode (Data=0.0)
WMI_SET_AUTO_FAN_STATUS: str = "SetAutoFanStatus" # Disable auto fan mode (Data=0.0)
WMI_SET_STEP_FAN_STATUS: str = "SetStepFanStatus" # Disable step fan mode (Data=0.0)
WMI_SET_FIXED_FAN_SPEED: str = "SetFixedFanSpeed" # Set Fan 1 speed (Data=raw_value)
WMI_SET_GPU_FAN_DUTY: str = "SetGPUFanDuty" # Set Fan 2 speed (Data=raw_value)
WMI_SET_CHARGE_POLICY: str = "SetChargePolicy" # Set policy (Data=policy_code)
WMI_SET_CHARGE_STOP: str = "SetChargeStop" # Set threshold (Data=percentage)
WMI_REQUEST_TIMEOUT_S: float = 5.0

# --- WMI Worker Communication ---
WMI_WORKER_STOP_SIGNAL: str = "STOP_WMI_WORKER" # Signal to stop the worker thread

# --- WMI Error/Default Values ---
TEMP_READ_ERROR_VALUE: float = -1.0
RPM_READ_ERROR_VALUE: int = -1
CHARGE_POLICY_READ_ERROR_VALUE: int = -1
CHARGE_THRESHOLD_READ_ERROR_VALUE: int = -1
INIT_APPLIED_PERCENTAGE: int = -1 # Initial state before first application

# --- WMI Battery Policy Codes ---
CHARGE_POLICY_STANDARD: int = 0
CHARGE_POLICY_CUSTOM: int = 4 # Gigabyte specific code for custom threshold

# ==============================================================================
# Control Logic Parameters
# ==============================================================================
MIN_TEMP_C: int = 0
MAX_TEMP_C: int = 100
MIN_FAN_PERCENT: int = 0
MAX_FAN_PERCENT: int = 100
MIN_CHARGE_PERCENT: int = 0 # Usually limited by hardware/BIOS (e.g., 50)
MAX_CHARGE_PERCENT: int = 100
MIN_CURVE_POINTS: int = 2 # Minimum points required for a valid fan curve
MIN_POINTS_FOR_INTERPOLATION: int = 2 # Minimum unique points for PCHIP

# ==============================================================================
# Task Scheduler / Single Instance
# ==============================================================================
TASK_SCHEDULER_NAME: str = f"{APP_INTERNAL_NAME} Startup Task"
STARTUP_ARG_MINIMIZED: str = "--minimized" # Argument passed when started by task scheduler
# Generate a unique mutex name for this application (replace with a real GUID if needed)
_APP_GUID: str = "{17e0cc04-cddb-4b9b-adcc-5faa4872e054}"
MUTEX_NAME: str = f"Global\\{APP_INTERNAL_NAME}_Mutex_{_APP_GUID}"
SHARED_MEM_NAME: str = f"Global\\{APP_INTERNAL_NAME}_SharedMem_{_APP_GUID}"
SHARED_MEM_SIZE: int = 64 # Size in bytes (enough for HWND as string + null terminator, or binary)

# ==============================================================================
# Font Configuration (for Matplotlib)
# ==============================================================================
# Attempt to use preferred fonts, fallback to generic sans-serif
PREFERRED_FONTS: List[str] = ['Microsoft YaHei', 'DengXian', 'SimHei', 'Arial Unicode MS', 'sans-serif']

# ==============================================================================
# Miscellaneous
# ==============================================================================
# Define known language codes and their display names for the language dropdown
# This is used as a fallback if the names aren't defined within the language file itself
KNOWN_LANGUAGES: Dict[str, str] = {
    "en": "English",
}