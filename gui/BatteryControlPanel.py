# gui/BatteryControlPanel.py
# -*- coding: utf-8 -*-
"""
Battery Control Panel QFrame - Pure View Component.
This class only holds widget references and updates them based on AppState.
UI creation and event handling are managed by UIBuilder and MainWindow respectively.
"""
from .qt import QFrame, Slot
from typing import TYPE_CHECKING
from tools.localization import tr
from core.state import CHARGE_POLICY_CUSTOM, AppState
from .ui_builder import BatteryControls

if TYPE_CHECKING:
    pass

class BatteryControlPanel(QFrame):
    """A pure view component for battery controls."""

    def __init__(self, controls: BatteryControls, parent=None):
        super().__init__(parent)
        self.controls = controls

    @Slot(object)
    def update_state(self, state: 'AppState'):
        """Updates the entire panel from the new AppState."""
        profile = state.profiles.get(state.active_profile_name)
        if not profile:
            return

        # Block signals to prevent feedback loops
        self.controls.charge_policy_button_group.blockSignals(True)
        self.controls.charge_threshold_slider.blockSignals(True)

        # Determine enabled states
        panel_enabled = state.is_panel_enabled
        is_custom_mode = panel_enabled and profile.battery_charge_policy == CHARGE_POLICY_CUSTOM

        # Update radio buttons
        if is_custom_mode:
            self.controls.custom_charge_radio.setChecked(True)
        else:
            self.controls.bios_charge_radio.setChecked(True)

        # Update slider and value label
        self.controls.charge_threshold_slider.setValue(profile.battery_charge_threshold)
        self.controls.charge_threshold_value_label.setText(f"{profile.battery_charge_threshold}{tr('percent_unit')}")

        # Set enabled state for all controls
        self.controls.charge_policy_label.setEnabled(panel_enabled)
        self.controls.bios_charge_radio.setEnabled(panel_enabled)
        self.controls.custom_charge_radio.setEnabled(panel_enabled)
        
        self.controls.charge_threshold_label.setEnabled(panel_enabled)
        self.controls.charge_threshold_slider.setEnabled(bool(is_custom_mode))
        self.controls.charge_threshold_value_label.setEnabled(bool(is_custom_mode))

        # Unblock signals
        self.controls.charge_policy_button_group.blockSignals(False)
        self.controls.charge_threshold_slider.blockSignals(False)

    def retranslate_ui(self) -> None:
        """Retranslates all user-visible text in the panel."""
        self.controls.charge_policy_label.setText(tr("charge_policy_label"))
        self.controls.bios_charge_radio.setText(tr("mode_bios"))
        self.controls.bios_charge_radio.setToolTip(tr("policy_bios_tooltip"))
        self.controls.custom_charge_radio.setText(tr("mode_custom"))
        self.controls.custom_charge_radio.setToolTip(tr("policy_custom_tooltip"))
        self.controls.charge_threshold_label.setText(tr("charge_threshold_label"))
        self.controls.charge_threshold_slider.setToolTip(tr("threshold_slider_tooltip"))
        
        # Re-apply the current value to update the unit string
        value = self.controls.charge_threshold_slider.value()
        self.controls.charge_threshold_value_label.setText(f"{value}{tr('percent_unit')}")
