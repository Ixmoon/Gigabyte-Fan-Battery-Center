# viewmodels/base_viewmodel.py
# -*- coding: utf-8 -*-
"""
Base class for ViewModel objects.
"""
from gui.qt import QObject, Signal

class BaseViewModel(QObject):
    """
    A base class for ViewModels to provide common signals and slots.
    """
    # Example of a common signal that might be shared across ViewModels
    panel_enabled_changed = Signal(bool)

    def __init__(self, parent: QObject = None):
        super().__init__(parent)
        self._is_panel_enabled = True

    def is_panel_enabled(self) -> bool:
        """Returns whether the panel associated with this ViewModel should be enabled."""
        return self._is_panel_enabled

    def set_panel_enabled(self, enabled: bool):
        """Sets the enabled state of the panel."""
        if self._is_panel_enabled != enabled:
            self._is_panel_enabled = enabled
            self.panel_enabled_changed.emit(enabled)