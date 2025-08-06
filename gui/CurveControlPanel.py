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
    Signal, Qt, QEvent, QObject, QLineEdit
)

from typing import List, Optional, TYPE_CHECKING

from tools.localization import tr
# from config.settings import NUM_PROFILES # ViewModel will provide profile data including count

if TYPE_CHECKING:
    from viewmodels.curve_control_viewmodel import CurveControlViewModel


class CurveControlPanel(QFrame):
    """
    A QFrame subclass that groups controls related to curve and profile management.
    Interacts with a ViewModel for its logic and state.
    """
    transient_status_signal = Signal(str) # Signal to MainWindow to show a temporary status

    def __init__(self, view_model: 'CurveControlViewModel', parent: QWidget = None):
        """
        Initializes the CurveControlPanel.

        Args:
            view_model: The ViewModel instance for curve control.
            parent: The parent widget.
        """
        super().__init__(parent)
        self.setObjectName("curveControlFrame") # Optional: for specific styling
        # self.setFrameShape(QFrame.Shape.StyledPanel)

        self.view_model = view_model
        self.profile_buttons: List[QPushButton] = [] # Still need to store button instances
        # self.profile_buttons_layout: Optional[QHBoxLayout] = None # REMOVED: No longer using a dedicated sub-layout

        self._init_ui()
        self._connect_viewmodel_signals()

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
        self.start_on_boot_checkbox.toggled.connect(self.view_model.set_start_on_boot) # Directly connect

        controls_layout.addWidget(self.start_on_boot_checkbox)
        controls_layout.addSpacerItem(QSpacerItem(10, 10, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum))

        # Reset Curve button
        self.reset_curve_button = QPushButton(tr("reset_curve_button"))
        self.reset_curve_button.setObjectName("resetCurveButton") # For styling
        self.reset_curve_button.clicked.connect(self._handle_reset_curve_button_clicked)
        controls_layout.addWidget(self.reset_curve_button)

        main_layout.addLayout(controls_layout)

        # Initialize UI states from ViewModel AFTER all elements are created and laid out
        self._update_curve_type_display(self.view_model.current_curve_type)
        
        # Profile buttons are built first and added to controls_layout
        self._rebuild_profile_buttons(self.view_model.profile_names, self.view_model.active_profile_name)

        # Now add stretch and remaining controls AFTER profile buttons
        controls_layout.addStretch(1)
        controls_layout.addWidget(self.start_on_boot_checkbox)
        controls_layout.addSpacerItem(QSpacerItem(10, 10, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum))
        controls_layout.addWidget(self.reset_curve_button)
        
        self._update_start_on_boot_display(self.view_model.is_start_on_boot_enabled)


    def _connect_viewmodel_signals(self) -> None:
        """Connects signals from the ViewModel to panel slots."""
        self.view_model.active_curve_type_updated.connect(self._update_curve_type_display)
        self.view_model.profile_list_updated.connect(self._handle_profile_list_updated)
        self.view_model.active_profile_updated.connect(self._update_active_profile_display)
        self.view_model.start_on_boot_status_updated.connect(self._update_start_on_boot_display)
        self.view_model.profile_renamed_locally.connect(self._update_profile_button_text_property)
        self.view_model.panel_enabled_updated.connect(self.set_panel_enabled)


    def _rebuild_profile_buttons(self, profile_names: List[str], active_profile_name: Optional[str]) -> None:
        """Clears and recreates profile buttons directly in controls_layout."""
        # Get the parent layout (controls_layout) of the profile buttons
        # Assuming profile buttons are direct children of a layout that's part of main_layout
        # This needs to reliably get controls_layout.
        # Since _init_ui sets self.layout() to main_layout, and controls_layout is a child of main_layout:
        if not self.layout() or not isinstance(self.layout().itemAt(0), QHBoxLayout): # main_layout should have controls_layout at index 0
             print("[DEBUG] CurveControlPanel: Could not find controls_layout to rebuild profile buttons.")
             return
        controls_layout = self.layout().itemAt(0).layout() # This should be controls_layout
        if not controls_layout:
            print("[DEBUG] CurveControlPanel: controls_layout is None during _rebuild_profile_buttons.")
            return

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

    def _handle_profile_list_updated(self, profile_names: List[str], active_profile_name: str) -> None:
        """Called when the ViewModel signals that the list of profiles has changed."""
        self._rebuild_profile_buttons(profile_names, active_profile_name)


    def _handle_curve_type_button_clicked(self, button: QPushButton) -> None:
        curve_type = 'cpu' if button == self.cpu_curve_button else 'gpu'
        self.view_model.set_active_curve_type(curve_type) # Corrected method name

    def _handle_profile_button_left_clicked(self, button: QPushButton) -> None:
        if button.isChecked(): # Button group ensures only one can be checked
            profile_name = button.property("profile_name")
            if profile_name:
                # self.transient_status_signal.emit(tr("applying_settings")) # Example
                self.view_model.activate_profile(profile_name)

    def _handle_reset_curve_button_clicked(self) -> None:
        # self.transient_status_signal.emit(tr("applying_settings")) # Example
        self.view_model.reset_active_curve() # ViewModel knows the active curve type

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if isinstance(obj, QPushButton) and obj in self.profile_buttons:
            if event.type() == QEvent.Type.MouseButtonDblClick and event.button() == Qt.MouseButton.LeftButton:
                self._handle_profile_button_double_click(obj)
                return True
            elif event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.RightButton:
                self._handle_profile_button_right_click(obj)
                event.accept()
                return True
        return super().eventFilter(obj, event)

    def _handle_profile_button_right_click(self, button: QPushButton) -> None:
        profile_name = button.property("profile_name")
        if profile_name:
            # self.transient_status_signal.emit(tr("saving_config")) # Example
            self.view_model.request_save_profile(profile_name)

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
            # ViewModel will handle validation (e.g., duplicates) before confirming rename
            # self.transient_status_signal.emit(tr("saving_config")) # Example
            self.view_model.request_rename_profile(old_name, new_name)
        elif ok and not new_name: # User pressed OK but entered empty string
             QMessageBox.warning(self, tr("rename_profile_error_title"), tr("rename_profile_error_empty"))


    def _update_curve_type_display(self, curve_type: str) -> None:
        """Updates the curve type radio buttons based on ViewModel."""
        self.curve_button_group.blockSignals(True)
        if curve_type == 'cpu':
            self.cpu_curve_button.setChecked(True)
        elif curve_type == 'gpu':
            self.gpu_curve_button.setChecked(True)
        self.curve_button_group.blockSignals(False)

    def _update_profile_button_text_property(self, old_name: str, new_name: str) -> None:
        """Updates a single profile button's text and property after rename confirmation."""
        for btn in self.profile_buttons:
            if btn.property("profile_name") == old_name:
                btn.setText(new_name)
                btn.setProperty("profile_name", new_name)
                # Active profile check is handled by _update_active_profile_display if active one renamed
                break

    def _update_active_profile_display(self, active_profile_name: str) -> None:
        """Sets the specified profile button as checked based on ViewModel."""
        self.profile_button_group.blockSignals(True)
        for btn in self.profile_buttons:
            is_active = (btn.property("profile_name") == active_profile_name)
            btn.setChecked(is_active)
        self.profile_button_group.blockSignals(False)

    def _update_start_on_boot_display(self, is_enabled: bool) -> None:
        """Updates the 'Start on Boot' checkbox state from ViewModel."""
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


if __name__ == '__main__':
    # Example Usage
    import sys
    from .qt import QApplication, QMainWindow, QLineEdit

    _translations = {
        "en": {
            "cpu_curve_button": "CPU Curve", "gpu_curve_button": "GPU Curve",
            "profile_default_name": "Profile", "profile_button_tooltip": "Left-click: Activate\nRight-click: Save current settings to this profile\nDouble-click: Rename",
            "start_on_boot_label": "Start on Boot", "start_on_boot_tooltip": "Run application when Windows starts.",
            "reset_curve_button": "Reset Curve",
            "rename_profile_title": "Rename Profile", "rename_profile_label": "Enter new name for '{old_name}':",
            "rename_profile_error_title": "Rename Error", "rename_profile_error_empty": "Profile name cannot be empty.",
            "rename_profile_error_duplicate": "Profile name '{new_name}' already exists."
        }
    }
    current_lang = "en"
    def tr(key, **kwargs):
        return _translations.get(current_lang, {}).get(key, key).format(**kwargs)

    app = QApplication(sys.argv)
    main_win = QMainWindow() # QInputDialog needs a proper parent window

    test_profile_names = ["Performance", "Silent", "Balanced"]
    panel = CurveControlPanel(test_profile_names, "Performance", False, main_win)

    def print_signal(name, *args):
        print(f"Signal '{name}' emitted with args: {args}")

    panel.curve_type_changed_signal.connect(lambda t: print_signal("curve_type_changed", t))
    panel.profile_activated_signal.connect(lambda n: print_signal("profile_activated", n))
    panel.profile_save_requested_signal.connect(lambda n: print_signal("profile_save_requested", n))
    panel.profile_rename_requested_signal.connect(lambda o, n: print_signal("profile_rename_requested", o, n))
    panel.reset_curve_signal.connect(lambda t: print_signal("reset_curve", t))
    panel.start_on_boot_toggled_signal.connect(lambda b: print_signal("start_on_boot_toggled", b))
    
    main_win.setCentralWidget(panel)
    main_win.show()
    main_win.resize(600, 100)
    sys.exit(app.exec())