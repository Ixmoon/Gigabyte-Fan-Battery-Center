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
from .base_control_panel import BaseControlPanel
from typing import TYPE_CHECKING

from tools.localization import tr

if TYPE_CHECKING:
    from viewmodels.battery_control_viewmodel import BatteryControlViewModel


class BatteryControlPanel(BaseControlPanel['BatteryControlViewModel']):
    """
    A QFrame subclass that groups controls related to battery management.
    Inherits from BaseControlPanel to reduce boilerplate.
    """
    def __init__(self, view_model: 'BatteryControlViewModel', parent: QWidget = None):
        """
        Initializes the BatteryControlPanel.
        """
        super().__init__(view_model, parent)
        self.setObjectName("batteryControlFrame")

    def _init_ui(self) -> None:
        """
        Initializes the UI elements for the battery control panel.
        Gets initial values from the ViewModel.
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
        # Connect to ViewModel method
        self.charge_policy_button_group.buttonToggled.connect(self._handle_policy_radio_toggled)

        self.charge_threshold_label = QLabel(tr("charge_threshold_label"))
        self.charge_threshold_slider = QSlider(Qt.Orientation.Horizontal)
        # Assuming ViewModel has min_threshold and max_threshold properties or getters
        min_thresh = getattr(self.view_model, 'min_threshold', 0) # Default if not present
        max_thresh = getattr(self.view_model, 'max_threshold', 100) # Default if not present
        self.charge_threshold_slider.setRange(min_thresh, max_thresh)
        self.charge_threshold_slider.setTickInterval(10)
        self.charge_threshold_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.charge_threshold_slider.setToolTip(tr("threshold_slider_tooltip"))

        self.charge_threshold_value_label = QLabel() # Text set by _update_charge_threshold_display
        self.charge_threshold_value_label.setMinimumWidth(45) # Consistent width
        self.charge_threshold_value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.charge_threshold_value_label.setObjectName("charge_threshold_value_label") # For styling

        # Connect to ViewModel methods before setting initial state that might trigger them
        self.charge_threshold_slider.sliderReleased.connect(self._handle_slider_released)
        self.charge_threshold_slider.valueChanged.connect(self._handle_slider_value_changed_by_user) # For live label update

        layout.addWidget(self.charge_policy_label)
        layout.addWidget(self.standard_charge_radio)
        layout.addWidget(self.custom_charge_radio)
        layout.addSpacerItem(QSpacerItem(20, 10, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))
        layout.addWidget(self.charge_threshold_label)
        layout.addWidget(self.charge_threshold_slider, 1) # Slider takes stretch factor
        layout.addWidget(self.charge_threshold_value_label)

        # Set initial state from ViewModel AFTER all UI elements are created
        self._update_charge_policy_display(self.view_model.get_current_charge_policy())
        # Call the internal update method with all necessary initial data
        self._update_charge_threshold_display_internal(
            self.view_model.get_current_charge_threshold(), # For UI slider position
            self.view_model.get_applied_charge_threshold(), # For actual value display
            self.view_model.get_current_charge_policy() == "custom" # is_custom_mode
        )
        # _update_charge_limit_controls_enabled is called by _update_charge_policy_display,
        # so it will also be correctly called after elements are created.
        # Explicit call to _update_charge_limit_controls_enabled(self.view_model.current_policy == "custom") is removed from here
        # as _update_charge_policy_display will handle it.

    def _connect_to_view_model(self) -> None:
        """Connects signals from the ViewModel to panel slots."""
        self.view_model.charge_policy_updated.connect(self._update_charge_policy_display)
        self.view_model.charge_threshold_updated.connect(self._slot_for_ui_threshold_updated) # Connect to a new intermediate slot
        self.view_model.charge_limit_control_enabled_updated.connect(self._update_charge_limit_controls_enabled)
        # Corrected signal name and connection to a new slot that queries current policy
        self.view_model.applied_charge_threshold_updated.connect(self._handle_applied_threshold_update_from_vm)
        self.view_model.threshold_slider_lock_updated.connect(self._update_threshold_slider_lock_state)
        self.view_model.panel_enabled_changed.connect(self.set_panel_enabled)


    @Slot(int) # New slot to handle applied_charge_threshold_updated signal
    def _handle_applied_threshold_update_from_vm(self, applied_threshold: int):
        """Handles updates to the applied threshold from the ViewModel."""
        is_custom = self.view_model.get_current_charge_policy() == "custom"
        self._update_actual_threshold_display_only(applied_threshold, is_custom)

    def _handle_policy_radio_toggled(self, button: QRadioButton, checked: bool) -> None:
        if checked:
            new_policy = "standard" if button == self.standard_charge_radio else "custom"
            # Potentially emit transient status before calling ViewModel,
            # if VM call is expected to take time or involve hardware.
            # self.transient_status_signal.emit(tr("applying_settings")) # Example
            self.view_model.set_charge_policy(new_policy)

    def _handle_slider_released(self) -> None:
        if self.view_model.get_current_charge_policy() == "custom":
            # self.transient_status_signal.emit(tr("applying_settings")) # Example
            self.view_model.set_charge_threshold(self.charge_threshold_slider.value())

    def _handle_slider_value_changed_by_user(self, value: int) -> None:
        """Updates the value label as the slider moves, only if in custom mode."""
        is_custom_mode = self.view_model.get_current_charge_policy() == "custom"
        value_text = f"{value}{tr('percent_unit')}"
        self.charge_threshold_value_label.setText(value_text if is_custom_mode else f"({value_text})")
        # If slider is moved by user, and not programmatically, ViewModel might want to know for live updates
        # For now, only sliderReleased signals change to ViewModel.

    def _update_charge_policy_display(self, policy: str) -> None:
        """Updates the radio buttons based on the ViewModel's policy."""
        self.charge_policy_button_group.blockSignals(True)
        if policy == "standard":
            self.standard_charge_radio.setChecked(True)
        elif policy == "custom":
            self.custom_charge_radio.setChecked(True)
        self.charge_policy_button_group.blockSignals(False)
        self._update_charge_limit_controls_enabled(policy == "custom")

    @Slot(int) # Slot for charge_threshold_updated signal (which carries ui_threshold)
    def _slot_for_ui_threshold_updated(self, ui_threshold: int) -> None:
        """Handles updates to the UI-driven threshold (e.g., slider position)."""
        # Get other needed info from ViewModel
        actual_threshold = self.view_model.get_applied_charge_threshold()
        is_custom_mode = self.view_model.get_current_charge_policy() == "custom"
        self._update_charge_threshold_display_internal(ui_threshold, actual_threshold, is_custom_mode)

    # Renamed original method to avoid signature conflict and clarify purpose
    def _update_charge_threshold_display_internal(self, ui_threshold: int, actual_threshold: int, is_custom_mode: bool) -> None:
        """
        Internal method to update the charge threshold slider and label.
        The slider shows the 'ui_threshold' (what the user wants or profile has).
        The label shows the 'actual_threshold' (what the system reports).
        """
        self.charge_threshold_slider.blockSignals(True)
        self.charge_threshold_slider.setValue(ui_threshold)
        self.charge_threshold_slider.blockSignals(False)
        
        value_text = f"{actual_threshold}{tr('percent_unit')}"
        # If not custom mode, the label should reflect the ui_threshold (slider position) as that's what user is setting,
        # even if it's not 'applied' in the same way. Or show applied if truly different.
        # For now, let's make the label always show actual_threshold, and parentheses indicate non-custom mode.
        self.charge_threshold_value_label.setText(value_text if is_custom_mode else f"({value_text})")


    def _update_actual_threshold_display_only(self, actual_threshold: int, is_custom_mode: bool) -> None:
        """
        Only updates the text label for the actual threshold, typically from a status update,
        without altering the slider's position (which represents user intent or profile setting).
        """
        value_text = f"{actual_threshold}{tr('percent_unit')}"
        self.charge_threshold_value_label.setText(value_text if is_custom_mode else f"({value_text})")


    def _update_charge_limit_controls_enabled(self, enabled: bool) -> None:
        """Enables/disables threshold controls based on ViewModel state (custom policy)."""
        self.charge_threshold_label.setEnabled(enabled)
        self.charge_threshold_slider.setEnabled(enabled)
        # Refresh label text to reflect enabled state (parentheses or not)
        # This assumes the text format is based on 'is_custom_mode'
        current_text = self.charge_threshold_value_label.text()
        if enabled and current_text.startswith("(") and current_text.endswith(")"):
            self.charge_threshold_value_label.setText(current_text[1:-1])
        elif not enabled and not (current_text.startswith("(") and current_text.endswith(")")):
            self.charge_threshold_value_label.setText(f"({current_text})")

    @Slot(bool)
    def _update_threshold_slider_lock_state(self, locked: bool) -> None:
        """
        Locks or unlocks the charge threshold slider.
        Note: 'locked' is True to lock (disable), False to unlock (enable).
        The ViewModel signal threshold_slider_lock_updated emits False to disable (lock), True to enable (unlock).
        So, we need to invert the boolean if interpreting 'locked' as 'should_be_locked'.
        Let's assume the signal means: True = slider enabled, False = slider disabled.
        """
        slider_should_be_enabled = locked # Assuming 'locked' signal means 'is_unlocked_and_enabled'
        
        # Only change enabled state if the panel itself is enabled and it's custom mode
        if self.isEnabled() and self.view_model.get_current_charge_policy() == "custom":
            self.charge_threshold_slider.setEnabled(slider_should_be_enabled)
            # The label's enabled state usually follows the slider or overall control group
            self.charge_threshold_label.setEnabled(slider_should_be_enabled)
        elif not self.isEnabled() or self.view_model.get_current_charge_policy() != "custom":
            # If panel is disabled or not in custom mode, slider should remain disabled
            self.charge_threshold_slider.setEnabled(False)
            self.charge_threshold_label.setEnabled(False)


    def set_panel_enabled(self, enabled: bool) -> None:
        """Globally enables or disables all controls in this panel."""
        self.standard_charge_radio.setEnabled(enabled)
        self.custom_charge_radio.setEnabled(enabled)
        if enabled:
            # When re-enabling the panel, defer to the ViewModel's state for threshold controls
            is_custom = self.view_model.get_current_charge_policy() == "custom"
            # Assuming charge_limit_controls_enabled is a property or getter in ViewModel
            limit_controls_enabled = getattr(self.view_model, 'charge_limit_controls_enabled', is_custom)
            self._update_charge_limit_controls_enabled(is_custom and limit_controls_enabled)
        else: # If globally disabling, ensure slider and its label are also disabled
            self.charge_threshold_label.setEnabled(False)
            self.charge_threshold_slider.setEnabled(False)

    def retranslate_ui(self) -> None:
        """Retranslates all user-visible text in the panel."""
        self.charge_policy_label.setText(tr("charge_policy_label"))
        self.standard_charge_radio.setText(tr("mode_standard"))
        self.standard_charge_radio.setToolTip(tr("policy_standard_tooltip"))
        self.custom_charge_radio.setText(tr("mode_custom"))
        self.custom_charge_radio.setToolTip(tr("policy_custom_tooltip"))
        self.charge_threshold_label.setText(tr("charge_threshold_label"))
        self.charge_threshold_slider.setToolTip(tr("threshold_slider_tooltip"))

        # Robustly update threshold value label from the ViewModel, not by parsing the UI.
        val = self.view_model.get_applied_charge_threshold()
        is_custom_mode = self.view_model.get_current_charge_policy() == "custom"
        
        if val >= 0: # Check for valid value
            self.charge_threshold_value_label.setText(f"{val}{tr('percent_unit')}" if is_custom_mode else f"({val}{tr('percent_unit')})")
        else:
            self.charge_threshold_value_label.setText(tr("value_not_available"))

