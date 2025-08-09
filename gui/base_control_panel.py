# gui/base_control_panel.py
# -*- coding: utf-8 -*-
"""
Base class for control panel QWidgets.
"""
from .qt import QFrame, Signal, Slot, QWidget
from typing import TYPE_CHECKING, Generic, TypeVar

if TYPE_CHECKING:
    from viewmodels.base_viewmodel import BaseViewModel

T_ViewModel = TypeVar('T_ViewModel', bound='BaseViewModel')

class BaseControlPanel(QFrame, Generic[T_ViewModel]):
    """
    A base class for control panels to reduce boilerplate code.
    It handles common functionalities like ViewModel integration,
    transient status signals, and basic UI setup hooks.
    """
    transient_status_signal = Signal(str)

    def __init__(self, view_model: T_ViewModel, parent: QFrame = None):
        """
        Initializes the BaseControlPanel.

        Args:
            view_model: The ViewModel instance for this panel.
            parent: The parent widget.
        """
        super().__init__(parent)
        self.view_model = view_model

        self._init_ui()
        self._connect_to_view_model()

    def _init_ui(self) -> None:
        """
        Abstract method to initialize UI elements.
        Subclasses must implement this.
        """
        raise NotImplementedError("Subclasses must implement _init_ui")

    def _connect_to_view_model(self) -> None:
        """
        Abstract method to connect signals from the ViewModel to panel slots.
        Subclasses must implement this.
        """
        raise NotImplementedError("Subclasses must implement _connect_to_view_model")

    @Slot(bool)
    def set_panel_enabled(self, enabled: bool) -> None:
        """
        Globally enables or disables all controls in this panel.
        Subclasses should override this to handle their specific widgets.
        """
        # Basic implementation, can be expanded by subclasses
        for child in self.findChildren(QWidget):
            child.setEnabled(enabled)

    def retranslate_ui(self) -> None:
        """
        Abstract method to retranslate all user-visible text in the panel.
        Subclasses must implement this.
        """
        raise NotImplementedError("Subclasses must implement retranslate_ui")