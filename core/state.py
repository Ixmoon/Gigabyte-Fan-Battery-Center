# core/state.py
# -*- coding: utf-8 -*-
"""
Defines the centralized state for the application.
Inspired by the state management approach in modern applications, this module
provides a single source of truth for all application data, both persistent
and transient.
"""

from dataclasses import dataclass, field, asdict, fields
from typing import List, Dict, Optional, Any
from config.settings import DEFAULT_PROFILE_SETTINGS
 
# ==============================================================================
# State Constants
# ==============================================================================

FAN_MODE_BIOS = "bios"
FAN_MODE_AUTO = "auto"
FAN_MODE_CUSTOM = "custom"
CHARGE_POLICY_BIOS = "bios"
CHARGE_POLICY_CUSTOM = "custom"


# ==============================================================================
# Data Structures for State
# ==============================================================================

@dataclass
class ProfileState:
    """
    Represents the complete set of user-configurable settings for a single profile.
    This structure is designed to be easily serialized to/from JSON.
    """
    # Note: The keys in DEFAULT_PROFILE_SETTINGS are UPPER_CASE.
    # The dataclass fields are lower_case. This is handled by load_from_dict.
    cpu_fan_table: List[List[int]] = field(default_factory=lambda: DEFAULT_PROFILE_SETTINGS['CPU_FAN_TABLE'])
    gpu_fan_table: List[List[int]] = field(default_factory=lambda: DEFAULT_PROFILE_SETTINGS['GPU_FAN_TABLE'])
    fan_mode: str = field(default=DEFAULT_PROFILE_SETTINGS['FAN_MODE'])
    custom_fan_speed: int = field(default=DEFAULT_PROFILE_SETTINGS['CUSTOM_FAN_SPEED'])
    battery_charge_policy: str = field(default=DEFAULT_PROFILE_SETTINGS['BATTERY_CHARGE_POLICY'])
    battery_charge_threshold: int = field(default=DEFAULT_PROFILE_SETTINGS['BATTERY_CHARGE_THRESHOLD'])
    fan_adjustment_interval_s: float = field(default=DEFAULT_PROFILE_SETTINGS['FAN_ADJUSTMENT_INTERVAL_S'])
    fan_hysteresis_percent: int = field(default=DEFAULT_PROFILE_SETTINGS['FAN_HYSTERESIS_PERCENT'])
    min_adjustment_step: int = field(default=DEFAULT_PROFILE_SETTINGS['MIN_ADJUSTMENT_STEP'])
    max_adjustment_step: int = field(default=DEFAULT_PROFILE_SETTINGS['MAX_ADJUSTMENT_STEP'])
    gui_update_interval_ms: int = field(default=DEFAULT_PROFILE_SETTINGS['GUI_UPDATE_INTERVAL_MS'])

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def load_from_dict(cls, data: Dict[str, Any]) -> 'ProfileState':
        # Normalize all keys in the input dictionary to lowercase to match dataclass fields
        normalized_data = {k.lower(): v for k, v in data.items()}
        
        # Get the field names defined in the dataclass
        known_fields = {f.name for f in fields(cls)}
        
        # Prepare init data, filtering out any unknown keys from the input dict
        init_data = {k: v for k, v in normalized_data.items() if k in known_fields}

        # Ensure fan tables are lists of lists, not lists of tuples, which can happen after JSON deserialization
        for key in ['cpu_fan_table', 'gpu_fan_table']:
            if key in init_data and init_data[key]:
                init_data[key] = [list(point) for point in init_data[key]]
        
        return cls(**init_data)


@dataclass
class AppState:
    """
    The main, top-level state object for the entire application.
    This object is the single source of truth.
    """
    # --- Persisted Global Settings ---
    language: str = "en"
    start_on_boot: bool = False
    active_profile_name: str = "Config 1"
    profiles: Dict[str, ProfileState] = field(default_factory=dict)
    window_geometry: Optional[str] = None # For storing QMainWindow geometry

    # --- Transient Runtime State (Flattened) ---
    cpu_temp: float = 0.0
    gpu_temp: float = 0.0
    cpu_fan_rpm: int = 0
    gpu_fan_rpm: int = 0
    applied_fan_mode: str = FAN_MODE_AUTO
    applied_fan_speed_percent: int = 0
    auto_fan_target_speed_percent: int = 0 # Target speed calculated by the auto controller
    applied_charge_policy: str = CHARGE_POLICY_BIOS
    applied_charge_threshold: int = 100
    is_panel_enabled: bool = True
    active_curve_type: str = "cpu" # 'cpu' or 'gpu'
    controller_status_message: str = ""
