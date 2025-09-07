# -*- coding: utf-8 -*-
"""
主应用窗口(QMainWindow)，作为UI的中心控制器，
连接用户操作与服务，并将状态更新分派给视图组件。
"""
import sys
import time
import os
from typing import Optional, Any

from .qt import *
from .lightweight_curve_canvas import LightweightCurveCanvas as CurveCanvas
from .StatusInfoPanel import StatusInfoPanel
from .CurveControlPanel import CurveControlPanel
from .FanControlPanel import FanControlPanel
from .BatteryControlPanel import BatteryControlPanel
from .custom_title_bar import CustomTitleBar
from core.state import AppState, ProfileState
from tools.localization import tr, set_language
from core.app_services import AppServices
from core.profile_manager import ProfileManager
from core.settings_manager import SettingsManager

class MainWindow(QMainWindow):
    """主应用窗口。"""
    gui_tick = Signal()
    window_initialized_signal = Signal(int)

    def __init__(self, app_services: AppServices, state: AppState, profile_manager: ProfileManager, settings_manager: SettingsManager, start_minimized: bool = False):
        super().__init__()
        self.app_services = app_services
        self.state = state
        self.profile_manager = profile_manager
        self.settings_manager = settings_manager
        self.start_minimized = start_minimized
        
        self.tray_icon: Optional[QSystemTrayIcon] = None
        self._is_quitting: bool = False
        self._is_showing_transient_status: bool = False
        self.status_clear_timer = QTimer(self)
        self.status_clear_timer.setSingleShot(True)
        
        self.gui_update_timer = QTimer(self)
        self.command_poll_timer: Optional[QTimer] = None
        self._is_initialized: bool = False
        
        self._apply_locale()
        self.init_ui()
        self.connect_signals()
        self.init_tray_icon()
        self.apply_styles()
        self.resize(1150, 700)
        self._restore_geometry()

        if self.start_minimized:
            if self.tray_icon: self.tray_icon.show()
            self.app_services.set_ui_visibility(False)
        else:
            self.show()

        self._start_command_poller()

    def _restore_geometry(self):
        geometry_str = self.state.window_geometry
        if geometry_str:
            try:
                self.restoreGeometry(QByteArray.fromHex(geometry_str.encode('ascii')))
            except (ValueError, TypeError): self.resize(1150, 700)

    def _apply_locale(self):
        QLocale.setDefault(QLocale(self.state.get_language()))

    def init_ui(self):
        self.setWindowTitle(tr("window_title"))
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        main_container = QWidget()
        main_container.setObjectName("mainContainer")
        self.setCentralWidget(main_container)
        overall_layout = QVBoxLayout(main_container)
        overall_layout.setContentsMargins(0, 0, 0, 0); overall_layout.setSpacing(0)
        self.title_bar = CustomTitleBar(self.settings_manager, self)
        overall_layout.addWidget(self.title_bar)
        content_widget = QWidget()
        content_widget.setObjectName("contentWidget")
        main_layout = QVBoxLayout(content_widget)
        main_layout.setContentsMargins(15, 15, 15, 15); main_layout.setSpacing(15)
        overall_layout.addWidget(content_widget)
        self.status_info_panel = StatusInfoPanel(self.state, self)
        main_layout.addWidget(self.status_info_panel)
        curve_area_frame = QFrame()
        curve_area_frame.setObjectName("curveFrame")
        curve_area_layout = QVBoxLayout(curve_area_frame)
        curve_area_layout.setContentsMargins(15, 15, 15, 15); curve_area_layout.setSpacing(5)
        self.curve_control_panel = CurveControlPanel(self.profile_manager, self.settings_manager, self.state, self)
        self.curve_canvas = CurveCanvas(self.state, self.profile_manager, self)
        curve_area_layout.addWidget(self.curve_control_panel)
        curve_area_layout.addWidget(self.curve_canvas)
        main_layout.addWidget(curve_area_frame, 1)
        bottom_controls_frame = QFrame()
        bottom_controls_frame.setObjectName("controlFrame")
        bottom_controls_layout = QVBoxLayout(bottom_controls_frame)
        self.fan_control_panel = FanControlPanel(self.state, self.profile_manager, self)
        self.battery_control_panel = BatteryControlPanel(self.state, self.profile_manager, self)
        bottom_controls_layout.addWidget(self.fan_control_panel)
        bottom_controls_layout.addWidget(self.battery_control_panel)
        main_layout.addWidget(bottom_controls_frame)

    def connect_signals(self):
        self.title_bar.minimize_button.clicked.connect(self.showMinimized)
        self.title_bar.maximize_button.clicked.connect(self._toggle_maximize)
        self.title_bar.close_button.clicked.connect(self.close)
        
        self.gui_tick.connect(self.app_services.on_gui_tick)
        
        self.state.controller_status_message_changed.connect(self._update_status_bar)
        self.state.active_profile_changed.connect(self._on_active_profile_changed)
        self.state.language_changed.connect(self._on_language_changed_by_state)

        self.curve_canvas.point_dragged.connect(self.on_curve_point_dragged)
        self.curve_control_panel.transient_status_signal.connect(self.set_transient_status)
        self.curve_canvas.transient_status_signal.connect(self.set_transient_status)
        self.status_clear_timer.timeout.connect(self._clear_transient_status)

    def init_tray_icon(self):
        if not QSystemTrayIcon.isSystemTrayAvailable(): return
        self.tray_icon = QSystemTrayIcon(self)
        icon = QIcon(self.state.paths.app_icon)
        self.setWindowIcon(icon)
        self.tray_icon.setIcon(icon)
        self.title_bar.icon_label.setPixmap(icon.pixmap(QSize(24, 24)))
        self.tray_icon.setToolTip(tr("window_title"))
        tray_menu = QMenu(self)
        show_hide_action = QAction(tr("tray_menu_show_hide"), self)
        show_hide_action.triggered.connect(self.toggle_window_visibility)
        quit_action = QAction(tr("tray_menu_quit"), self)
        quit_action.triggered.connect(self._request_quit)
        tray_menu.addAction(show_hide_action); tray_menu.addSeparator(); tray_menu.addAction(quit_action)
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.on_tray_icon_activated)
        if not self.start_minimized:
            self.tray_icon.show()

    def apply_styles(self):
        style_path = self.state.paths.style_qss
        if os.path.exists(style_path):
            with open(style_path, "r", encoding="utf-8") as f:
                self.setStyleSheet(f.read())

    @Slot(ProfileState)
    def _on_active_profile_changed(self, profile: ProfileState):
        if profile:
            new_interval = profile.get_value('gui_update_interval_ms', 1000)
            if self.gui_update_timer.interval() != new_interval:
                self.gui_update_timer.setInterval(new_interval)

    @Slot(str)
    def _update_status_bar(self, message: str):
        if not self._is_showing_transient_status:
            self.title_bar.status_label.setText(tr(message) if message else "")

    @Slot(str, int)
    def set_transient_status(self, message: str, duration_ms: int = 2000):
        self.status_clear_timer.stop()
        self.title_bar.status_label.setText(message)
        self._is_showing_transient_status = True
        self.status_clear_timer.start(duration_ms)

    def _clear_transient_status(self):
        self._is_showing_transient_status = False
        self._update_status_bar(self.state.get_controller_status_message())

    @Slot(str, int, float, float)
    def on_curve_point_dragged(self, curve_type: str, index: int, new_temp: float, new_speed: float):
        self.set_transient_status(tr("curve_point_tooltip", temp=int(new_temp), speed=int(new_speed)))

    @Slot(str)
    def _on_language_changed_by_state(self, lang_code: str):
        set_language(lang_code)
        self.retranslate_ui()

    def retranslate_ui(self):
        self.setWindowTitle(tr("window_title"))
        self.title_bar.retranslate_ui()
        self.status_info_panel.retranslate_ui()
        self.curve_control_panel.retranslate_ui()
        self.fan_control_panel.retranslate_ui()
        self.battery_control_panel.retranslate_ui()
        self.curve_canvas.retranslate_ui()
        if self.tray_icon and self.tray_icon.contextMenu():
            actions = self.tray_icon.contextMenu().actions()
            actions[0].setText(tr("tray_menu_show_hide"))
            actions[-1].setText(tr("tray_menu_quit"))
        self._update_status_bar(self.state.get_controller_status_message())

    def _start_gui_timer(self):
        active_profile = self.state.get_active_profile()
        initial_interval = active_profile.get_value('gui_update_interval_ms', 1000) if active_profile else 1000
        self.gui_update_timer.setInterval(initial_interval)
        self.gui_update_timer.timeout.connect(self.gui_tick.emit)
        self.gui_update_timer.start()

    def _start_command_poller(self):
        from tools.single_instance import read_command_from_shared_memory, write_command_to_shared_memory, COMMAND_NONE
        self.command_poll_timer = QTimer(self)
        self.command_poll_timer.setInterval(500)
        def _on_poll_tick():
            command = read_command_from_shared_memory()
            if command is not None and command != COMMAND_NONE:
                write_command_to_shared_memory(COMMAND_NONE)
                self._handle_command(command)
        self.command_poll_timer.timeout.connect(_on_poll_tick)
        self.command_poll_timer.start()

    def _handle_command(self, command: int):
        from config.settings import COMMAND_QUIT, COMMAND_RELOAD_AND_SHOW, COMMAND_RELOAD_ONLY
        if command == COMMAND_QUIT: self._request_quit()
        elif command == COMMAND_RELOAD_AND_SHOW:
            self.profile_manager.reload_and_apply_active_profile()
            self.toggle_window_visibility(force_show=True)
        elif command == COMMAND_RELOAD_ONLY:
            self.profile_manager.reload_and_apply_active_profile()

    def showEvent(self, event: QShowEvent):
        if not self._is_initialized:
            self._is_initialized = True
            QTimer.singleShot(0, lambda: self.window_initialized_signal.emit(int(self.winId())))
        
        # 调用AppServices中的方法来处理UI可见性变化
        self.app_services.set_ui_visibility(True)
        self._start_gui_timer()
        super().showEvent(event)

    def hideEvent(self, event: QHideEvent):
        self.gui_update_timer.stop()
        # 调用AppServices中的方法来处理UI可见性变化
        self.app_services.set_ui_visibility(False)
        super().hideEvent(event)

    def _toggle_maximize(self):
        self.showNormal() if self.isMaximized() else self.showMaximized()

    def changeEvent(self, event: QEvent):
        if event.type() == QEvent.Type.WindowStateChange:
            self.title_bar.update_window_state(self.isMaximized())
        super().changeEvent(event)

    if sys.platform == 'win32':
        def nativeEvent(self, event_type: Any, message: int) -> tuple[bool, int]:
            from ctypes.wintypes import MSG
            msg = MSG.from_address(message.__int__())

            if msg.message == 0x0083: # WM_NCCALCSIZE
                return True, 0

            if msg.message == 0x00A3: # WM_NCLBUTTONDBLCLK
                pos = QPoint(msg.lParam & 0xFFFF, (msg.lParam >> 16) & 0xFFFF)
                # 检查双击是否在标题栏的非按钮区域
                if self.title_bar.geometry().contains(self.mapFromGlobal(pos)):
                    child = self.title_bar.childAt(self.title_bar.mapFromGlobal(pos))
                    if not isinstance(child, (QPushButton, QComboBox)):
                        self._toggle_maximize()
                        return True, 0

            if msg.message == 0x0084: # WM_NCHITTEST
                pos = self.mapFromGlobal(QPoint(msg.lParam & 0xFFFF, (msg.lParam >> 16) & 0xFFFF))
                
                # 仅在窗口化状态下检查边框用于缩放
                if not self.isMaximized():
                    border=8; on_left=pos.x()<border; on_right=pos.x()>self.width()-border; on_top=pos.y()<border; on_bottom=pos.y()>self.height()-border
                    if on_top and on_left: return True, 13
                    if on_top and on_right: return True, 14
                    if on_bottom and on_left: return True, 16
                    if on_bottom and on_right: return True, 17
                    if on_left: return True, 10
                    if on_right: return True, 11
                    if on_top: return True, 12
                    if on_bottom: return True, 15
                
                if self.title_bar and pos.y() < self.title_bar.height():
                    child = self.title_bar.childAt(self.title_bar.mapFrom(self, pos))
                    if isinstance(child, (QPushButton, QComboBox)):
                        result = super().nativeEvent(event_type, message)
                        return (bool(result[0]), int(result[1])) if isinstance(result, (tuple, list)) and len(result) == 2 else (False, 0)
                    return True, 2 # HTCAPTION
            
            result = super().nativeEvent(event_type, message)
            return (bool(result[0]), int(result[1])) if isinstance(result, (tuple, list)) and len(result) == 2 else (False, 0)

    @Slot(QSystemTrayIcon.ActivationReason)
    def on_tray_icon_activated(self, reason: QSystemTrayIcon.ActivationReason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.toggle_window_visibility()

    def toggle_window_visibility(self, force_show: bool = False):
        if force_show or not self.isVisible() or self.isMinimized():
            self.showNormal(); self.activateWindow(); self.raise_()
        else: self.hide()

    def _request_quit(self):
        if self._is_quitting: return
        self._is_quitting = True
        self._shutdown_services()
        app = QApplication.instance()
        if app: app.quit()

    def _shutdown_services(self):
        try:
            geometry_str = bytes(self.saveGeometry().toHex().data()).decode('ascii')
            self.settings_manager.set_window_geometry(geometry_str)
        except Exception as e:
            print(f"警告: 关闭时保存窗口几何信息失败: {e}", file=sys.stderr)

    def closeEvent(self, event: QCloseEvent):
        if self._is_quitting: event.accept()
        elif self.tray_icon and self.tray_icon.isVisible():
            self.hide(); event.ignore()
        else:
            self._request_quit(); event.accept()