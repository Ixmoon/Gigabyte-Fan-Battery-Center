# -*- coding: utf-8 -*-
"""
一个集中的、可靠的操作提示管理器，用于解决Qt默认ToolTip机制在复杂UI下可能失效的问题。
"""
from .qt import QObject, QTimer, QToolTip, QEvent, QWidget, QCursor, Slot, QPoint
from typing import Dict, Optional
from tools.localization import tr
from config.settings import TOOLTIP_DELAY_MS

class TooltipManager(QObject):
    """
    通过事件过滤器主动管理和显示工具提示的单例类。
    """
    _instance: Optional['TooltipManager'] = None

    @staticmethod
    def get_instance() -> 'TooltipManager':
        """获取TooltipManager的单例实例。"""
        if TooltipManager._instance is None:
            TooltipManager._instance = TooltipManager()
        return TooltipManager._instance

    def __init__(self, parent: Optional[QObject] = None):
        """初始化函数，私有以强制单例模式。"""
        if TooltipManager._instance is not None:
            raise RuntimeError("TooltipManager is a singleton, use get_instance()")
        super().__init__(parent)
        
        self._registered_widgets: Dict[QWidget, str] = {}
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(TOOLTIP_DELAY_MS)
        self._timer.timeout.connect(self._show_tooltip)

        self._current_widget: Optional[QWidget] = None

    def register(self, widget: QWidget, text_key: str):
        """
        为一个控件注册一个工具提示。
        
        Args:
            widget: 需要显示工具提示的控件。
            text_key: 用于在翻译文件中查找文本的键。
        """
        if widget not in self._registered_widgets:
            self._registered_widgets[widget] = text_key
            widget.installEventFilter(self)

    def unregister(self, widget: QWidget):
        """取消一个控件的工具提示注册。"""
        if widget in self._registered_widgets:
            widget.removeEventFilter(self)
            del self._registered_widgets[widget]

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        """
        事件过滤器，用于捕获鼠标进入和离开事件以控制工具提示。
        """
        if not isinstance(watched, QWidget):
            return super().eventFilter(watched, event)

        # 根据事件类型启动或停止计时器
        if event.type() == QEvent.Type.Enter:
            self._current_widget = watched
            self._timer.start()
        elif event.type() == QEvent.Type.Leave:
            self._timer.stop()
            if self._current_widget is watched:
                self._current_widget = None
            QToolTip.hideText()
        elif event.type() == QEvent.Type.Hide:
            # 如果控件被隐藏，也停止计时并隐藏提示
            if watched == self._current_widget:
                self._timer.stop()
                self._current_widget = None
                QToolTip.hideText()
        
        return super().eventFilter(watched, event)

    @Slot()
    def _show_tooltip(self):
        """
        当计时器触发时，显示工具提示。
        """
        if self._current_widget and self._current_widget.isVisible() and self._current_widget.isEnabled():
            text_key = self._registered_widgets.get(self._current_widget)
            if text_key:
                translated_text = tr(text_key)
                if translated_text:
                    # 增加偏移量以防止提示框在光标下闪烁，从而避免事件冲突
                    pos = QCursor.pos()
                    offset_pos = QPoint(pos.x() + 16, pos.y() + 16)
                    QToolTip.showText(offset_pos, translated_text, self._current_widget)

# 创建全局单例实例，供应用各处使用
tooltip_manager = TooltipManager.get_instance()