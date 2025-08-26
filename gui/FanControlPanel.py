# gui/FanControlPanel.py
# -*- coding: utf-8 -*-
"""
Fan Control Panel QFrame - Pure View Component.
This class only holds widget references and updates them based on AppState.
UI creation and event handling are managed by UIBuilder and MainWindow respectively.
"""
from .qt import QFrame, Slot
from tools.localization import tr
from typing import TYPE_CHECKING
from .ui_builder import FanControls
from core.state import AppState

if TYPE_CHECKING:
    pass

class FanControlPanel(QFrame):
    """A pure view component for fan controls."""

    def __init__(self, controls: FanControls, parent=None):
        super().__init__(parent)
        self.controls = controls

    @Slot(object)
    def update_state(self, state: 'AppState'):
        """Updates the entire panel from the new AppState."""
        profile = state.profiles.get(state.active_profile_name)

        panel_enabled = profile is not None and state.is_panel_enabled
        is_custom_mode = panel_enabled and profile and profile.fan_mode == "custom"

        if profile:
            # Update radio buttons
            controls = self.controls
            controls.bios_fan_mode_radio.blockSignals(True)
            controls.auto_fan_mode_radio.blockSignals(True)
            controls.custom_fan_mode_radio.blockSignals(True)
            
            controls.bios_fan_mode_radio.setChecked(profile.fan_mode == "bios")
            controls.auto_fan_mode_radio.setChecked(profile.fan_mode == "auto")
            controls.custom_fan_mode_radio.setChecked(profile.fan_mode == "custom")
            
            controls.bios_fan_mode_radio.blockSignals(False)
            controls.auto_fan_mode_radio.blockSignals(False)
            controls.custom_fan_mode_radio.blockSignals(False)

            # Update slider and value label
            controls.custom_fan_speed_slider.blockSignals(True)
            controls.custom_fan_speed_slider.setValue(profile.custom_fan_speed)
            controls.custom_fan_speed_slider.blockSignals(False)
            controls.custom_fan_speed_value_label.setText(f"{profile.custom_fan_speed}{tr('percent_unit')}")
        
        # Set enabled state for all controls
        self.controls.fan_mode_label.setEnabled(panel_enabled)
        self.controls.bios_fan_mode_radio.setEnabled(panel_enabled)
        self.controls.auto_fan_mode_radio.setEnabled(panel_enabled)
        self.controls.custom_fan_mode_radio.setEnabled(panel_enabled)
        
        self.controls.custom_fan_speed_label.setEnabled(panel_enabled)
        self.controls.custom_fan_speed_slider.setEnabled(bool(is_custom_mode))
        self.controls.custom_fan_speed_value_label.setEnabled(bool(is_custom_mode))

    def retranslate_ui(self) -> None:
        """Retranslates all user-visible text in the panel."""
        self.controls.fan_mode_label.setText(tr("fan_mode_label"))
        self.controls.bios_fan_mode_radio.setText(tr("mode_bios"))
        self.controls.auto_fan_mode_radio.setText(tr("mode_auto"))
        self.controls.custom_fan_mode_radio.setText(tr("mode_custom"))
        self.controls.custom_fan_speed_label.setText(tr("custom_speed_label"))
        
        # Re-apply the current value to update the unit string
        value = self.controls.custom_fan_speed_slider.value()
        self.controls.custom_fan_speed_value_label.setText(f"{value}{tr('percent_unit')}")
