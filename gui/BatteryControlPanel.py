# -*- coding: utf-8 -*-
"""
电池控制面板QFrame - 一个自包含的视图组件。
此类继承自BaseControlPanel，为电池控制提供特定的UI配置。
"""
from .qt import QWidget
from .base_control_panel import BaseControlPanel
from core.state import AppState
from core.profile_manager import ProfileManager
from config.settings import CHARGE_POLICY_CUSTOM, MIN_CHARGE_PERCENT, MAX_CHARGE_PERCENT
from typing import Optional

class BatteryControlPanel(BaseControlPanel):
    """电池控制的专用视图组件。"""

    def __init__(self, state: AppState, profile_manager: ProfileManager, parent: Optional[QWidget] = None):
        config = {
            "mode_label_key": "charge_policy_label",
            "radio_configs": [("bios", "mode_bios"), ("custom", "mode_custom")],
            "slider_label_key": "charge_threshold_label",
            "slider_range": (MIN_CHARGE_PERCENT, MAX_CHARGE_PERCENT),
            "custom_mode_name": CHARGE_POLICY_CUSTOM,
            "profile_mode_attr": "battery_charge_policy",
            "profile_value_attr": "battery_charge_threshold",
            "mode_tooltip_key": "charge_policy_tooltip",
            "slider_tooltip_key": "charge_threshold_tooltip",
            "is_fan_control": False, # 【新增】标记这不是风扇控制面板
        }
        super().__init__(config, state, profile_manager, parent)