# -*- coding: utf-8 -*-
"""
应用的自定义标题栏小部件。
"""

from .qt import (
    QWidget, QHBoxLayout, QLabel, QPushButton, QComboBox, QSize, Qt, Signal, QMouseEvent,
    QIcon, QPixmap, QPainter, QSvgRenderer, QBuffer, QIODevice, QByteArray, QMainWindow
)
from tools.localization import tr, get_available_languages, get_current_language
from core.settings_manager import SettingsManager
from typing import Optional, cast
from .qt import (
    QWidget, QHBoxLayout, QLabel, QPushButton, QComboBox, QSize, Qt, Signal, QMouseEvent,
    QIcon, QPixmap, QPainter, QSvgRenderer, QBuffer, QIODevice, QByteArray, QMainWindow
)
from tools.localization import tr, get_available_languages, get_current_language
from core.settings_manager import SettingsManager

# SVG图标数据
SVG_MINIMIZE = """
<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 12 12">
  <path stroke="{color}" stroke-width="2" d="M2 6h8"/>
</svg>
"""
SVG_MAXIMIZE = """
<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 12 12">
  <path fill-opacity="0" stroke="{color}" stroke-width="2" d="M2 2h8v8H2z"/>
</svg>
"""
SVG_RESTORE = """
<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 12 12">
  <path fill-opacity="0" stroke="{color}" stroke-width="2" d="M4 4h6v6H4z"/>
  <path fill="#33373B" d="M2 2h6v1H3v5H2z"/>
  <path fill-opacity="0" stroke="{color}" stroke-width="1.5" d="M2.5 7.5V2.5h5"/>
</svg>
"""
SVG_CLOSE = """
<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 12 12">
  <path stroke="{color}" stroke-width="2.5" d="M2.5 2.5l7 7M2.5 9.5l7-7"/>
</svg>
"""

class CustomTitleBar(QWidget):
    """带有图标、标题、状态、语言选择器和窗口控件的自定义标题栏。"""
    
    def __init__(self, settings_manager: SettingsManager, parent: Optional[QMainWindow] = None):
        super().__init__(parent)
        self.settings_manager = settings_manager
        self.setObjectName("customTitleBar")
        self.setFixedHeight(40)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 5, 0)
        layout.setSpacing(10)

        self.icon_label = QLabel(self)
        self.icon_label.setFixedSize(QSize(24, 24))
        self.icon_label.setScaledContents(True)

        self.title_label = QLabel(tr("window_title"), self)
        self.title_label.setObjectName("titleBarLabel")

        self.status_label = QLabel(self)
        self.status_label.setObjectName("statusLabel")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.language_combo = QComboBox()
        self._populate_language_combo()
        self.language_combo.currentIndexChanged.connect(self._on_language_changed)

        layout.addWidget(self.icon_label)
        layout.addWidget(self.title_label)
        layout.addStretch(1)
        layout.addWidget(self.status_label)
        layout.addStretch(1)
        layout.addWidget(self.language_combo)
        layout.addSpacing(10)

        self.minimize_button = QPushButton()
        self.maximize_button = QPushButton()
        self.close_button = QPushButton()
        
        self.minimize_button.setObjectName("windowControlButton")
        self.maximize_button.setObjectName("windowControlButton")
        self.close_button.setObjectName("windowControlButton_close")

        for btn in [self.minimize_button, self.maximize_button, self.close_button]:
            btn.setFixedSize(QSize(30, 30))
            btn.setIconSize(QSize(12, 12))

        self.minimize_button.setIcon(self._create_svg_icon(SVG_MINIMIZE))
        self.close_button.setIcon(self._create_svg_icon(SVG_CLOSE))
        self.update_window_state(False)

        layout.addWidget(self.minimize_button)
        layout.addWidget(self.maximize_button)
        layout.addWidget(self.close_button)

    def _create_svg_icon(self, svg_data: str, color: str = "#E0E0E0") -> QIcon:
        if not QSvgRenderer: return QIcon()
        
        renderer = QSvgRenderer(QByteArray(svg_data.format(color=color).encode("utf-8")))
        pixmap = QPixmap(renderer.defaultSize())
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        return QIcon(pixmap)

    def update_window_state(self, is_maximized: bool):
        if is_maximized:
            self.maximize_button.setIcon(self._create_svg_icon(SVG_RESTORE))
            self.maximize_button.setToolTip(tr("restore_button_tooltip"))
        else:
            self.maximize_button.setIcon(self._create_svg_icon(SVG_MAXIMIZE))
            self.maximize_button.setToolTip(tr("maximize_button_tooltip"))

    def _populate_language_combo(self):
        self.language_combo.blockSignals(True)
        self.language_combo.clear()
        current_lang_code = get_current_language()
        available_langs = get_available_languages()
        
        current_idx = 0
        codes_in_order = sorted(available_langs.keys())

        for i, code in enumerate(codes_in_order):
            display_name = available_langs[code]
            self.language_combo.addItem(display_name, code)
            if code == current_lang_code:
                current_idx = i
        
        if codes_in_order:
            self.language_combo.setCurrentIndex(current_idx)
        self.language_combo.blockSignals(False)

    def _on_language_changed(self, index: int):
        new_lang_code = self.language_combo.itemData(index)
        if new_lang_code and new_lang_code != get_current_language():
            self.settings_manager.set_language(new_lang_code)

    def retranslate_ui(self):
        self.title_label.setText(tr("window_title"))
        self._populate_language_combo()
        parent_widget = cast(QMainWindow, self.parent())
        is_max = parent_widget.isMaximized() if parent_widget else False
        self.update_window_state(is_max)