# gui/BatteryControlPanel.py
# -*- coding: utf-8 -*-
"""
Battery Control Panel QWidget for Fan & Battery Control.

Contains controls for charge policy (Standard/Custom) and custom charge threshold.
"""
from .qt import (
    QWidget, QHBoxLayout, QLabel, QRadioButton, QButtonGroup,
    QSlider, QSpacerItem, QSizePolicy, QFrame, Qt, Slot
)
from typing import TYPE_CHECKING, Optional

from tools.localization import tr
from core.state import AppState, CHARGE_POLICY_STANDARD, CHARGE_POLICY_CUSTOM


if TYPE_CHECKING:
    from core.app_services import AppServices


class BatteryControlPanel(QFrame):
    """
    A QFrame subclass that groups controls related to battery management.
    Inherits from BaseControlPanel and interacts directly with AppServices.
    """
    def __init__(self, app_services: 'AppServices', parent: Optional[QWidget] = None):
        """
        Initializes the BatteryControlPanel.
        """
        super().__init__(parent)
        self.app_services = app_services
        self.setObjectName("batteryControlFrame")
        self._init_ui()
        self._connect_signals()

    def _init_ui(self) -> None:
        """
        Initializes the UI elements for the battery control panel.
        """
        layout = QHBoxLayout(self) # Main layout for this panel
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(10)

        self.charge_policy_label = QLabel(tr("charge_policy_label"))
        self.standard_charge_radio = QRadioButton(tr("mode_standard"))
        self.standard_charge_radio.setToolTip(tr("policy_standard_tooltip"))
        self.custom_charge_radio = QRadioButton(tr("mode_custom"))
        self.custom_charge_radio.setToolTip(tr("policy_custom_tooltip"))

        self.charge_policy_button_group = QButtonGroup(self)
        self.charge_policy_button_group.addButton(self.standard_charge_radio) # No explicit ID needed if using object
        self.charge_policy_button_group.addButton(self.custom_charge_radio)

        self.charge_threshold_label = QLabel(tr("charge_threshold_label"))
        self.charge_threshold_slider = QSlider(Qt.Orientation.Horizontal)
        # Constants are now used directly
        self.charge_threshold_slider.setRange(60, 100)
        self.charge_threshold_slider.setTickInterval(5)
        self.charge_threshold_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.charge_threshold_slider.setToolTip(tr("threshold_slider_tooltip"))

        self.charge_threshold_value_label = QLabel() # Text set by _update_charge_threshold_display
        self.charge_threshold_value_label.setMinimumWidth(45) # Consistent width
        self.charge_threshold_value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.charge_threshold_value_label.setObjectName("charge_threshold_value_label") # For styling

        # Signal connections are handled in _connect_signals
        layout.addWidget(self.charge_policy_label)
        layout.addWidget(self.standard_charge_radio)
        layout.addWidget(self.custom_charge_radio)
        layout.addSpacerItem(QSpacerItem(20, 10, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))
        layout.addWidget(self.charge_threshold_label)
        layout.addWidget(self.charge_threshold_slider, 1)
        layout.addWidget(self.charge_threshold_value_label)

    def _connect_signals(self) -> None:
        """Connects UI element signals to AppServices."""
        self.charge_policy_button_group.buttonToggled.connect(self._handle_policy_radio_toggled)
        self.charge_threshold_slider.sliderReleased.connect(self._handle_slider_released)
        self.charge_threshold_slider.valueChanged.connect(self._update_slider_label)

    def update_state(self, state: AppState):
        """Updates the entire panel from the new AppState."""
        profile = state.profiles.get(state.active_profile_name)
        if not profile:
            return

        # Block signals to prevent feedback loops during state updates
        self.charge_policy_button_group.blockSignals(True)
        self.charge_threshold_slider.blockSignals(True)

        # Update Charge Policy Radio Buttons
        is_custom_mode = profile.battery_charge_policy == CHARGE_POLICY_CUSTOM
        if is_custom_mode:
            self.custom_charge_radio.setChecked(True)
        else:
            self.standard_charge_radio.setChecked(True)

        # Update Threshold Slider and Label
        self.charge_threshold_slider.setValue(profile.battery_charge_threshold)
        value_text = f"{profile.battery_charge_threshold}{tr('percent_unit')}"
        self.charge_threshold_value_label.setText(value_text)

        # Update Enabled/Disabled State
        panel_enabled = state.is_panel_enabled
        self.standard_charge_radio.setEnabled(panel_enabled)
        self.custom_charge_radio.setEnabled(panel_enabled)
        
        controls_enabled = panel_enabled and is_custom_mode
        self.charge_threshold_label.setEnabled(controls_enabled)
        self.charge_threshold_slider.setEnabled(controls_enabled)
        self.charge_threshold_value_label.setEnabled(controls_enabled)

        # Unblock signals
        self.charge_policy_button_group.blockSignals(False)
        self.charge_threshold_slider.blockSignals(False)

    def _handle_policy_radio_toggled(self, button: QRadioButton, checked: bool) -> None:
        """Handles user interaction with the charge policy radio buttons."""
        if checked:
            new_policy = CHARGE_POLICY_CUSTOM if button == self.custom_charge_radio else CHARGE_POLICY_STANDARD
            self.app_services.set_battery_charge_policy(new_policy)

    def _handle_slider_released(self) -> None:
        """Handles user releasing the charge threshold slider."""
        new_threshold = self.charge_threshold_slider.value()
        self.app_services.set_battery_charge_threshold(new_threshold)

    def _update_slider_label(self, value: int) -> None:
        """Updates the value label as the slider moves."""
        self.charge_threshold_value_label.setText(f"{value}{tr('percent_unit')}")

    def retranslate_ui(self) -> None:
        """Retranslates all user-visible text in the panel."""
        self.charge_policy_label.setText(tr("charge_policy_label"))
        self.standard_charge_radio.setText(tr("mode_standard"))
        self.standard_charge_radio.setToolTip(tr("policy_standard_tooltip"))
        self.custom_charge_radio.setText(tr("mode_custom"))
        self.custom_charge_radio.setToolTip(tr("policy_custom_tooltip"))
        self.charge_threshold_label.setText(tr("charge_threshold_label"))
        self.charge_threshold_slider.setToolTip(tr("threshold_slider_tooltip"))
        
        # Re-apply the current value to update the unit string, if needed
        self._update_slider_label(self.charge_threshold_slider.value())

