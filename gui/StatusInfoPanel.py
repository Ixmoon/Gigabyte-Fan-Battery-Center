# gui/StatusInfoPanel.py
# -*- coding: utf-8 -*-
"""
Status Information Panel QWidget for Fan & Battery Control.

Displays CPU/GPU temperatures, fan RPMs, battery info, and controller status.
"""
from __future__ import annotations
from typing import TYPE_CHECKING, Optional

from .qt import QWidget, QGridLayout, QLabel, QFrame

from tools.localization import tr
from config.settings import (
    TEMP_READ_ERROR_VALUE, RPM_READ_ERROR_VALUE,
    FAN_MODE_AUTO, CHARGE_POLICY_STANDARD, CHARGE_POLICY_CUSTOM
)

if TYPE_CHECKING:
    from core.state import AppState


class StatusInfoPanel(QFrame):
    """
    A QFrame subclass that displays various system status information.
    """
    def __init__(self, parent: Optional[QWidget] = None):
        """
        Initializes the StatusInfoPanel.

        Args:
            parent: The parent widget.
        """
        super().__init__(parent)
        self.setObjectName("infoFrame") # For styling consistent with MainWindow
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self._init_ui()

    def _init_ui(self) -> None:
        """
        Initializes the UI elements for the status panel.
        """
        layout = QGridLayout(self)
        layout.setContentsMargins(10, 5, 10, 10)
        layout.setSpacing(10)

        self.cpu_temp_label = QLabel(str(tr("cpu_temp_label")))
        self.cpu_temp_value = QLabel(str(tr("value_not_available")))
        self.gpu_temp_label = QLabel(str(tr("gpu_temp_label")))
        self.gpu_temp_value = QLabel(str(tr("value_not_available")))
        self.fan1_rpm_label = QLabel(str(tr("fan1_rpm_label")))
        self.fan1_rpm_value = QLabel(str(tr("value_not_available")))
        self.fan2_rpm_label = QLabel(str(tr("fan2_rpm_label")))
        self.fan2_rpm_value = QLabel(str(tr("value_not_available")))
        self.applied_target_label = QLabel(str(tr("applied_target_label")))
        self.applied_target_value = QLabel(str(tr("value_not_available")))
        self.battery_info_label = QLabel(str(tr("battery_info_label")))
        self.battery_info_value = QLabel(str(tr("value_not_available")))

        # Assign object names for styling/testing if needed from MainWindow
        self.cpu_temp_value.setObjectName("cpu_temp_value")
        self.gpu_temp_value.setObjectName("gpu_temp_value")
        self.fan1_rpm_value.setObjectName("fan1_rpm_value")
        self.fan2_rpm_value.setObjectName("fan2_rpm_value")
        self.applied_target_value.setObjectName("applied_target_value")
        self.battery_info_value.setObjectName("battery_info_value")

        # Add widgets to grid layout
        layout.addWidget(self.cpu_temp_label, 0, 0)
        layout.addWidget(self.cpu_temp_value, 0, 1)
        layout.addWidget(self.gpu_temp_label, 0, 2)
        layout.addWidget(self.gpu_temp_value, 0, 3)
        layout.addWidget(self.fan1_rpm_label, 1, 0)
        layout.addWidget(self.fan1_rpm_value, 1, 1)
        layout.addWidget(self.fan2_rpm_label, 1, 2)
        layout.addWidget(self.fan2_rpm_value, 1, 3)
        layout.addWidget(self.applied_target_label, 2, 0)
        layout.addWidget(self.applied_target_value, 2, 1)
        layout.addWidget(self.battery_info_label, 2, 2)
        layout.addWidget(self.battery_info_value, 2, 3)

        layout.setColumnStretch(1, 1) # Allow values to expand
        layout.setColumnStretch(3, 1)

    def update_state(self, state: AppState) -> None:
        """
        Updates the display labels with new data from the AppState.

        Args:
            state: The new application state.
        """
        # Set the enabled state of all labels first
        self.setEnabled(state.is_panel_enabled)

        profile = state.profiles.get(state.active_profile_name)

        # Temperatures
        cpu_temp = state.cpu_temp
        gpu_temp = state.gpu_temp
        cpu_temp_str = f"{cpu_temp:.1f}{tr('celsius_unit')}" if cpu_temp != TEMP_READ_ERROR_VALUE else str(tr("temp_error"))
        gpu_temp_str = f"{gpu_temp:.1f}{tr('celsius_unit')}" if gpu_temp != TEMP_READ_ERROR_VALUE else str(tr("temp_error"))
        self.cpu_temp_value.setText(str(cpu_temp_str))
        self.gpu_temp_value.setText(str(gpu_temp_str))

        # RPMs
        fan1_rpm = state.cpu_fan_rpm
        fan2_rpm = state.gpu_fan_rpm
        rpm1_str = f"{fan1_rpm}{tr('rpm_unit')}" if fan1_rpm != RPM_READ_ERROR_VALUE else str(tr("rpm_error"))
        rpm2_str = f"{fan2_rpm}{tr('rpm_unit')}" if fan2_rpm != RPM_READ_ERROR_VALUE else str(tr("rpm_error"))
        self.fan1_rpm_value.setText(str(rpm1_str))
        self.fan2_rpm_value.setText(str(rpm2_str))

        if not profile:
            self.applied_target_value.setText(str(tr("value_not_available")))
            self.battery_info_value.setText(str(tr("value_not_available")))
            return

        # Fan Speed / Target Display from Profile
        fan_mode = profile.fan_mode
        
        if fan_mode == FAN_MODE_AUTO:
            fan_display_text = str(tr('mode_auto'))
        else:  # Fixed mode
            fan_display_text = f"{profile.fixed_fan_speed}{tr('percent_unit')}"
        self.applied_target_value.setText(str(fan_display_text))

        # Battery Info Display from Profile
        charge_policy = profile.battery_charge_policy
        charge_threshold = profile.battery_charge_threshold

        policy_str = tr("policy_error")
        if charge_policy == CHARGE_POLICY_STANDARD:
            policy_str = tr("mode_standard")
        elif charge_policy == CHARGE_POLICY_CUSTOM:
            policy_str = tr("mode_custom")
        
        threshold_str = f"{charge_threshold}{tr('percent_unit')}"
        
        self.battery_info_value.setText(str(tr("battery_display_format", policy=policy_str, limit=threshold_str)))

    def retranslate_ui(self) -> None:
        """Retranslates all user-visible text in the panel."""
        self.cpu_temp_label.setText(str(tr("cpu_temp_label")))
        self.gpu_temp_label.setText(str(tr("gpu_temp_label")))
        self.fan1_rpm_label.setText(str(tr("fan1_rpm_label")))
        self.fan2_rpm_label.setText(str(tr("fan2_rpm_label")))
        self.applied_target_label.setText(str(tr("applied_target_label")))
        self.battery_info_label.setText(str(tr("battery_info_label")))
        # The value labels will be updated by update_status with translated units/errors
        # If there's an initial state that needs re-translation before first update_status,
        # check against the translated "not available" value.
        vna = str(tr("value_not_available"))
        if self.cpu_temp_value.text() == vna:
             self.cpu_temp_value.setText(vna) # No unit needed for "---"
        if self.gpu_temp_value.text() == vna:
             self.gpu_temp_value.setText(vna)
        if self.fan1_rpm_value.text() == vna:
             self.fan1_rpm_value.setText(vna)
        if self.fan2_rpm_value.text() == vna:
             self.fan2_rpm_value.setText(vna)
        if self.applied_target_value.text() == vna:
            self.applied_target_value.setText(vna)
        if self.battery_info_value.text() == vna:
            self.battery_info_value.setText(vna)

    def set_panel_enabled(self, enabled: bool) -> None:
        """
        Sets the enabled state of the panel.
        For StatusInfoPanel, this typically doesn't change interactivity of labels,
        but is implemented for interface consistency.
        """
        # Labels generally don't need to be explicitly enabled/disabled
        # unless specific visual cues for disabled state are desired.
        # self.cpu_temp_label.setEnabled(enabled) # Example if needed
        pass

if __name__ == '__main__':
    # Example Usage (for testing the panel independently)
    import sys
    from .qt import QApplication
    # Mock translations for standalone testing
    _translations = {
        "en": {
            "cpu_temp_label": "CPU Temp:", "gpu_temp_label": "GPU Temp:",
            "fan1_rpm_label": "Fan 1 RPM:", "fan2_rpm_label": "Fan 2 RPM:",
            "applied_target_label": "Applied/Target:", "battery_info_label": "Battery Policy/Limit:",
            "status_label": "Status:", "initializing": "Initializing...",
            "celsius_unit": "°C", "rpm_unit": " RPM", "percent_unit": "%",
            "temp_error": "Error", "rpm_error": "Error", "policy_error": "Error",
            "threshold_error": "Error", "mode_auto": "Auto", "mode_standard": "Standard",
            "mode_custom": "Custom", "unknown_mode": "Unknown", "unknown_state": "Unknown State",
            "wmi_error": "WMI Error"
        }
    }
    current_lang = "en"
    def tr(key, **kwargs):
        translation = _translations.get(current_lang, {}).get(key, key)
        if kwargs and translation is not None:
            return translation.format(**kwargs)
        return translation or key

    app = QApplication(sys.argv)
    panel = StatusInfoPanel()
    panel.show()
    panel.resize(500, 150)

    # Example data to update the panel (This test is now illustrative, as it doesn't use the AppState object)
    # To properly test, one would need to construct an AppState object.
    # For now, we can manually set text to see the layout.
    panel.cpu_temp_value.setText(f"65.5{str(tr('celsius_unit'))}")
    panel.gpu_temp_value.setText(f"72.1{str(tr('celsius_unit'))}")
    panel.fan1_rpm_value.setText(f"2500{str(tr('rpm_unit'))}")
    panel.fan2_rpm_value.setText(f"2800{str(tr('rpm_unit'))}")
    panel.applied_target_value.setText(str(tr("fan_display_auto_simple_format", applied=f"60{tr('percent_unit')}", mode=tr('mode_auto'))))
    panel.battery_info_value.setText(str(tr("battery_display_format", policy=tr('mode_custom'), limit=f"80{tr('percent_unit')}")))

    sys.exit(app.exec())