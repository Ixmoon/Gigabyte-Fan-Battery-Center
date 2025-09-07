# -*- coding: utf-8 -*-
"""
曲线控制面板QFrame - 一个自包含的视图组件，管理所有配置文件和曲线相关的交互。
"""
from .qt import *
from typing import List, Optional
from tools.localization import tr
from core.state import AppState
from core.profile_manager import ProfileManager
from core.settings_manager import SettingsManager
from .tooltip_manager import tooltip_manager
from .RenameProfileDialog import RenameProfileDialog

class CurveControlPanel(QFrame):
    """曲线和配置文件管理的自包含视图组件。"""
    transient_status_signal = Signal(str)

    def __init__(self, profile_manager: ProfileManager, settings_manager: SettingsManager, state: AppState, parent=None):
        super().__init__(parent)
        self.profile_manager = profile_manager
        self.settings_manager = settings_manager
        self.state = state
        self.profile_buttons: List[QPushButton] = []
        
        self._init_ui()
        self._connect_signals()
        
        self._update_curve_type_display(self.state.get_active_curve_type())
        self._update_start_on_boot_display(self.state.get_start_on_boot())
        self._rebuild_profile_buttons(self.state.get_profile_names(), self.state.get_active_profile_name())
        self._update_interactive_controls_enablement(self.state.get_is_fan_control_panel_enabled())

    def _init_ui(self):
        self.controls_layout = QHBoxLayout()
        
        self.cpu_curve_button = QPushButton(tr("cpu_curve_button"), self)
        self.cpu_curve_button.setCheckable(True)
        self.gpu_curve_button = QPushButton(tr("gpu_curve_button"), self)
        self.gpu_curve_button.setCheckable(True)
        
        self.curve_button_group = QButtonGroup(self)
        self.curve_button_group.addButton(self.cpu_curve_button)
        self.curve_button_group.addButton(self.gpu_curve_button)
        self.curve_button_group.setExclusive(True)
        
        self.profile_button_group = QButtonGroup(self)
        self.profile_button_group.setExclusive(True)
        
        self.add_profile_button = QPushButton("+", self)
        self.add_profile_button.setObjectName("addProfileButton")
        
        self.start_on_boot_checkbox = QCheckBox(tr("start_on_boot_label"), self)
        
        self.reset_curve_button = QPushButton(tr("reset_curve_button"), self)
        self.reset_curve_button.setObjectName("resetCurveButton")
        
        tooltip_manager.register(self.add_profile_button, "add_profile_tooltip")
        tooltip_manager.register(self.start_on_boot_checkbox, "start_on_boot_tooltip")
        tooltip_manager.register(self.reset_curve_button, "reset_curve_tooltip")

        self.controls_layout.addWidget(self.cpu_curve_button)
        self.controls_layout.addWidget(self.gpu_curve_button)
        self.controls_layout.addSpacerItem(QSpacerItem(15, 10, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum))
        
        self.controls_layout.addStretch(1)
        self.controls_layout.addWidget(self.start_on_boot_checkbox)
        self.controls_layout.addSpacerItem(QSpacerItem(10, 10, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum))
        self.controls_layout.addWidget(self.reset_curve_button)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addLayout(self.controls_layout)

    def _connect_signals(self):
        self.curve_button_group.buttonClicked.connect(self._handle_curve_type_button_clicked)
        self.profile_button_group.buttonClicked.connect(self._handle_profile_button_left_clicked)
        self.add_profile_button.clicked.connect(self._handle_add_profile_clicked)
        self.start_on_boot_checkbox.toggled.connect(self.settings_manager.set_start_on_boot)
        self.reset_curve_button.clicked.connect(self.profile_manager.reset_active_curve)
        
        self.state.is_fan_control_panel_enabled_changed.connect(self._update_interactive_controls_enablement)
        self.state.active_curve_type_changed.connect(self._update_curve_type_display)
        self.state.start_on_boot_changed.connect(self._update_start_on_boot_display)
        self.state.profiles_list_changed.connect(self._rebuild_profile_buttons)

    @Slot(bool)
    def _update_interactive_controls_enablement(self, is_enabled: bool):
        self.reset_curve_button.setEnabled(is_enabled)
        self.cpu_curve_button.setEnabled(is_enabled)
        self.gpu_curve_button.setEnabled(is_enabled)

    @Slot(list, str)
    def _rebuild_profile_buttons(self, profile_names: List[str], active_profile_name: Optional[str]):
        for button in self.profile_buttons:
            self.profile_button_group.removeButton(button)
            tooltip_manager.unregister(button)
            button.deleteLater()
        self.profile_buttons.clear()

        while self.controls_layout.count() > 3:
            item = self.controls_layout.itemAt(2)
            if isinstance(item, QSpacerItem):
                break
            widget = item.widget()
            if widget:
                self.controls_layout.removeWidget(widget)
            else:
                self.controls_layout.removeItem(item)

        for i, profile_name in enumerate(profile_names):
            button = QPushButton(profile_name, self)
            button.setCheckable(True)
            button.installEventFilter(self)
            button.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed)
            button.setObjectName(f"profileButton_{i}")
            button.setProperty("profile_name", profile_name)
            button.setChecked(profile_name == active_profile_name)
            tooltip_manager.register(button, "profile_button_tooltip")
            self.profile_buttons.append(button)
            self.profile_button_group.addButton(button)
            self.controls_layout.insertWidget(2 + i, button)
        
        self.controls_layout.insertWidget(2 + len(self.profile_buttons), self.add_profile_button)
        self.controls_layout.insertStretch(2 + len(self.profile_buttons) + 1, 1)


    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if isinstance(obj, QPushButton) and obj in self.profile_buttons:
            if event.type() == QEvent.Type.MouseButtonDblClick:
                self._handle_profile_button_double_click(obj)
                return True
            elif event.type() == QEvent.Type.MouseButtonPress and isinstance(event, QMouseEvent) and event.button() == Qt.MouseButton.RightButton:
                self._handle_profile_button_right_click(obj)
                return True
        return super().eventFilter(obj, event)

    def _handle_curve_type_button_clicked(self, button: QPushButton):
        self.settings_manager.set_active_curve_type('cpu' if button == self.cpu_curve_button else 'gpu')

    def _handle_profile_button_left_clicked(self, button: QPushButton):
        if button.isChecked():
            self.profile_manager.activate_profile(button.property("profile_name"))

    def _handle_profile_button_right_click(self, button: QPushButton):
        profile_name = button.property("profile_name")
        active_profile = self.profile_manager.get_active_profile()
        target_profile = self.state.get_profile(profile_name)
        if active_profile and target_profile:
            target_profile.from_dict(active_profile.to_dict())
            self.profile_manager.save_config()
            self.transient_status_signal.emit(tr("profile_saved_message", profile_name=profile_name))

    def _handle_profile_button_double_click(self, button: QPushButton):
        old_name = button.property("profile_name")
        dialog = RenameProfileDialog(old_name, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            if dialog.result_action == "rename":
                new_name = dialog.new_name()
                if new_name and new_name != old_name:
                    if self.state.get_profile(new_name):
                        # 使用tr()函数
                        QMessageBox.warning(self, tr("add_profile_error_title"), tr("add_profile_duplicate_name_error", name=new_name))
                    else:
                        self.profile_manager.rename_profile(old_name, new_name)
            elif dialog.result_action == "delete":
                self.profile_manager.delete_profile(old_name)

    def _handle_add_profile_clicked(self):
        # 使用tr()函数
        new_name, ok = QInputDialog.getText(self, tr("add_profile_title"), tr("add_profile_label"), QLineEdit.EchoMode.Normal, "")
        if ok and new_name:
            new_name = new_name.strip()
            if not new_name:
                QMessageBox.warning(self, tr("add_profile_error_title"), tr("add_profile_empty_name_error"))
                return
            if self.state.get_profile(new_name):
                QMessageBox.warning(self, tr("add_profile_error_title"), tr("add_profile_duplicate_name_error", name=new_name))
                return
            self.profile_manager.create_new_profile(new_name)

    @Slot(str)
    def _update_curve_type_display(self, curve_type: str):
        self.curve_button_group.blockSignals(True)
        try:
            self.cpu_curve_button.setChecked(curve_type == 'cpu')
            self.gpu_curve_button.setChecked(curve_type == 'gpu')
        finally:
            self.curve_button_group.blockSignals(False)

    @Slot(bool)
    def _update_start_on_boot_display(self, is_enabled: bool):
        self.start_on_boot_checkbox.blockSignals(True)
        try:
            self.start_on_boot_checkbox.setChecked(is_enabled)
        finally:
            self.start_on_boot_checkbox.blockSignals(False)

    def retranslate_ui(self):
        self.cpu_curve_button.setText(tr("cpu_curve_button"))
        self.gpu_curve_button.setText(tr("gpu_curve_button"))
        self.reset_curve_button.setText(tr("reset_curve_button"))
        self.start_on_boot_checkbox.setText(tr("start_on_boot_label"))