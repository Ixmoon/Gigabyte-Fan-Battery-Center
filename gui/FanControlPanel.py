# gui/FanControlPanel.py
# -*- coding: utf-8 -*-
"""
Fan Control Panel QWidget for Fan & Battery Control.

Contains controls for fan mode (Auto/Manual) and manual fan speed.
"""
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QRadioButton, QButtonGroup,
    QSlider, QSpacerItem, QSizePolicy, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, pyqtSlot # Added pyqtSlot

from tools.localization import tr
# from config.settings import DEFAULT_PROFILE_SETTINGS # No longer needed for initial speed
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from viewmodels.fan_control_viewmodel import FanControlViewModel


class FanControlPanel(QFrame):
    """
    A QFrame subclass that groups controls related to fan management.
    Interacts with a FanControlViewModel.
    """
    # Signals emitted by this panel are now minimal, as logic resides in ViewModel.
    # MainWindow might still listen for high-level signals if panels emit them,
    # or connect directly to ViewModel signals if VM is passed to MainWindow.
    # For now, assuming direct interaction with passed ViewModel.
    transient_status_signal = pyqtSignal(str) # For messages like "Applying settings"

    def __init__(self, view_model: 'FanControlViewModel', parent: QWidget = None):
        super().__init__(parent)
        self.setObjectName("fanControlFrame")
        self.view_model = view_model

        self._init_ui()
        self._connect_to_view_model()

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
        
        # Connect UI interaction to ViewModel slots
        self.auto_fan_mode_radio.toggled.connect(
            lambda checked: self.view_model.set_fan_mode("auto") if checked else None
        )
        self.manual_fan_mode_radio.toggled.connect(
            lambda checked: self.view_model.set_fan_mode("fixed") if checked else None
        )

        self.manual_fan_speed_label = QLabel(tr("manual_speed_label"))
        self.manual_fan_speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.manual_fan_speed_slider.setRange(0, 100)
        self.manual_fan_speed_slider.setTickInterval(10)
        self.manual_fan_speed_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        
        # Slider value changes are sent to VM upon release or direct value change (e.g. keyboard)
        self.manual_fan_speed_slider.valueChanged.connect(self._handle_slider_value_changed_for_label)
        self.manual_fan_speed_slider.sliderReleased.connect(
            lambda: self.view_model.set_fixed_speed(self.manual_fan_speed_slider.value())
        )
        # Consider also valueChanged if direct keyboard input should immediately trigger VM update
        # self.manual_fan_speed_slider.valueChanged.connect(self.view_model.set_fixed_speed) # More responsive

        self.manual_fan_speed_value_label = QLabel(f"---{tr('percent_unit')}")
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

        # Initialize UI from ViewModel state AFTER all elements are created and laid out
        self._update_fan_mode_display(self.view_model.get_current_fan_mode())
        # _update_fixed_speed_display updates both slider and its label from current_fixed_speed
        self._update_fixed_speed_display(self.view_model.get_current_fixed_speed())
        # _update_applied_speed_label is primarily for when actual hardware reported speed differs.
        # For init, current_fixed_speed is the best representation of desired state.
        # If applied_fixed_speed is significantly different at init (e.g. error state),
        # that would be handled by the first status update from AppRunner.
        # The call to _update_fixed_speed_display above already sets manual_fan_speed_value_label.
        # self._update_applied_speed_label(self.view_model.get_applied_fixed_speed()) # This might be redundant.

        # set_panel_enabled calls _update_slider_enable_state, which depends on UI elements and current mode.
        # It should be called after _update_fan_mode_display has set the initial mode.
        self.set_panel_enabled(self.view_model.is_panel_enabled())


    def _connect_to_view_model(self):
        """Connects ViewModel signals to panel slots."""
        self.view_model.fan_mode_updated.connect(self._update_fan_mode_display)
        self.view_model.fixed_speed_updated.connect(self._update_fixed_speed_display)
        self.view_model.applied_fixed_speed_updated.connect(self._update_applied_speed_label)
        self.view_model.panel_enabled_changed.connect(self.set_panel_enabled)
        self.view_model.fixed_speed_control_enabled_updated.connect(self._update_fixed_speed_controls_enabled)

    def _handle_slider_value_changed_for_label(self, value: int):
        """Updates the speed label next to the slider as it's dragged."""
        # This only updates the visual label during dragging/value change.
        # The actual command to change speed is sent on sliderReleased or if VM handles valueChanged directly.
        self.manual_fan_speed_value_label.setText(f"{value}{tr('percent_unit')}")
        # If ViewModel should be updated on every valueChanged (not just release):
        # self.view_model.set_fixed_speed(value)


    # --- Slots to update UI based on ViewModel changes ---
    @pyqtSlot(str)
    def _update_fan_mode_display(self, mode: str):
        """Updates radio buttons based on ViewModel state."""
        is_auto = (mode == "auto")
        self.auto_fan_mode_radio.blockSignals(True)
        self.manual_fan_mode_radio.blockSignals(True)
        
        self.auto_fan_mode_radio.setChecked(is_auto)
        self.manual_fan_mode_radio.setChecked(not is_auto)
        
        self.auto_fan_mode_radio.blockSignals(False)
        self.manual_fan_mode_radio.blockSignals(False)
        
        self._update_slider_enable_state(not is_auto and self.isEnabled())

    @pyqtSlot(int)
    def _update_fixed_speed_display(self, speed: int):
        """Updates the slider position and its immediate label based on ViewModel state."""
        self.manual_fan_speed_slider.blockSignals(True)
        self.manual_fan_speed_slider.setValue(speed)
        self.manual_fan_speed_slider.blockSignals(False)
        # Update the label next to the slider
        self.manual_fan_speed_value_label.setText(f"{speed}{tr('percent_unit')}")

    @pyqtSlot(int)
    def _update_applied_speed_label(self, applied_speed: int):
        """Updates the speed label to show the actual applied speed (could be different from slider)."""
        # This method is distinct if we want the label to specifically show *applied* speed
        # which might differ from the slider's *desired* speed until confirmation.
        # For simplicity, often the fixed_speed_updated might handle both slider and label.
        # If fixed_speed_updated already sets the label to the slider's value,
        # this one is for the case where hardware status confirms a different applied value.
        # For now, let's assume fixed_speed_updated sets the label to the slider value,
        # and this method is less critical if the ViewModel ensures they are usually in sync.
        # However, if the label is meant to show "actual %" from status, this is where it's set.
        # self.manual_fan_speed_value_label.setText(f"{applied_speed}{tr('percent_unit')}")
        pass # Assuming _update_fixed_speed_display also updates the label for simplicity for now.

    def _update_slider_enable_state(self, enabled: bool):
        """Enables/disables manual fan speed controls."""
        self.manual_fan_speed_label.setEnabled(enabled)
        self.manual_fan_speed_slider.setEnabled(enabled)
        # Value label is typically always enabled or its appearance handled by stylesheet.


    @pyqtSlot(bool)
    def _update_fixed_speed_controls_enabled(self, enabled: bool):
        """Enables/disables the fixed fan speed slider and its associated label."""
        # This specifically targets the slider and its direct label for the locking mechanism.
        # The overall panel_enabled state is handled by set_panel_enabled.
        # We only disable the slider if the panel itself is supposed to be enabled.
        if self.isEnabled(): # Check if the panel itself is enabled
            self.manual_fan_speed_label.setEnabled(enabled)
            self.manual_fan_speed_slider.setEnabled(enabled)
        # If panel is disabled, these should remain disabled regardless of 'enabled' param here.
        # However, if the panel is re-enabled, this slot might be called with 'true'
        # but the slider should only be enabled if also in 'fixed' mode.
        # This logic is better handled in conjunction with _update_slider_enable_state or set_panel_enabled.
        # For now, directly set based on 'enabled' but consider interaction with overall panel state.
        # A more robust approach might be:
        # if self.view_model.is_panel_enabled(): # Check VM's global enable state
        #    is_manual_mode = self.view_model.get_current_fan_mode() == "fixed"
        #    actual_slider_enabled_state = enabled and is_manual_mode
        #    self.manual_fan_speed_label.setEnabled(actual_slider_enabled_state)
        #    self.manual_fan_speed_slider.setEnabled(actual_slider_enabled_state)
        # else:
        #    self.manual_fan_speed_label.setEnabled(False)
        #    self.manual_fan_speed_slider.setEnabled(False)
        # Simpler for now:
        # self.manual_fan_speed_label.setEnabled(enabled)
        # self.manual_fan_speed_slider.setEnabled(enabled)
        # The `set_panel_enabled` method will correctly call `_update_slider_enable_state`
        # which considers the fan mode. This slot should purely reflect the `enabled` state
        # from the ViewModel signal for the lock.
        self.manual_fan_speed_slider.setEnabled(enabled)
        # The label's enabled state can also follow this, or be tied to the slider's state.
        self.manual_fan_speed_label.setEnabled(enabled)


    @pyqtSlot(bool)
    def set_panel_enabled(self, enabled: bool) -> None:
        """Globally enables or disables all controls in this panel based on ViewModel."""
        self.fan_mode_label.setEnabled(enabled)
        self.auto_fan_mode_radio.setEnabled(enabled)
        self.manual_fan_mode_radio.setEnabled(enabled)
        
        # Slider enable state depends on both global panel enable AND fan mode
        current_fan_mode = self.view_model.get_current_fan_mode() # Get from VM
        is_manual_mode_active = (current_fan_mode == "fixed")
        
        self._update_slider_enable_state(enabled and is_manual_mode_active)


    def retranslate_ui(self) -> None:
        """Retranslates all user-visible text in the panel."""
        self.fan_mode_label.setText(tr("fan_mode_label"))
        self.auto_fan_mode_radio.setText(tr("mode_auto"))
        self.manual_fan_mode_radio.setText(tr("mode_manual"))
        self.manual_fan_speed_label.setText(tr("manual_speed_label"))
        
        # Update speed value label using current value from slider (or VM) and new unit
        current_slider_val = self.manual_fan_speed_slider.value()
        self.manual_fan_speed_value_label.setText(f"{current_slider_val}{tr('percent_unit')}")


if __name__ == '__main__':
    # Example Usage
    import sys
    from PyQt6.QtWidgets import QApplication, QMainWindow

    _translations = {
        "en": {
            "fan_mode_label": "Fan Mode:", "mode_auto": "Auto", "mode_manual": "Manual",
            "manual_speed_label": "Manual Speed:", "percent_unit": "%"
        },
        # Add a dummy fallback for retranslate_ui test
        "_fallback": {"percent_unit": "%"}
    }
    current_lang = "en"
    def tr(key, **kwargs):
        _fallback = kwargs.pop('_fallback', False)
        if _fallback: # for testing retranslate where previous unit might not be in current lang dict
            return _translations.get("_fallback", {}).get(key, key).format(**kwargs)
        return _translations.get(current_lang, {}).get(key, key).format(**kwargs)


    app = QApplication(sys.argv)
    main_win = QMainWindow()
    panel = FanControlPanel(initial_mode="fixed", initial_speed=50)

    def print_fan_mode(mode):
        print(f"Fan mode changed to: {mode}")
        panel.set_fixed_speed(panel.manual_fan_speed_slider.value(), panel.manual_fan_speed_slider.value()) # reflect change

    def print_fixed_speed(speed):
        print(f"Fixed speed changed to: {speed}%")
        # In a real app, AppRunner would send back the actual applied speed
        panel.set_fixed_speed(speed, speed)


    panel.fan_mode_changed_signal.connect(print_fan_mode)
    panel.fixed_speed_changed_signal.connect(print_fixed_speed)

    main_win.setCentralWidget(panel)
    main_win.show()
    main_win.resize(500, 100)

    # Test programmatic updates
    def test_updates():
        print("Testing programmatic updates...")
        panel.set_fan_mode("auto")
        # Simulate status update from AppRunner/ViewModel
        panel.set_fixed_speed(30, 30) # Slider should update if mode was fixed
                                      # Label always updates with applied speed
        QTimer.singleShot(2000, lambda: panel.set_fan_mode("fixed"))
        QTimer.singleShot(2500, lambda: panel.set_fixed_speed(75, 75)) # Update slider to 75, label to 75%

    QTimer.singleShot(3000, test_updates)


    sys.exit(app.exec())