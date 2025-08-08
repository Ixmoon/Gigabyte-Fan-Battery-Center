# gui/StatusInfoPanel.py
# -*- coding: utf-8 -*-
"""
Status Information Panel QWidget for Fan & Battery Control.

Displays CPU/GPU temperatures, fan RPMs, battery info, and controller status.
"""
from .qt import QWidget, QGridLayout, QLabel, QFrame

from tools.localization import tr
from config.settings import TEMP_READ_ERROR_VALUE, RPM_READ_ERROR_VALUE

class StatusInfoPanel(QFrame):
    """
    A QFrame subclass that displays various system status information.
    """
    def __init__(self, parent: QWidget = None):
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

        self.cpu_temp_label = QLabel(tr("cpu_temp_label"))
        self.cpu_temp_value = QLabel(tr("value_not_available"))
        self.gpu_temp_label = QLabel(tr("gpu_temp_label"))
        self.gpu_temp_value = QLabel(tr("value_not_available"))
        self.fan1_rpm_label = QLabel(tr("fan1_rpm_label"))
        self.fan1_rpm_value = QLabel(tr("value_not_available"))
        self.fan2_rpm_label = QLabel(tr("fan2_rpm_label"))
        self.fan2_rpm_value = QLabel(tr("value_not_available"))
        self.applied_target_label = QLabel(tr("applied_target_label"))
        self.applied_target_value = QLabel(tr("value_not_available"))
        self.battery_info_label = QLabel(tr("battery_info_label"))
        self.battery_info_value = QLabel(tr("value_not_available"))

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

    def update_status(self, status_data: dict) -> None:
        """
        Updates the display labels with new status data.

        Args:
            status_data: A dictionary containing the status information.
                         Expected keys:
                         'cpu_temp', 'gpu_temp', 'fan1_rpm', 'fan2_rpm',
                         'applied_fan_percentage', 'theoretical_target_percentage',
                         'current_fan_mode', 'current_charge_policy',
                         'current_charge_threshold', 'controller_status_message'
        """
        # Temperatures
        cpu_temp = status_data.get('cpu_temp', TEMP_READ_ERROR_VALUE)
        gpu_temp = status_data.get('gpu_temp', TEMP_READ_ERROR_VALUE)
        cpu_temp_str = f"{cpu_temp:.1f}{tr('celsius_unit')}" if cpu_temp != TEMP_READ_ERROR_VALUE else tr("temp_error")
        gpu_temp_str = f"{gpu_temp:.1f}{tr('celsius_unit')}" if gpu_temp != TEMP_READ_ERROR_VALUE else tr("temp_error")
        self.cpu_temp_value.setText(cpu_temp_str)
        self.gpu_temp_value.setText(gpu_temp_str)

        # RPMs
        fan1_rpm = status_data.get('fan1_rpm', RPM_READ_ERROR_VALUE)
        fan2_rpm = status_data.get('fan2_rpm', RPM_READ_ERROR_VALUE)
        rpm1_str = f"{fan1_rpm}{tr('rpm_unit')}" if fan1_rpm != RPM_READ_ERROR_VALUE else tr("rpm_error")
        rpm2_str = f"{fan2_rpm}{tr('rpm_unit')}" if fan2_rpm != RPM_READ_ERROR_VALUE else tr("rpm_error")
        self.fan1_rpm_value.setText(rpm1_str)
        self.fan2_rpm_value.setText(rpm2_str)

        # Fan Speed / Target Display
        applied_speed = status_data.get('applied_fan_percentage', -1)
        target_speed = status_data.get('theoretical_target_percentage', -1)
        fan_mode = status_data.get('current_fan_mode', 'unknown')
 
        applied_speed_str = f"{applied_speed}{tr('percent_unit')}" if applied_speed != -1 else tr("value_not_available")
        target_speed_str = f"{target_speed}{tr('percent_unit')}" if target_speed != -1 else tr("value_not_available")
        
        fan_display_text = applied_speed_str
        if fan_mode == "auto":
            fan_display_text = tr("fan_display_auto_format", applied=applied_speed_str, target=target_speed_str, mode=tr('mode_auto'))
        elif fan_mode == "unknown":
            fan_display_text = tr("fan_display_error_format", error=tr('wmi_error'), mode=tr('unknown_mode'))
        self.applied_target_value.setText(fan_display_text)
 
        # Battery Info Display
        charge_policy = status_data.get('current_charge_policy')
        charge_threshold = status_data.get('current_charge_threshold', -1)
 
        policy_str = tr("policy_error")
        if charge_policy == "standard":
            policy_str = tr("mode_standard")
        elif charge_policy == "custom":
            policy_str = tr("mode_custom")
        elif charge_policy is None:
            policy_str = tr("unknown_mode")
 
        threshold_str = tr("threshold_error")
        if charge_threshold != -1:
            threshold_str = f"{charge_threshold}{tr('percent_unit')}"
        
        self.battery_info_value.setText(tr("battery_display_format", policy=policy_str, limit=threshold_str))

        # Controller Status Message is now handled by the title bar
        pass

    def retranslate_ui(self) -> None:
        """Retranslates all user-visible text in the panel."""
        self.cpu_temp_label.setText(tr("cpu_temp_label"))
        self.gpu_temp_label.setText(tr("gpu_temp_label"))
        self.fan1_rpm_label.setText(tr("fan1_rpm_label"))
        self.fan2_rpm_label.setText(tr("fan2_rpm_label"))
        self.applied_target_label.setText(tr("applied_target_label"))
        self.battery_info_label.setText(tr("battery_info_label"))
        # The value labels will be updated by update_status with translated units/errors
        # If there's an initial state that needs re-translation before first update_status,
        # check against the translated "not available" value.
        vna = tr("value_not_available")
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
        return _translations.get(current_lang, {}).get(key, key).format(**kwargs)

    app = QApplication(sys.argv)
    panel = StatusInfoPanel()
    panel.show()
    panel.resize(500, 150)

    # Example data to update the panel
    test_data_1 = {
        'cpu_temp': 65.5, 'gpu_temp': 72.1, 'fan1_rpm': 2500, 'fan2_rpm': 2800,
        'applied_fan_percentage': 60, 'theoretical_target_percentage': 65,
        'current_fan_mode': 'auto', 'current_charge_policy': 'custom',
        'current_charge_threshold': 80, 'controller_status_message': 'All systems nominal.'
    }
    test_data_2 = {
        'cpu_temp': TEMP_READ_ERROR_VALUE, 'gpu_temp': 55.0, 'fan1_rpm': RPM_READ_ERROR_VALUE, 'fan2_rpm': 0,
        'applied_fan_percentage': 0, 'theoretical_target_percentage': 0,
        'current_fan_mode': 'fixed', 'current_charge_policy': 'standard',
        'current_charge_threshold': 100, 'controller_status_message': 'CPU Temp Read Error.'
    }
    import functools
    from .qt import QTimer
    QTimer.singleShot(2000, functools.partial(panel.update_status, test_data_1))
    QTimer.singleShot(5000, functools.partial(panel.update_status, test_data_2))

    sys.exit(app.exec())