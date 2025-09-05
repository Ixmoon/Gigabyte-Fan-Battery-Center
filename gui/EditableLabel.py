# -*- coding: utf-8 -*-
"""
一个自定义控件，平时显示为QLabel，双击后变为可编辑的QLineEdit。
"""
# 【改进】使用显式导入代替通配符导入
from .qt import (
    QWidget, Signal, QLabel, QLineEdit, QStackedLayout, QIntValidator,
    Qt, QMouseEvent
)
from typing import Optional, cast

class EditableLabel(QWidget):
    """一个可双击编辑的标签控件。"""
    editingFinished = Signal(int)

    def __init__(self, unit: str = "", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.unit = unit
        
        self.label = QLabel(self)
        self.line_edit = QLineEdit(self)
        self.line_edit.hide()
        
        self.line_edit.setValidator(QIntValidator(0, 100, self))
        
        layout: QStackedLayout = QStackedLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.label)
        layout.addWidget(self.line_edit)
        
        self.line_edit.editingFinished.connect(self._finish_editing)
        self.setFocusProxy(self.line_edit)

    def text(self) -> str:
        """获取标签的文本（不含单位）。"""
        return self.label.text().replace(self.unit, "").strip()

    def value(self) -> int:
        """获取标签表示的整数值。"""
        try:
            return int(self.text())
        except ValueError:
            return 0

    def setText(self, text: str):
        """设置标签的文本。"""
        self.label.setText(f"{text}{self.unit}")

    def setValue(self, value: int):
        """设置标签的数值。"""
        self.setText(str(value))

    def setAlignment(self, alignment: Qt.AlignmentFlag):
        """设置标签和编辑框的对齐方式。"""
        self.label.setAlignment(alignment)
        self.line_edit.setAlignment(alignment)

    def setMinimumWidth(self, minw: int):
        """设置最小宽度。"""
        self.label.setMinimumWidth(minw)
        super().setMinimumWidth(minw)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        """处理双击事件，切换到编辑模式。"""
        if self.isEnabled():
            self.line_edit.setText(self.text())
            cast(QStackedLayout, self.layout()).setCurrentWidget(self.line_edit)
            self.line_edit.selectAll()
            self.line_edit.setFocus()
        super().mouseDoubleClickEvent(event)

    def _finish_editing(self):
        """完成编辑，提交值并切换回标签模式。"""
        new_value = self.line_edit.text()
        if new_value:
            self.setValue(int(new_value))
            self.editingFinished.emit(int(new_value))
        cast(QStackedLayout, self.layout()).setCurrentWidget(self.label)

    def setEnabled(self, enabled: bool):
        """重写 setEnabled 以同时控制内部控件。"""
        self.label.setEnabled(enabled)
        super().setEnabled(enabled)