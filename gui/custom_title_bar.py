# gui/custom_title_bar.py
# -*- coding: utf-8 -*-
"""
A custom title bar widget for the application.
"""

from .qt import (
    QWidget, QHBoxLayout, QLabel, QPushButton, QComboBox, QSize, Signal, Qt
)
from tools.localization import tr, get_available_languages, get_current_language

class CustomTitleBar(QWidget):
    """A custom title bar with icon, title, status, language selector, and window controls."""
    
    language_changed_signal = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
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

        self.minimize_button = QPushButton("—")
        self.maximize_button = QPushButton("□")
        self.close_button = QPushButton("✕")
        self.minimize_button.setObjectName("windowControlButton")
        self.maximize_button.setObjectName("windowControlButton")
        self.close_button.setObjectName("windowControlButton_close")

        for btn in [self.minimize_button, self.maximize_button, self.close_button]:
            btn.setFixedSize(QSize(30, 30))

        layout.addWidget(self.minimize_button)
        layout.addWidget(self.maximize_button)
        layout.addWidget(self.close_button)

    def _populate_language_combo(self):
        """Populates the language selection QComboBox."""
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
        """Handles language selection change."""
        new_lang_code = self.language_combo.itemData(index)
        if new_lang_code and new_lang_code != get_current_language():
            self.language_changed_signal.emit(new_lang_code)

    def retranslate_ui(self):
        """Retranslates all user-visible text in the title bar."""
        self.title_label.setText(tr("window_title"))
        self._populate_language_combo()
