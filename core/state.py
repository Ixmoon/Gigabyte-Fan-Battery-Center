# core/state.py
# -*- coding: utf-8 -*-
"""
Defines the centralized state for the application.
Inspired by the state management approach in modern applications, this module
provides a single source of truth for all application data, both persistent
and transient.
"""

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional

# ==============================================================================
# State Constants
# ==============================================================================

FAN_MODE_AUTO = "auto"
FAN_MODE_FIXED = "fixed"
CHARGE_POLICY_STANDARD = "standard"
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
    cpu_fan_table: List[List[int]] = field(default_factory=list)
    gpu_fan_table: List[List[int]] = field(default_factory=list)
    fan_mode: str = FAN_MODE_AUTO
    fixed_fan_speed: int = 50
    charge_policy: str = CHARGE_POLICY_CUSTOM
    charge_threshold: int = 80

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class RuntimeState:
    """
    Represents the transient, real-time state of the application and hardware.
    This data is not saved to disk.
    """
    cpu_temp: float = 0.0
    gpu_temp: float = 0.0
    cpu_fan_rpm: int = 0
    gpu_fan_rpm: int = 0

    # The actual values currently applied to the hardware
    applied_fan_mode: str = FAN_MODE_AUTO
    applied_fan_speed_percent: int = 0
    applied_charge_policy: str = CHARGE_POLICY_STANDARD
    applied_charge_threshold: int = 100

    # UI-specific state
    is_panel_enabled: bool = True
    active_curve_type: str = "cpu" # 'cpu' or 'gpu'


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
    window_geometry: Optional[bytes] = None # For storing QMainWindow geometry

    # --- Transient Runtime State ---
    runtime: RuntimeState = field(default_factory=RuntimeState)
