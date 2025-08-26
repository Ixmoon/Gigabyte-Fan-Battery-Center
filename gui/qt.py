# gui/qt.py
# -*- coding: utf-8 -*-
"""
Centralized Qt imports.

This module provides a single point of entry for all Qt-related imports,
allowing for easier migration between different Qt bindings (e.g., PySide6)
and improving code cohesion by centralizing framework dependencies.
"""

# This will be PySide6
from PySide6.QtCore import (
    QObject,
    QTimer,
    QCoreApplication,
    QMetaObject,
    Qt,
    QLocale,
    QEvent,
    QByteArray,
    Signal,
    Slot,
    QSize,
    QPoint,
    QRectF,
    QPointF,
    QThread,
    QRunnable,
    QThreadPool
)
from PySide6.QtGui import (
    QIcon,
    QAction,
    QPainter,
    QColor,
    QPen,
    QBrush,
    QFont,
    QPolygonF,
    QCloseEvent,
    QShowEvent,
    QHideEvent,
    QMouseEvent,
    QResizeEvent,
    QPixmap
)
from PySide6.QtWidgets import (
    QApplication,
    QMessageBox,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFrame,
    QSystemTrayIcon,
    QMenu,
    QStyle,
    QGridLayout,
    QLabel,
    QRadioButton,
    QButtonGroup,
    QSlider,
    QSpacerItem,
    QSizePolicy,
    QPushButton,
    QCheckBox,
    QInputDialog,
    QLineEdit,
    QComboBox
)