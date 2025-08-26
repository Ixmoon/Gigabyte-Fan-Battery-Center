# gui/StatusInfoPanel.py
# -*- coding: utf-8 -*-
"""
Status Information Panel QFrame - Pure View Component.
"""
from .qt import QFrame, Slot
from typing import TYPE_CHECKING
from core.state import AppState
from tools.localization import tr
from config.settings import (
    TEMP_READ_ERROR_VALUE, RPM_READ_ERROR_VALUE,
    FAN_MODE_AUTO, FAN_MODE_CUSTOM, FAN_MODE_BIOS,
    CHARGE_POLICY_CUSTOM, CHARGE_POLICY_BIOS
)
from .ui_builder import StatusInfoControls

if TYPE_CHECKING:
    pass

class StatusInfoPanel(QFrame):
    """A pure view component for displaying system status."""

    def __init__(self, controls: StatusInfoControls, parent=None):
        super().__init__(parent)
        self.controls = controls

    @Slot(object)
    def update_state(self, state: AppState) -> None:
        """Updates the display labels with new data from the AppState."""
        self.setEnabled(state.is_panel_enabled)
        profile = state.profiles.get(state.active_profile_name)

        # Temperatures
        cpu_temp = state.cpu_temp
        gpu_temp = state.gpu_temp
        cpu_temp_str = f"{cpu_temp:.1f}{tr('celsius_unit')}" if cpu_temp != TEMP_READ_ERROR_VALUE else tr("temp_error")
        gpu_temp_str = f"{gpu_temp:.1f}{tr('celsius_unit')}" if gpu_temp != TEMP_READ_ERROR_VALUE else tr("temp_error")
        self.controls.cpu_temp_value.setText(cpu_temp_str)
        self.controls.gpu_temp_value.setText(gpu_temp_str)

        # RPMs
        fan1_rpm = state.cpu_fan_rpm
        fan2_rpm = state.gpu_fan_rpm
        rpm1_str = f"{fan1_rpm}{tr('rpm_unit')}" if fan1_rpm != RPM_READ_ERROR_VALUE else tr("rpm_error")
        rpm2_str = f"{fan2_rpm}{tr('rpm_unit')}" if fan2_rpm != RPM_READ_ERROR_VALUE else tr("rpm_error")
        self.controls.cpu_fan_rpm_value.setText(rpm1_str)
        self.controls.gpu_fan_rpm_value.setText(rpm2_str)

        if not profile:
            self.controls.applied_target_value.setText(tr("value_not_available"))
            self.controls.battery_info_value.setText(tr("value_not_available"))
            return

        # Fan Speed / Target Display
        fan_mode = profile.fan_mode
        if fan_mode == FAN_MODE_AUTO:
            fan_display_text = tr("fan_display_auto_format", applied=state.applied_fan_speed_percent, target=state.auto_fan_target_speed_percent)
        elif fan_mode == FAN_MODE_CUSTOM:
            fan_display_text = f"{profile.custom_fan_speed}{tr('percent_unit')}"
        else: # FAN_MODE_BIOS
            fan_display_text = tr('mode_bios')
        self.controls.applied_target_value.setText(fan_display_text)

        # Battery Info Display
        policy_str = tr("mode_custom") if profile.battery_charge_policy == CHARGE_POLICY_CUSTOM else tr("mode_bios")
        threshold_str = f"{profile.battery_charge_threshold}{tr('percent_unit')}"
        self.controls.battery_info_value.setText(tr("battery_display_format", policy=policy_str, limit=threshold_str))

    def retranslate_ui(self) -> None:
        """Retranslates all user-visible text in the panel."""
        self.controls.cpu_temp_label.setText(tr("cpu_temp_label"))
        self.controls.gpu_temp_label.setText(tr("gpu_temp_label"))
        self.controls.cpu_fan_rpm_label.setText(tr("fan1_rpm_label"))
        self.controls.gpu_fan_rpm_label.setText(tr("fan2_rpm_label"))
        self.controls.applied_target_label.setText(tr("applied_target_label"))
        self.controls.battery_info_label.setText(tr("battery_info_label"))
        # Values are updated dynamically by update_state, which uses tr()