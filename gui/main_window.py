# gui/main_window.py
# -*- coding: utf-8 -*-
"""
Main application window (QMainWindow) for the Fan & Battery Control GUI.
Acts as the central controller for the UI, connecting user actions to services
and dispatching state updates to view components.
"""
import sys
import time
if sys.platform == 'win32':
    import ctypes
    from ctypes.wintypes import MSG
import os
from typing import List, Optional, Any

from .qt import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFrame, QMessageBox,
    QSystemTrayIcon, QMenu, QStyle, Qt, QTimer, Signal, QLocale, QEvent,
    Slot, QByteArray, QIcon, QAction, QCloseEvent, QShowEvent, QHideEvent,
    QLabel, QPushButton, QComboBox, QSize, QPoint, QMouseEvent,
    QRunnable, QThreadPool, QObject
)

from .lightweight_curve_canvas import LightweightCurveCanvas as CurveCanvas
from .StatusInfoPanel import StatusInfoPanel
from .CurveControlPanel import CurveControlPanel
from .FanControlPanel import FanControlPanel
from .BatteryControlPanel import BatteryControlPanel
from .custom_title_bar import CustomTitleBar
from .ui_builder import UIBuilder, FanControls, BatteryControls, StatusInfoControls, CurveControls

from core.state import AppState
from tools.localization import tr, get_available_languages, set_language, get_current_language
from tools.task_scheduler import create_startup_task, delete_startup_task, is_startup_task_registered
from config.settings import APP_NAME, APP_ICON_NAME

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from core.app_services import AppServices

CurveType = str
FanTable = List[List[int]]

class WorkerSignals(QObject):
    finished = Signal()

class StatusClearer(QRunnable):
    def __init__(self, delay_sec):
        super().__init__()
        self.delay_sec = delay_sec
        self.signals = WorkerSignals()

    def run(self):
        time.sleep(self.delay_sec)
        self.signals.finished.emit()

class MainWindow(QMainWindow):
    """Main application window."""
    main_tick = Signal()

    def __init__(self, app_services: 'AppServices', start_minimized: bool = False):
        super().__init__()
        self.app_services = app_services
        self.start_minimized = start_minimized

        # --- Internal State ---
        self.tray_icon: Optional[QSystemTrayIcon] = None
        self._is_quitting: bool = False
        self._is_window_visible: bool = not start_minimized
        self._is_showing_transient_status: bool = False
        self.command_poll_timer: Optional[QTimer] = None
        self._is_initialized: bool = False
        self.thread_pool = QThreadPool()

        # --- UI Components ---
        self.title_bar: Optional[CustomTitleBar] = None
        self.status_info_panel: Optional[StatusInfoPanel] = None
        self.curve_control_panel: Optional[CurveControlPanel] = None
        self.fan_control_panel: Optional[FanControlPanel] = None
        self.battery_control_panel: Optional[BatteryControlPanel] = None
        self.curve_canvas: Optional[CurveCanvas] = None
        
        # --- Control Collections (from UIBuilder) ---
        self.fan_controls: Optional[FanControls] = None
        self.battery_controls: Optional[BatteryControls] = None
        self.status_info_controls: Optional[StatusInfoControls] = None
        self.curve_controls: Optional[CurveControls] = None

        self._apply_locale(get_current_language())
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
            self.app_services.set_ui_visibility(True)

        self._start_command_poller()

    def _restore_geometry(self):
        geometry_str = self.app_services.state.window_geometry
        if geometry_str:
            try:
                self.restoreGeometry(QByteArray.fromHex(geometry_str.encode('ascii')))
            except (ValueError, TypeError):
                print(f"Warning: Could not restore geometry from invalid hex.", file=sys.stderr)
                self.resize(1150, 700)

    def _apply_locale(self, lang_code: str):
        try:
            QLocale.setDefault(QLocale(lang_code))
        except Exception as e:
            print(f"Warning: Could not set locale for '{lang_code}': {e}", file=sys.stderr)

    def init_ui(self):
        self.setWindowTitle(tr("window_title"))
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)

        main_container = QWidget()
        main_container.setObjectName("mainContainer")
        self.setCentralWidget(main_container)

        overall_layout = QVBoxLayout(main_container)
        overall_layout.setContentsMargins(0, 0, 0, 0)
        overall_layout.setSpacing(0)

        self.title_bar = CustomTitleBar(self)
        overall_layout.addWidget(self.title_bar)

        content_widget = QWidget()
        content_widget.setObjectName("contentWidget")
        main_layout = QVBoxLayout(content_widget)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)
        overall_layout.addWidget(content_widget)

        builder = UIBuilder()

        status_panel_container = QFrame()
        self.status_info_controls = builder.build_status_info_panel(status_panel_container)
        self.status_info_panel = StatusInfoPanel(self.status_info_controls, status_panel_container)
        main_layout.addWidget(status_panel_container)

        curve_area_frame = QFrame()
        curve_area_frame.setObjectName("curveFrame")
        curve_area_frame.setFrameShape(QFrame.Shape.StyledPanel)
        curve_area_layout = QVBoxLayout(curve_area_frame)
        curve_area_layout.setContentsMargins(15, 15, 15, 15)
        curve_area_layout.setSpacing(5)

        curve_panel_container = QFrame()
        self.curve_controls = builder.build_curve_control_panel(curve_panel_container)
        self.curve_control_panel = CurveControlPanel(self.curve_controls, self.app_services, curve_panel_container)
        curve_area_layout.addWidget(curve_panel_container)

        self.curve_canvas = CurveCanvas(self)
        curve_area_layout.addWidget(self.curve_canvas)

        main_layout.addWidget(curve_area_frame)
        main_layout.setStretchFactor(curve_area_frame, 1)

        bottom_controls_frame = QFrame()
        bottom_controls_frame.setObjectName("controlFrame")
        bottom_controls_frame.setFrameShape(QFrame.Shape.StyledPanel)
        bottom_controls_layout = QHBoxLayout(bottom_controls_frame)
        bottom_controls_layout.setContentsMargins(10, 10, 10, 10)
        bottom_controls_layout.setSpacing(20)

        fan_battery_layout = QVBoxLayout()
        fan_battery_layout.setSpacing(10)

        fan_panel_container = QFrame()
        self.fan_controls = builder.build_fan_panel(fan_panel_container)
        self.fan_control_panel = FanControlPanel(self.fan_controls, fan_panel_container)
        fan_battery_layout.addWidget(fan_panel_container)

        battery_panel_container = QFrame()
        self.battery_controls = builder.build_battery_panel(battery_panel_container)
        self.battery_control_panel = BatteryControlPanel(self.battery_controls, battery_panel_container)
        fan_battery_layout.addWidget(battery_panel_container)

        bottom_controls_layout.addLayout(fan_battery_layout, 1)
        main_layout.addWidget(bottom_controls_frame)

    def connect_signals(self):
        if self.title_bar:
            self.title_bar.language_changed_signal.connect(self._handle_language_change)
            self.title_bar.minimize_button.clicked.connect(self.showMinimized)
            self.title_bar.maximize_button.clicked.connect(self._toggle_maximize)
            self.title_bar.close_button.clicked.connect(self.close)

        self.app_services.state_changed.connect(self.on_state_changed)
        self.main_tick.connect(self.app_services.on_main_tick)

        if self.fan_controls:
            fc = self.fan_controls
            fc.bios_fan_mode_radio.toggled.connect(
                lambda checked: self.app_services.set_fan_mode("bios") if checked else None
            )
            fc.auto_fan_mode_radio.toggled.connect(
                lambda checked: self.app_services.set_fan_mode("auto") if checked else None
            )
            fc.custom_fan_mode_radio.toggled.connect(
                lambda checked: self.app_services.set_fan_mode("custom") if checked else None
            )
            fc.custom_fan_speed_slider.valueChanged.connect(
                 lambda value: fc.custom_fan_speed_value_label.setText(f"{value}{tr('percent_unit')}")
            )
            fc.custom_fan_speed_slider.sliderReleased.connect(
                lambda: self.app_services.set_custom_fan_speed(fc.custom_fan_speed_slider.value())
            )

        if self.battery_controls:
            bc = self.battery_controls
            bc.bios_charge_radio.toggled.connect(
                lambda checked: self.app_services.set_battery_charge_policy("bios") if checked else None
            )
            bc.custom_charge_radio.toggled.connect(
                lambda checked: self.app_services.set_battery_charge_policy("custom") if checked else None
            )
            bc.charge_threshold_slider.valueChanged.connect(
                lambda value: bc.charge_threshold_value_label.setText(f"{value}{tr('percent_unit')}")
            )
            bc.charge_threshold_slider.sliderReleased.connect(
                lambda: self.app_services.set_battery_charge_threshold(bc.charge_threshold_slider.value())
            )

        if self.curve_canvas:
            self.curve_canvas.point_dragged.connect(self.on_curve_point_dragged)
            self.curve_canvas.curve_changed.connect(self.on_curve_modified)

        if self.curve_control_panel:
            self.curve_control_panel.transient_status_signal.connect(self.set_transient_status)

    def init_tray_icon(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.tray_icon = None
            return

        self.tray_icon = QSystemTrayIcon(self)
        
        base_dir = self.app_services.base_dir
        external_icon_path = os.path.join(base_dir, APP_ICON_NAME)
        external_icon = QIcon(external_icon_path)

        final_icon = None
        if not external_icon.isNull():
            final_icon = external_icon
        else:
            window_icon = self.windowIcon()
            if not window_icon.isNull():
                final_icon = window_icon
            else:
                final_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)

        self.setWindowIcon(final_icon)
        self.tray_icon.setIcon(final_icon)
        if self.title_bar:
            self.title_bar.icon_label.setPixmap(final_icon.pixmap(QSize(24, 24)))
 
        self.tray_icon.setToolTip(tr("window_title"))
 
        tray_menu = QMenu(self)
        show_hide_action = QAction(tr("tray_menu_show_hide"), self)
        show_hide_action.triggered.connect(self.toggle_window_visibility)
        tray_menu.addAction(show_hide_action)
        tray_menu.addSeparator()
        quit_action = QAction(tr("tray_menu_quit"), self)
        quit_action.triggered.connect(self._request_quit)
        tray_menu.addAction(quit_action)
        self.tray_icon.setContextMenu(tray_menu)

        self.tray_icon.activated.connect(self.on_tray_icon_activated)

        if not self.start_minimized:
            self.tray_icon.show()

    def apply_styles(self):
        style_sheet_path = os.path.join(os.path.dirname(__file__), "style.qss")
        try:
            with open(style_sheet_path, "r", encoding="utf-8") as f:
                self.setStyleSheet(f.read())
        except Exception as e:
            print(f"Warning: Could not load stylesheet. Error: {e}", file=sys.stderr)

    @Slot(object)
    def on_state_changed(self, state: AppState):
        if not self._is_window_visible:
            return
        
        if self.status_info_panel: self.status_info_panel.update_state(state)
        if self.fan_control_panel: self.fan_control_panel.update_state(state)
        if self.battery_control_panel: self.battery_control_panel.update_state(state)
        if self.curve_control_panel: self.curve_control_panel.update_state(state)

        if self.curve_canvas:
            self.curve_canvas.update_temp_indicators(state.cpu_temp, state.gpu_temp)
            self.curve_canvas.set_active_curve(state.active_curve_type)
            active_profile = state.profiles.get(state.active_profile_name)
            if active_profile:
                self.curve_canvas.update_plot(active_profile.cpu_fan_table, active_profile.gpu_fan_table)

        status_key = state.controller_status_message
        if self.title_bar:
            self.title_bar.status_label.setText(tr(status_key) if status_key else "")

    @Slot(str)
    def set_transient_status(self, message: str, duration_ms: int = 2000):
        if self._is_window_visible and self.title_bar:
            self.title_bar.status_label.setText(message)
        
        self._is_showing_transient_status = True
        
        # Use a worker thread to clear the status after a delay
        worker = StatusClearer(delay_sec=duration_ms / 1000.0)
        worker.signals.finished.connect(self._clear_transient_status)
        self.thread_pool.start(worker)

    def _clear_transient_status(self):
        self._is_showing_transient_status = False
        # Ensure this is run on the main thread, although signal connection should handle it
        self.on_state_changed(self.app_services.state)

    @Slot(str, int, float, float)
    def on_curve_point_dragged(self, curve_type: str, index: int, new_temp: float, new_speed: float):
        self.set_transient_status(tr("curve_point_tooltip", temp=int(new_temp), speed=int(new_speed)))

    @Slot(str)
    def on_curve_modified(self, curve_type: str):
        if self.curve_canvas:
            final_table = self.curve_canvas.get_curve_data(curve_type)
            self.app_services.set_curve_data(curve_type, final_table)
            self.set_transient_status(tr("saving_config"))

    @Slot(str)
    def _handle_language_change(self, lang_code: str):
        set_language(lang_code)
        self.app_services.set_language(lang_code)
        self.retranslate_ui()

    def retranslate_ui(self):
        self.setWindowTitle(tr("window_title"))
        if self.title_bar: self.title_bar.retranslate_ui()
        if self.status_info_panel: self.status_info_panel.retranslate_ui()
        if self.curve_control_panel: self.curve_control_panel.retranslate_ui()
        if self.fan_control_panel: self.fan_control_panel.retranslate_ui()
        if self.battery_control_panel: self.battery_control_panel.retranslate_ui()
        if self.curve_canvas: self.curve_canvas.retranslate_ui()

        if self.tray_icon and self.tray_icon.contextMenu():
            menu = self.tray_icon.contextMenu()
            actions = menu.actions()
            if len(actions) >= 2:
                actions[0].setText(tr("tray_menu_show_hide"))
                actions[-1].setText(tr("tray_menu_quit"))
        
        self.on_state_changed(self.app_services.state)

    def _start_command_poller(self):
        from tools.single_instance import read_command_from_shared_memory, write_command_to_shared_memory
        from config.settings import COMMAND_NONE

        self.command_poll_timer = QTimer(self)
        self.command_poll_timer.setInterval(500) # Global 500ms heartbeat

        def _on_poll_tick():
            # 1. Emit the main application tick signal
            self.main_tick.emit()

            # 2. Check for single-instance commands
            command = read_command_from_shared_memory()
            if command is not None and command != COMMAND_NONE:
                write_command_to_shared_memory(COMMAND_NONE)
                self._handle_command(command)

        self.command_poll_timer.timeout.connect(_on_poll_tick)
        self.command_poll_timer.start()

    def _handle_command(self, command: int):
        from config.settings import COMMAND_QUIT, COMMAND_RELOAD_AND_SHOW
        if command == COMMAND_QUIT:
            self._request_quit()
        elif command == COMMAND_RELOAD_AND_SHOW:
            if not self.isVisible() or self.isMinimized():
                self.toggle_window_visibility()

    def showEvent(self, event: QShowEvent):
        if not self._is_initialized:
            self._is_initialized = True
            # This signal is no longer needed as initialization is synchronous
            # QTimer.singleShot(0, lambda: self.window_initialized_signal.emit(int(self.winId())))

        if not self._is_window_visible:
            self._is_window_visible = True
            self.app_services.set_ui_visibility(True)
            self.on_state_changed(self.app_services.state)
        
        super().showEvent(event)

    def hideEvent(self, event: QHideEvent):
        if self._is_window_visible:
            self._is_window_visible = False
            self.app_services.set_ui_visibility(False)
            if self.title_bar and self.title_bar.status_label.text() != tr("shutting_down"):
                self.set_transient_status(tr("paused"))
        super().hideEvent(event)

    def _toggle_maximize(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    if sys.platform == 'win32':
        def nativeEvent(self, event_type: Any, message: int) -> tuple[bool, int]:
            if event_type == b"windows_generic_MSG":
                msg = MSG.from_address(message.__int__())
                if msg.message == 0x0084: # WM_NCHITTEST
                    if self.isMaximized(): return True, 1
                    local_pos = self.mapFromGlobal(QPoint(msg.lParam & 0xFFFF, (msg.lParam >> 16) & 0xFFFF))
                    border_width = 8
                    on_left = local_pos.x() < border_width
                    on_right = local_pos.x() > self.width() - border_width
                    on_top = local_pos.y() < border_width
                    on_bottom = local_pos.y() > self.height() - border_width
                    if on_top and on_left: return True, 13
                    if on_top and on_right: return True, 14
                    if on_bottom and on_left: return True, 16
                    if on_bottom and on_right: return True, 17
                    if on_left: return True, 10
                    if on_right: return True, 11
                    if on_top: return True, 12
                    if on_bottom: return True, 15
                    if self.title_bar and local_pos.y() < self.title_bar.height():
                        child_widget = self.title_bar.childAt(self.title_bar.mapFrom(self, local_pos))
                        if isinstance(child_widget, (QPushButton, QComboBox)):
                            return super().nativeEvent(event_type, message) # type: ignore
                        return True, 2
            return super().nativeEvent(event_type, message) # type: ignore

    @Slot(QSystemTrayIcon.ActivationReason)
    def on_tray_icon_activated(self, reason: QSystemTrayIcon.ActivationReason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.toggle_window_visibility()

    def toggle_window_visibility(self):
        if self.isVisible() and not self.isMinimized():
            self.hide()
        else:
            self.showNormal()
            self.activateWindow()
            self.raise_()

    def _request_quit(self):
        if self._is_quitting: return
        self._is_quitting = True
        self._shutdown_services()
        app = QApplication.instance()
        if app:
            QTimer.singleShot(0, app.quit)

    def _shutdown_services(self):
        try:
            geometry_str = bytes(self.saveGeometry().toHex().data()).decode('ascii')
            self.app_services.set_window_geometry(geometry_str)
        except Exception as e:
            print(f"Warning: Failed to save window geometry on close: {e}", file=sys.stderr)
        self.app_services.shutdown()

    def closeEvent(self, event: QCloseEvent):
        if self._is_quitting:
            event.accept()
            return
        if self.tray_icon and self.tray_icon.isVisible():
            self.hide()
            event.ignore()
        else:
            self._request_quit()
            event.accept()
