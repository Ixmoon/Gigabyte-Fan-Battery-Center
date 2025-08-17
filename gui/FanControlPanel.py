# gui/FanControlPanel.py
# -*- coding: utf-8 -*-
"""
Fan Control Panel QWidget for Fan & Battery Control.

Contains controls for fan mode (Auto/Manual) and manual fan speed.
"""
from .qt import (
    QWidget, QHBoxLayout, QLabel, QRadioButton, QButtonGroup,
    QSlider, QSpacerItem, QSizePolicy, QFrame, Qt, Slot
)
from tools.localization import tr
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from core.app_services import AppServices
    from core.state import AppState


class FanControlPanel(QFrame):
    """
    A QFrame subclass that groups controls related to fan management.
    It directly interacts with AppServices.
    """
    def __init__(self, app_services: 'AppServices', parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.app_services = app_services
        self.setObjectName("fanControlFrame")
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(10)

        self.fan_mode_label = QLabel(tr("fan_mode_label"))
        self.auto_fan_mode_radio = QRadioButton(tr("mode_auto"))
        self.manual_fan_mode_radio = QRadioButton(tr("mode_manual"))

        self.fan_mode_button_group = QButtonGroup(self)
        self.fan_mode_button_group.addButton(self.auto_fan_mode_radio) # ID not strictly needed now
        self.fan_mode_button_group.addButton(self.manual_fan_mode_radio)
        
        # Connect UI interaction directly to AppServices
        self.auto_fan_mode_radio.toggled.connect(
            lambda checked: self.app_services.set_fan_mode("auto") if checked else None
        )
        self.manual_fan_mode_radio.toggled.connect(
            lambda checked: self.app_services.set_fan_mode("fixed") if checked else None
        )

        self.manual_fan_speed_label = QLabel(tr("manual_speed_label"))
        self.manual_fan_speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.manual_fan_speed_slider.setRange(0, 100)
        self.manual_fan_speed_slider.setTickInterval(10)
        self.manual_fan_speed_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        
        # Slider value changes are sent to AppServices upon release
        self.manual_fan_speed_slider.valueChanged.connect(self._handle_slider_value_changed_for_label)
        self.manual_fan_speed_slider.sliderReleased.connect(
            lambda: self.app_services.set_fixed_fan_speed(self.manual_fan_speed_slider.value())
        )
 
        self.manual_fan_speed_value_label = QLabel(tr("value_not_available"))
        self.manual_fan_speed_value_label.setMinimumWidth(45)
        self.manual_fan_speed_value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.manual_fan_speed_value_label.setObjectName("manual_speed_value_label")

        layout.addWidget(self.fan_mode_label)
        layout.addWidget(self.auto_fan_mode_radio)
        layout.addWidget(self.manual_fan_mode_radio)
        layout.addSpacerItem(QSpacerItem(20, 10, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))
        layout.addWidget(self.manual_fan_speed_label)
        layout.addWidget(self.manual_fan_speed_slider, 1)
        layout.addWidget(self.manual_fan_speed_value_label)

        # UI initialization is now handled by the first call to update_state().

    def update_state(self, state: 'AppState'):
        """Updates the entire panel from the new AppState."""
        profile = state.profiles.get(state.active_profile_name)

        if not profile:
            self.set_panel_enabled(False)
            return

        # Always enable the panel, but specific controls are managed below
        self.set_panel_enabled(True)
        self._update_fan_mode_display(profile.fan_mode)
        self._update_fixed_speed_display(profile.fixed_fan_speed)
        
        # Enable fixed speed controls only when in fixed mode
        is_fixed_mode = (profile.fan_mode == "fixed")
        self._update_fixed_speed_controls_enabled(is_fixed_mode)

    def _handle_slider_value_changed_for_label(self, value: int):
        """Updates the speed label next to the slider as it's dragged."""
        # This only updates the visual label during dragging/value change.
        # The actual command to change speed is sent on sliderReleased or if VM handles valueChanged directly.
        self.manual_fan_speed_value_label.setText(f"{value}{tr('percent_unit')}")

    # --- Slots to update UI based on state changes ---
    def _update_fan_mode_display(self, mode: str):
        """Updates radio buttons based on ViewModel state."""
        is_auto = (mode == "auto")
        self.auto_fan_mode_radio.blockSignals(True)
        self.manual_fan_mode_radio.blockSignals(True)
        
        self.auto_fan_mode_radio.setChecked(is_auto)
        self.manual_fan_mode_radio.setChecked(not is_auto)
        
        self.auto_fan_mode_radio.blockSignals(False)
        self.manual_fan_mode_radio.blockSignals(False)

    def _update_fixed_speed_display(self, speed: int):
        """Updates the slider position and its immediate label based on ViewModel state."""
        self.manual_fan_speed_slider.blockSignals(True)
        self.manual_fan_speed_slider.setValue(speed)
        self.manual_fan_speed_slider.blockSignals(False)
        # Update the label next to the slider
        self.manual_fan_speed_value_label.setText(f"{speed}{tr('percent_unit')}")

    def _update_fixed_speed_controls_enabled(self, enabled: bool):
        """Enables/disables the fixed fan speed slider and its associated label."""
        # This is now a simple pass-through controlled by the main update_state logic
        self.manual_fan_speed_label.setEnabled(enabled)
        self.manual_fan_speed_slider.setEnabled(enabled)

    def set_panel_enabled(self, enabled: bool) -> None:
        """Globally enables or disables all controls in this panel."""
        self.fan_mode_label.setEnabled(enabled)
        self.auto_fan_mode_radio.setEnabled(enabled)
        self.manual_fan_mode_radio.setEnabled(enabled)

        # The logic to enable/disable the slider is now in update_state.
        # For a simple global disable, we can disable them here too.
        if not enabled:
            self._update_fixed_speed_controls_enabled(False)
        # When re-enabling, update_state will handle the detailed logic.

    def retranslate_ui(self) -> None:
        """Retranslates all user-visible text in the panel."""
        self.fan_mode_label.setText(tr("fan_mode_label"))
        self.auto_fan_mode_radio.setText(tr("mode_auto"))
        self.manual_fan_mode_radio.setText(tr("mode_manual"))
        self.manual_fan_speed_label.setText(tr("manual_speed_label"))
        
        # Robustly update speed value label from the AppState
        if self.app_services and self.app_services.state:
            profile = self.app_services.state.profiles.get(self.app_services.state.active_profile_name)
            if profile:
                current_speed = profile.fixed_fan_speed
                self.manual_fan_speed_value_label.setText(f"{current_speed}{tr('percent_unit')}")

