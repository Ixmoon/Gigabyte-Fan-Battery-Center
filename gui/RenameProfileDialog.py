# -*- coding: utf-8 -*-
"""
一个自定义对话框，用于重命名或删除配置文件。
"""
from .qt import QDialog, QVBoxLayout, QLabel, QLineEdit, QDialogButtonBox, QMessageBox, QWidget
from tools.localization import tr
from typing import Optional

class RenameProfileDialog(QDialog):
    """用于重命名和删除配置文件的自定义对话框。"""
    def __init__(self, old_name: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        # 使用tr()函数
        self.setWindowTitle(tr("rename_profile_title"))
        
        self.result_action: str = "cancel"
        self.old_name = old_name
        
        layout = QVBoxLayout(self)
        
        # 使用tr()函数
        self.label = QLabel(tr("rename_profile_label", old_name=old_name), self)
        layout.addWidget(self.label)
        
        self.line_edit = QLineEdit(old_name, self)
        layout.addWidget(self.line_edit)
        
        self.button_box = QDialogButtonBox(self)
        # 使用tr()函数
        self.rename_button = self.button_box.addButton(tr("rename_button"), QDialogButtonBox.ButtonRole.AcceptRole)
        self.delete_button = self.button_box.addButton(tr("delete_button"), QDialogButtonBox.ButtonRole.DestructiveRole)
        self.button_box.addButton(QDialogButtonBox.StandardButton.Cancel)
        
        layout.addWidget(self.button_box)
        
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        self.delete_button.clicked.connect(self._on_delete_clicked)

    def new_name(self) -> str:
        return self.line_edit.text().strip()

    def _on_delete_clicked(self):
        # 使用tr()函数
        reply = QMessageBox.warning(
            self,
            tr("delete_profile_title"),
            tr("delete_profile_confirm_msg", name=self.old_name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.result_action = "delete"
            self.accept()

    def accept(self):
        if self.result_action != "delete":
            self.result_action = "rename"
        super().accept()