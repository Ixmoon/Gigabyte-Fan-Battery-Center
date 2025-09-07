# -*- coding: utf-8 -*-
"""
风扇控制面板QFrame - 一个自包含的视图组件。
此类继承自BaseControlPanel，为风扇控制提供特定的UI配置。
"""
from .qt import QWidget
from .base_control_panel import BaseControlPanel
from core.state import AppState
from core.profile_manager import ProfileManager
from config.settings import FAN_MODE_CUSTOM
from typing import Optional

class FanControlPanel(BaseControlPanel):
    """风扇控制的专用视图组件。"""
    
    def __init__(self, state: AppState, profile_manager: ProfileManager, parent: Optional[QWidget] = None):
        config = {
            "mode_label_key": "fan_mode_label",
            "radio_configs": [("bios", "mode_bios"), ("auto", "mode_auto"), ("custom", "mode_custom")],
            "slider_label_key": "custom_speed_label",
            "slider_range": (0, 100),
            "custom_mode_name": FAN_MODE_CUSTOM,
            "profile_mode_attr": "fan_mode",
            "profile_value_attr": "custom_fan_speed",
            "mode_tooltip_key": "fan_mode_tooltip",
            "slider_tooltip_key": "custom_fan_speed_tooltip",
            "is_fan_control": True, # 标记这是一个风扇控制面板
        }
        super().__init__(config, state, profile_manager, parent)