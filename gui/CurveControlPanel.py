# gui/CurveControlPanel.py
# -*- coding: utf-8 -*-
"""
Curve Control Panel QWidget for Fan & Battery Control.

Contains controls for selecting curve type (CPU/GPU), managing profiles,
toggling start on boot, and resetting curves.
"""
from .qt import (
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QButtonGroup, QCheckBox,
    QSpacerItem, QSizePolicy, QFrame, QInputDialog, QMessageBox,
    Signal, Qt, QEvent, QObject, QLineEdit, QMouseEvent
)

from typing import List, Optional, TYPE_CHECKING, cast

from tools.localization import tr

if TYPE_CHECKING:
    from core.app_services import AppServices
    from core.state import AppState


class CurveControlPanel(QFrame):
    """
    A QFrame subclass that groups controls related to curve and profile management.
    Interacts with AppServices for its logic and gets state updates.
    """
    transient_status_signal = Signal(str) # Signal to MainWindow to show a temporary status

    def __init__(self, app_services: 'AppServices', parent: Optional[QWidget] = None):
        """
        Initializes the CurveControlPanel.

        Args:
            app_services: The application services instance.
            parent: The parent widget.
        """
        super().__init__(parent)
        self.setObjectName("curveControlFrame")

        self.app_services = app_services
        self.profile_buttons: List[QPushButton] = []

        self._init_ui()

    def _init_ui(self) -> None:
        """
        Initializes the UI elements for the curve control panel.
        """
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5) # Adjust margins as needed
        main_layout.setSpacing(5)

        controls_layout = QHBoxLayout()

        # Curve type buttons
        self.cpu_curve_button = QPushButton(tr("cpu_curve_button"))
        self.cpu_curve_button.setCheckable(True)
        self.gpu_curve_button = QPushButton(tr("gpu_curve_button"))
        self.gpu_curve_button.setCheckable(True)

        self.curve_button_group = QButtonGroup(self)
        self.curve_button_group.addButton(self.cpu_curve_button)
        self.curve_button_group.addButton(self.gpu_curve_button)
        self.curve_button_group.setExclusive(True)
        self.curve_button_group.buttonClicked.connect(self._handle_curve_type_button_clicked)

        controls_layout.addWidget(self.cpu_curve_button)
        controls_layout.addWidget(self.gpu_curve_button)
        controls_layout.addSpacerItem(QSpacerItem(15, 10, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum))

        # Profile buttons - will be added directly to controls_layout by _rebuild_profile_buttons
        self.profile_button_group = QButtonGroup(self)
        self.profile_button_group.setExclusive(True)
        self.profile_button_group.buttonClicked.connect(self._handle_profile_button_left_clicked)

        # Placeholder for where profile buttons will be inserted by _rebuild_profile_buttons
        # controls_layout.addLayout(self.profile_buttons_layout) # REMOVED

        # controls_layout.addStretch(1) # MOVED: This will be added AFTER profile buttons

        # Start on Boot checkbox
        self.start_on_boot_checkbox = QCheckBox(tr("start_on_boot_label"))
        self.start_on_boot_checkbox.setToolTip(tr("start_on_boot_tooltip"))
        self.start_on_boot_checkbox.toggled.connect(self._handle_start_on_boot_toggled)

        # controls_layout.addWidget(self.start_on_boot_checkbox) # MOVED: Added after profile buttons
        controls_layout.addSpacerItem(QSpacerItem(10, 10, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum))

        # Reset Curve button
        self.reset_curve_button = QPushButton(tr("reset_curve_button"))
        self.reset_curve_button.setObjectName("resetCurveButton") # For styling
        self.reset_curve_button.clicked.connect(self._handle_reset_curve_button_clicked)
        controls_layout.addWidget(self.reset_curve_button)

        main_layout.addLayout(controls_layout)

        # UI is now initialized by the first call to update_state from MainWindow
        # Rebuild buttons with empty lists to set up the layout correctly
        self._rebuild_profile_buttons([], None)

        # Now add stretch and remaining controls AFTER profile buttons
        controls_layout.addStretch(1)
        controls_layout.addWidget(self.start_on_boot_checkbox)
        controls_layout.addSpacerItem(QSpacerItem(10, 10, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum))
        controls_layout.addWidget(self.reset_curve_button)

    def update_state(self, state: 'AppState'):
        """Updates the entire panel from the new AppState."""
        self._update_curve_type_display(state.active_curve_type)
        self._rebuild_profile_buttons(list(state.profiles.keys()), state.active_profile_name)
        self._update_start_on_boot_display(state.start_on_boot)

        # The panel's enabled state should follow the global state
        self.set_panel_enabled(state.is_panel_enabled)

    def _rebuild_profile_buttons(self, profile_names: List[str], active_profile_name: Optional[str]) -> None:
        """Clears and recreates profile buttons directly in controls_layout."""
        # Get the parent layout (controls_layout) of the profile buttons
        # Assuming profile buttons are direct children of a layout that's part of main_layout
        # This needs to reliably get controls_layout.
        # Since _init_ui sets self.layout() to main_layout, and controls_layout is a child of main_layout:
        layout = self.layout()
        if not layout:
            return
        layout_item = layout.itemAt(0)
        if not layout_item or not isinstance(layout_item.layout(), QHBoxLayout):
            return
        controls_layout = cast(QHBoxLayout, layout_item.layout())

        # Clear existing buttons from layout and group
        for button in self.profile_buttons:
            self.profile_button_group.removeButton(button)
            controls_layout.removeWidget(button) # Remove from controls_layout
            button.deleteLater()
        self.profile_buttons.clear()

        # Determine insert index: after CPU/GPU buttons and their spacer
        # CPU button, GPU button, Spacer = 3 items. Insert at index 3.
        insert_idx = 3
        if controls_layout.count() < insert_idx: # Safety if layout is unexpectedly sparse
            insert_idx = controls_layout.count()


        for i, profile_name in enumerate(profile_names):
            button = QPushButton(profile_name)
            button.setCheckable(True)
            button.setToolTip(tr("profile_button_tooltip"))
            button.setObjectName(f"profileButton_{i}")
            button.setProperty("profile_name", profile_name)
            button.installEventFilter(self)

            self.profile_buttons.append(button)
            self.profile_button_group.addButton(button)
            # controls_layout.addWidget(button) # Add directly to controls_layout (before stretch)
            controls_layout.insertWidget(insert_idx + i, button) # Insert at calculated position

            if profile_name == active_profile_name:
                button.setChecked(True)

    def _handle_curve_type_button_clicked(self, button: QPushButton) -> None:
        curve_type = 'cpu' if button == self.cpu_curve_button else 'gpu'
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

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if isinstance(obj, QPushButton) and obj in self.profile_buttons:
            if event.type() == QEvent.Type.MouseButtonDblClick and isinstance(event, QMouseEvent) and event.button() == Qt.MouseButton.LeftButton:
                self._handle_profile_button_double_click(obj)
                return True
            elif event.type() == QEvent.Type.MouseButtonPress and isinstance(event, QMouseEvent) and event.button() == Qt.MouseButton.RightButton:
                self._handle_profile_button_right_click(obj)
                event.accept()
                return True
        return super().eventFilter(obj, event)

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
        if ok and new_name:
            new_name = new_name.strip()
            if not new_name:
                QMessageBox.warning(self, tr("rename_profile_error_title"), tr("rename_profile_error_empty"))
                return
            self.app_services.rename_profile(old_name, new_name)
        elif ok and not new_name:
             QMessageBox.warning(self, tr("rename_profile_error_title"), tr("rename_profile_error_empty"))


    def _update_curve_type_display(self, curve_type: str) -> None:
        """Updates the curve type radio buttons based on ViewModel."""
        self.curve_button_group.blockSignals(True)
        if curve_type == 'cpu':
            self.cpu_curve_button.setChecked(True)
        elif curve_type == 'gpu':
            self.gpu_curve_button.setChecked(True)
        self.curve_button_group.blockSignals(False)

    def _update_start_on_boot_display(self, is_enabled: bool) -> None:
        """Updates the 'Start on Boot' checkbox state."""
        self.start_on_boot_checkbox.blockSignals(True)
        self.start_on_boot_checkbox.setChecked(is_enabled)
        self.start_on_boot_checkbox.blockSignals(False)

    def set_panel_enabled(self, enabled: bool) -> None:
        """Globally enables or disables all controls in this panel."""
        self.cpu_curve_button.setEnabled(enabled)
        self.gpu_curve_button.setEnabled(enabled)
        for btn in self.profile_buttons:
            btn.setEnabled(enabled)
        self.start_on_boot_checkbox.setEnabled(enabled)
        self.reset_curve_button.setEnabled(enabled)
        # The eventFilter for profile buttons will still work as it's on the panel itself.

    def retranslate_ui(self) -> None:
        """Retranslates all user-visible text in the panel."""
        self.cpu_curve_button.setText(tr("cpu_curve_button"))
        self.gpu_curve_button.setText(tr("gpu_curve_button"))
        self.reset_curve_button.setText(tr("reset_curve_button"))
        for btn in self.profile_buttons:
            btn.setToolTip(tr("profile_button_tooltip"))
            # Profile names are dynamic and handled by update_profile_button_name or init
        self.start_on_boot_checkbox.setText(tr("start_on_boot_label"))
        self.start_on_boot_checkbox.setToolTip(tr("start_on_boot_tooltip"))

