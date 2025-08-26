# gui/ui_builder.py
# -*- coding: utf-8 -*-
"""
Defines the UIBuilder class responsible for creating and laying out all UI widgets.
This centralizes UI construction, decoupling it from the application logic in the panels.
"""

from dataclasses import dataclass
from typing import cast
from .qt import (
    QWidget, QLabel, QRadioButton, QSlider, QButtonGroup, QHBoxLayout,
    QVBoxLayout, QFrame, QSpacerItem, QSizePolicy, Qt, QGridLayout,
    QPushButton, QCheckBox
)
from tools.localization import tr

# ==============================================================================
# Dataclasses for Widget Collections
# ==============================================================================

@dataclass
class StatusInfoControls:
    """Holds all widgets for the StatusInfoPanel."""
    cpu_temp_label: QLabel
    cpu_temp_value: QLabel
    gpu_temp_label: QLabel
    gpu_temp_value: QLabel
    cpu_fan_rpm_label: QLabel
    cpu_fan_rpm_value: QLabel
    gpu_fan_rpm_label: QLabel
    gpu_fan_rpm_value: QLabel
    applied_target_label: QLabel
    applied_target_value: QLabel
    battery_info_label: QLabel
    battery_info_value: QLabel

@dataclass
class CurveControls:
    """Holds all widgets for the CurveControlPanel."""
    cpu_curve_button: QPushButton
    gpu_curve_button: QPushButton
    curve_button_group: QButtonGroup
    profile_button_group: QButtonGroup
    start_on_boot_checkbox: QCheckBox
    reset_curve_button: QPushButton
    # Profile buttons are managed dynamically by the panel, not stored here.
    # The layout is returned implicitly via the parent.
    controls_layout: QHBoxLayout

@dataclass
class FanControls:
    """Holds all widgets for the FanControlPanel."""
    fan_mode_label: QLabel
    bios_fan_mode_radio: QRadioButton
    auto_fan_mode_radio: QRadioButton
    custom_fan_mode_radio: QRadioButton
    fan_mode_button_group: QButtonGroup
    custom_fan_speed_label: QLabel
    custom_fan_speed_slider: QSlider
    custom_fan_speed_value_label: QLabel

@dataclass
class BatteryControls:
    """Holds all widgets for the BatteryControlPanel."""
    charge_policy_label: QLabel
    bios_charge_radio: QRadioButton
    custom_charge_radio: QRadioButton
    charge_policy_button_group: QButtonGroup
    charge_threshold_label: QLabel
    charge_threshold_slider: QSlider
    charge_threshold_value_label: QLabel

# ==============================================================================
# UIBuilder Class
# ==============================================================================

class UIBuilder:
    """Builds and lays out UI components, returning collections of widgets."""

    def build_fan_panel(self, parent: QWidget) -> FanControls:
        """Builds the fan control panel UI."""
        parent.setObjectName("fanControlFrame")
        layout = QHBoxLayout(parent)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(10)

        fan_mode_label = QLabel(tr("fan_mode_label"))
        bios_fan_mode_radio = QRadioButton(tr("mode_bios"))
        auto_fan_mode_radio = QRadioButton(tr("mode_auto"))
        custom_fan_mode_radio = QRadioButton(tr("mode_custom"))
        
        fan_mode_button_group = QButtonGroup(parent)
        fan_mode_button_group.addButton(bios_fan_mode_radio)
        fan_mode_button_group.addButton(auto_fan_mode_radio)
        fan_mode_button_group.addButton(custom_fan_mode_radio)

        custom_fan_speed_label = QLabel(tr("custom_speed_label"))
        custom_fan_speed_label.setObjectName("custom_fan_speed_label")
        
        custom_fan_speed_slider = QSlider(Qt.Orientation.Horizontal)
        custom_fan_speed_slider.setRange(0, 100)
        custom_fan_speed_slider.setTickInterval(10)
        custom_fan_speed_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        
        custom_fan_speed_value_label = QLabel(tr("value_not_available"))
        custom_fan_speed_value_label.setMinimumWidth(45)
        custom_fan_speed_value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        custom_fan_speed_value_label.setObjectName("custom_speed_value_label")

        layout.addWidget(fan_mode_label)
        layout.addWidget(bios_fan_mode_radio)
        layout.addWidget(auto_fan_mode_radio)
        layout.addWidget(custom_fan_mode_radio)
        layout.addSpacerItem(QSpacerItem(20, 10, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))
        layout.addWidget(custom_fan_speed_label)
        layout.addWidget(custom_fan_speed_slider, 1)
        layout.addWidget(custom_fan_speed_value_label)

        return FanControls(
            fan_mode_label=fan_mode_label,
            bios_fan_mode_radio=bios_fan_mode_radio,
            auto_fan_mode_radio=auto_fan_mode_radio,
            custom_fan_mode_radio=custom_fan_mode_radio,
            fan_mode_button_group=fan_mode_button_group,
            custom_fan_speed_label=custom_fan_speed_label,
            custom_fan_speed_slider=custom_fan_speed_slider,
            custom_fan_speed_value_label=custom_fan_speed_value_label
        )

    def build_battery_panel(self, parent: QWidget) -> BatteryControls:
        """Builds the battery control panel UI."""
        parent.setObjectName("batteryControlFrame")
        layout = QHBoxLayout(parent)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(10)

        charge_policy_label = QLabel(tr("charge_policy_label"))
        bios_charge_radio = QRadioButton(tr("mode_bios"))
        bios_charge_radio.setToolTip(tr("policy_bios_tooltip"))
        custom_charge_radio = QRadioButton(tr("mode_custom"))
        custom_charge_radio.setToolTip(tr("policy_custom_tooltip"))

        charge_policy_button_group = QButtonGroup(parent)
        charge_policy_button_group.addButton(bios_charge_radio)
        charge_policy_button_group.addButton(custom_charge_radio)

        charge_threshold_label = QLabel(tr("charge_threshold_label"))
        
        charge_threshold_slider = QSlider(Qt.Orientation.Horizontal)
        charge_threshold_slider.setRange(60, 100)
        charge_threshold_slider.setTickInterval(5)
        charge_threshold_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        charge_threshold_slider.setToolTip(tr("threshold_slider_tooltip"))

        charge_threshold_value_label = QLabel()
        charge_threshold_value_label.setMinimumWidth(45)
        charge_threshold_value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        charge_threshold_value_label.setObjectName("charge_threshold_value_label")

        layout.addWidget(charge_policy_label)
        layout.addWidget(bios_charge_radio)
        layout.addWidget(custom_charge_radio)
        layout.addSpacerItem(QSpacerItem(20, 10, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))
        layout.addWidget(charge_threshold_label)
        layout.addWidget(charge_threshold_slider, 1)
        layout.addWidget(charge_threshold_value_label)

        return BatteryControls(
            charge_policy_label=charge_policy_label,
            bios_charge_radio=bios_charge_radio,
            custom_charge_radio=custom_charge_radio,
            charge_policy_button_group=charge_policy_button_group,
            charge_threshold_label=charge_threshold_label,
            charge_threshold_slider=charge_threshold_slider,
            charge_threshold_value_label=charge_threshold_value_label
        )

    def build_status_info_panel(self, parent: QWidget) -> StatusInfoControls:
        """Builds the status info panel UI."""
        frame_parent = cast(QFrame, parent)
        frame_parent.setObjectName("infoFrame")
        frame_parent.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QGridLayout(parent)
        layout.setContentsMargins(10, 5, 10, 10)
        layout.setSpacing(10)

        cpu_temp_label = QLabel(tr("cpu_temp_label"))
        cpu_temp_value = QLabel(tr("value_not_available"))
        gpu_temp_label = QLabel(tr("gpu_temp_label"))
        gpu_temp_value = QLabel(tr("value_not_available"))
        fan1_rpm_label = QLabel(tr("fan1_rpm_label"))
        fan1_rpm_value = QLabel(tr("value_not_available"))
        fan2_rpm_label = QLabel(tr("fan2_rpm_label"))
        fan2_rpm_value = QLabel(tr("value_not_available"))
        applied_target_label = QLabel(tr("applied_target_label"))
        applied_target_value = QLabel(tr("value_not_available"))
        battery_info_label = QLabel(tr("battery_info_label"))
        battery_info_value = QLabel(tr("value_not_available"))

        cpu_temp_value.setObjectName("cpu_temp_value")
        gpu_temp_value.setObjectName("gpu_temp_value")
        fan1_rpm_value.setObjectName("fan1_rpm_value")
        fan2_rpm_value.setObjectName("fan2_rpm_value")
        applied_target_value.setObjectName("applied_target_value")
        battery_info_value.setObjectName("battery_info_value")

        layout.addWidget(cpu_temp_label, 0, 0)
        layout.addWidget(cpu_temp_value, 0, 1)
        layout.addWidget(gpu_temp_label, 0, 2)
        layout.addWidget(gpu_temp_value, 0, 3)
        layout.addWidget(fan1_rpm_label, 1, 0)
        layout.addWidget(fan1_rpm_value, 1, 1)
        layout.addWidget(fan2_rpm_label, 1, 2)
        layout.addWidget(fan2_rpm_value, 1, 3)
        layout.addWidget(applied_target_label, 2, 0)
        layout.addWidget(applied_target_value, 2, 1)
        layout.addWidget(battery_info_label, 2, 2)
        layout.addWidget(battery_info_value, 2, 3)

        layout.setColumnStretch(1, 1)
        layout.setColumnStretch(3, 1)

        return StatusInfoControls(
            cpu_temp_label=cpu_temp_label,
            cpu_temp_value=cpu_temp_value,
            gpu_temp_label=gpu_temp_label,
            gpu_temp_value=gpu_temp_value,
            cpu_fan_rpm_label=fan1_rpm_label,
            cpu_fan_rpm_value=fan1_rpm_value,
            gpu_fan_rpm_label=fan2_rpm_label,
            gpu_fan_rpm_value=fan2_rpm_value,
            applied_target_label=applied_target_label,
            applied_target_value=applied_target_value,
            battery_info_label=battery_info_label,
            battery_info_value=battery_info_value,
        )

    def build_curve_control_panel(self, parent: QWidget) -> CurveControls:
        """Builds the curve control panel UI."""
        main_layout = QVBoxLayout(parent)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)

        controls_layout = QHBoxLayout()
        
        cpu_curve_button = QPushButton(tr("cpu_curve_button"))
        cpu_curve_button.setCheckable(True)
        gpu_curve_button = QPushButton(tr("gpu_curve_button"))
        gpu_curve_button.setCheckable(True)

        curve_button_group = QButtonGroup(parent)
        curve_button_group.addButton(cpu_curve_button)
        curve_button_group.addButton(gpu_curve_button)
        curve_button_group.setExclusive(True)

        profile_button_group = QButtonGroup(parent)
        profile_button_group.setExclusive(True)

        start_on_boot_checkbox = QCheckBox(tr("start_on_boot_label"))
        start_on_boot_checkbox.setToolTip(tr("start_on_boot_tooltip"))

        reset_curve_button = QPushButton(tr("reset_curve_button"))
        reset_curve_button.setObjectName("resetCurveButton")

        controls_layout.addWidget(cpu_curve_button)
        controls_layout.addWidget(gpu_curve_button)
        controls_layout.addSpacerItem(QSpacerItem(15, 10, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum))
        
        controls_layout.addStretch(1)
        controls_layout.addWidget(start_on_boot_checkbox)
        controls_layout.addSpacerItem(QSpacerItem(10, 10, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum))
        controls_layout.addWidget(reset_curve_button)
        
        main_layout.addLayout(controls_layout)

        return CurveControls(
            cpu_curve_button=cpu_curve_button,
            gpu_curve_button=gpu_curve_button,
            curve_button_group=curve_button_group,
            profile_button_group=profile_button_group,
            start_on_boot_checkbox=start_on_boot_checkbox,
            reset_curve_button=reset_curve_button,
            controls_layout=controls_layout
        )