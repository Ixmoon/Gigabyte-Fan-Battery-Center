# gui/SettingsPanel.py
# -*- coding: utf-8 -*-
"""
Settings Panel QWidget for Fan & Battery Control.

Contains controls for application settings like language.
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QFrame
)
from PyQt6.QtCore import pyqtSignal, Qt, QTimer

from tools.localization import tr, get_available_languages, get_current_language

class SettingsPanel(QFrame):
    """
    A QFrame subclass that groups application settings controls.
    """
    language_changed_signal = pyqtSignal(str) # lang_code
    transient_status_signal = pyqtSignal(str) # For MainWindow to show temporary status

    def __init__(self, parent: QWidget = None):
        """
        Initializes the SettingsPanel.

        Args:
            parent: The parent widget.
        """
        super().__init__(parent)
        self.setObjectName("settingsFrame") # Optional for styling
        # self.setFrameShape(QFrame.Shape.StyledPanel)

        self._init_ui()

    def _init_ui(self) -> None:
        """
        Initializes the UI elements for the settings panel.
        """
        # Main layout for this panel can be QVBoxLayout if settings are stacked vertically
        # or QHBoxLayout if they are primarily horizontal.
        # For just language, QHBoxLayout within a QVBoxLayout for the frame is fine.
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(5,5,5,5)
        outer_layout.setAlignment(Qt.AlignmentFlag.AlignTop)


        controls_layout = QHBoxLayout()
        controls_layout.setContentsMargins(0,0,0,0) # No inner margins if outer has them
        controls_layout.setSpacing(10)


        self.language_label = QLabel(tr("language_label"))
        self.language_combo = QComboBox()
        self._populate_language_combo()
        self.language_combo.currentIndexChanged.connect(self._on_language_changed)

        controls_layout.addWidget(self.language_label)
        controls_layout.addWidget(self.language_combo)
        controls_layout.addStretch(1) # Push to left if more items are added later in this row

        outer_layout.addLayout(controls_layout)
        outer_layout.addStretch(1) # Pushes the QHBoxLayout to the top


    def _populate_language_combo(self) -> None:
        """Populates the language selection QComboBox."""
        self.language_combo.blockSignals(True)
        self.language_combo.clear()
        current_lang_code = get_current_language()
        available_langs = get_available_languages() # Returns dict {code: display_name}
        
        current_idx = 0
        # Sort by display name for user-friendliness, or by code for consistency
        # Sticking to code sorting as in MainWindow for now.
        codes_in_order = sorted(available_langs.keys()) 

        for i, code in enumerate(codes_in_order):
            display_name = available_langs[code]
            self.language_combo.addItem(display_name, code) # Store code as item data
            if code == current_lang_code:
                current_idx = i
        
        if codes_in_order: # Ensure list is not empty
             self.language_combo.setCurrentIndex(current_idx)
        self.language_combo.blockSignals(False)

    def _on_language_changed(self, index: int) -> None:
        new_lang_code = self.language_combo.itemData(index)
        if new_lang_code and new_lang_code != get_current_language():
            # self.transient_status_signal.emit(tr("applying_settings")) # Example if it took time
            self.language_changed_signal.emit(new_lang_code)
            # The AppRunner/ViewModel will handle saving config and telling MainWindow to retranslate all

    # Removed set_language_combo as _populate_language_combo handles this during retranslate_ui

    def set_panel_enabled(self, enabled: bool) -> None:
        """Globally enables or disables all controls in this panel."""
        self.language_label.setEnabled(enabled)
        self.language_combo.setEnabled(enabled)

    def retranslate_ui(self) -> None:
        """Retranslates all user-visible text in the panel."""
        self.language_label.setText(tr("language_label"))
        self._populate_language_combo() # Repopulate with translated display names


if __name__ == '__main__':
    # Example Usage
    import sys
    from PyQt6.QtWidgets import QApplication, QMainWindow
    from tools.localization import load_translations # Need to load some dummy translations

    # Mock languages.json content for standalone testing
    import json
    import os
    
    # Create a dummy languages.json if it doesn't exist for the test
    dummy_lang_file_path = "dummy_languages.json"
    if not os.path.exists(dummy_lang_file_path):
        dummy_langs_data = {
            "en": {"name": "English", "translation": {"language_label": "Language:"}},
            "zh_CN": {"name": "简体中文", "translation": {"language_label": "语言："}},
            "de": {"name": "Deutsch", "translation": {"language_label": "Sprache:"}}
        }
        with open(dummy_lang_file_path, "w", encoding="utf-8") as f:
            json.dump(dummy_langs_data, f, ensure_ascii=False, indent=4)
        
        # For this simple test, we'll assume load_translations can take a path.
        # Or, better, mock get_available_languages and get_current_language.
        load_translations(dummy_lang_file_path, force_reload=True)


    _available_languages_cache = { # Mocking the cache within localization
        "en": "English", "zh_CN": "简体中文", "de": "Deutsch"
    }
    _current_language_cache = "en"
    _translations_cache = {
        "en": {"language_label": "Language:"},
        "zh_CN": {"language_label": "语言："},
        "de": {"language_label": "Sprache:"}
    }

    def mock_get_available_languages():
        return _available_languages_cache.copy()

    def mock_get_current_language():
        return _current_language_cache
    
    def mock_tr(key, **kwargs):
        return _translations_cache.get(_current_language_cache, {}).get(key, key).format(**kwargs)

    # Apply mocks
    import tools.localization
    tools.localization.get_available_languages = mock_get_available_languages
    tools.localization.get_current_language = mock_get_current_language
    tools.localization.tr = mock_tr
    # No need to call load_translations if we mock its outputs

    app = QApplication(sys.argv)
    main_win = QMainWindow()
    panel = SettingsPanel()

    def print_lang_change(lang_code):
        print(f"Language change requested: {lang_code}")
        # Simulate language actually changing for re-test
        global _current_language_cache
        _current_language_cache = lang_code
        panel.retranslate_ui() # Manually call retranslate for test
        panel.set_language_combo(lang_code) # Ensure combo updates after programmatic change

    panel.language_changed_signal.connect(print_lang_change)

    main_win.setCentralWidget(panel)
    main_win.show()
    main_win.resize(300, 150)

    # Test programmatic update
    QTimer.singleShot(2000, lambda: print_lang_change("zh_CN"))
    QTimer.singleShot(4000, lambda: print_lang_change("de"))
    
    # Clean up dummy file if created
    # if os.path.exists(dummy_lang_file_path) and "dummy" in dummy_lang_file_path :
    #     os.remove(dummy_lang_file_path)


    sys.exit(app.exec())