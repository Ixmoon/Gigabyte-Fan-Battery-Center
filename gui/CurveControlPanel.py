# gui/CurveControlPanel.py
# -*- coding: utf-8 -*-
"""
Curve Control Panel QFrame - View Component with dynamic UI logic.
"""
from .qt import (
    QFrame, QPushButton, QInputDialog, QMessageBox,
    Signal, Qt, QEvent, QObject, QLineEdit, QMouseEvent, Slot, QHBoxLayout
)
from typing import List, Optional, TYPE_CHECKING, cast
from tools.localization import tr
from .ui_builder import CurveControls
from core.state import AppState
from core.app_services import AppServices

if TYPE_CHECKING:
    pass

class CurveControlPanel(QFrame):
    """
    A view component for curve and profile management. It handles dynamic
    creation of profile buttons and their specific interactions.
    """
    transient_status_signal = Signal(str)

    def __init__(self, controls: CurveControls, app_services: 'AppServices', parent=None):
        super().__init__(parent)
        self.controls = controls
        self.app_services = app_services
        self.profile_buttons: List[QPushButton] = []
        
        # Connect signals for static controls
        self.controls.curve_button_group.buttonClicked.connect(self._handle_curve_type_button_clicked)
        self.controls.profile_button_group.buttonClicked.connect(self._handle_profile_button_left_clicked)
        self.controls.start_on_boot_checkbox.toggled.connect(self._handle_start_on_boot_toggled)
        self.controls.reset_curve_button.clicked.connect(self._handle_reset_curve_button_clicked)

    @Slot(object)
    def update_state(self, state: 'AppState'):
        """Updates the entire panel from the new AppState."""
        self.setEnabled(state.is_panel_enabled)

        # Update static controls
        self._update_curve_type_display(state.active_curve_type)
        self._update_start_on_boot_display(state.start_on_boot)
        
        # Dynamically rebuild profile buttons
        self._rebuild_profile_buttons(list(state.profiles.keys()), state.active_profile_name)

    def _rebuild_profile_buttons(self, profile_names: List[str], active_profile_name: Optional[str]) -> None:
        """Clears and recreates profile buttons."""
        controls_layout = self.controls.controls_layout

        for button in self.profile_buttons:
            self.controls.profile_button_group.removeButton(button)
            controls_layout.removeWidget(button)
            button.deleteLater()
        self.profile_buttons.clear()

        insert_idx = 3 # After CPU/GPU buttons and spacer
        for i, profile_name in enumerate(profile_names):
            button = QPushButton(profile_name)
            button.setCheckable(True)
            button.setToolTip(tr("profile_button_tooltip"))
            button.setObjectName(f"profileButton_{i}")
            button.setProperty("profile_name", profile_name)
            button.installEventFilter(self)

            self.profile_buttons.append(button)
            self.controls.profile_button_group.addButton(button)
            controls_layout.insertWidget(insert_idx + i, button)

            if profile_name == active_profile_name:
                button.setChecked(True)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if isinstance(obj, QPushButton) and obj in self.profile_buttons:
            if event.type() == QEvent.Type.MouseButtonDblClick:
                self._handle_profile_button_double_click(obj)
                return True
            elif event.type() == QEvent.Type.MouseButtonPress and isinstance(event, QMouseEvent) and event.button() == Qt.MouseButton.RightButton:
                self._handle_profile_button_right_click(obj)
                return True
        return super().eventFilter(obj, event)

    def _handle_curve_type_button_clicked(self, button: QPushButton) -> None:
        curve_type = 'cpu' if button == self.controls.cpu_curve_button else 'gpu'
        self.app_services.set_active_curve_type(curve_type)

    def _handle_profile_button_left_clicked(self, button: QPushButton) -> None:
        if button.isChecked():
            profile_name = button.property("profile_name")
            if profile_name:
                self.app_services.activate_profile(profile_name)

    def _handle_start_on_boot_toggled(self, checked: bool) -> None:
        self.app_services.set_start_on_boot(checked)

    def _handle_reset_curve_button_clicked(self) -> None:
        self.app_services.reset_active_curve()

    def _handle_profile_button_right_click(self, button: QPushButton) -> None:
        profile_name = button.property("profile_name")
        if profile_name:
            self.app_services.save_current_settings_to_profile(profile_name)
            self.transient_status_signal.emit(tr("profile_saved_message", profile_name=profile_name))

    def _handle_profile_button_double_click(self, button: QPushButton) -> None:
        old_name = button.property("profile_name")
        if not old_name: return

        new_name, ok = QInputDialog.getText(self, tr("rename_profile_title"),
                                            tr("rename_profile_label", old_name=old_name),
                                            QLineEdit.EchoMode.Normal, old_name)
        if ok and new_name and new_name.strip():
            self.app_services.rename_profile(old_name, new_name.strip())
        elif ok:
             QMessageBox.warning(self, tr("rename_profile_error_title"), tr("rename_profile_error_empty"))

    def _update_curve_type_display(self, curve_type: str) -> None:
        self.controls.curve_button_group.blockSignals(True)
        self.controls.cpu_curve_button.setChecked(curve_type == 'cpu')
        self.controls.gpu_curve_button.setChecked(curve_type == 'gpu')
        self.controls.curve_button_group.blockSignals(False)

    def _update_start_on_boot_display(self, is_enabled: bool) -> None:
        self.controls.start_on_boot_checkbox.blockSignals(True)
        self.controls.start_on_boot_checkbox.setChecked(is_enabled)
        self.controls.start_on_boot_checkbox.blockSignals(False)

    def retranslate_ui(self) -> None:
        self.controls.cpu_curve_button.setText(tr("cpu_curve_button"))
        self.controls.gpu_curve_button.setText(tr("gpu_curve_button"))
        self.controls.reset_curve_button.setText(tr("reset_curve_button"))
        for btn in self.profile_buttons:
            btn.setToolTip(tr("profile_button_tooltip"))
        self.controls.start_on_boot_checkbox.setText(tr("start_on_boot_label"))
        self.controls.start_on_boot_checkbox.setToolTip(tr("start_on_boot_tooltip"))
