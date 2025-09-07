# -*- coding: utf-8 -*-
"""
中心化的Qt导入。

此模块为所有Qt相关导入提供单点入口，
便于在不同Qt绑定（例如PySide6）之间迁移，
并通过集中化框架依赖来提高代码的内聚性。
"""

# 将使用 PySide6
from PySide6.QtCore import (
    QObject,
    QTimer,
    QCoreApplication,
    Qt,
    QLocale,
    QEvent,
    QByteArray, # 重新添加 QByteArray 的导入
    Signal,
    Slot,
    QSize,
    QPoint,
    QRectF,
    QPointF,
    QRunnable,
    QThreadPool,
    Property,
    QBuffer,
    QIODevice
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
    QPixmap,
    QCursor,
    QIntValidator
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
    QComboBox,
    QToolTip,
    QStackedLayout,
    QDialog,
    QDialogButtonBox
)

# 为SVG图标导入，这可能需要 `pip install PySide6-Addons`
try:
    from PySide6.QtSvg import QSvgRenderer
except ImportError:
    print("警告: 未找到 PySide6.QtSvg 模块。SVG图标将无法显示。请运行 'pip install PySide6-Addons'。")
    QSvgRenderer = None