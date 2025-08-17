# File: 9 gui/main_window.py (Modified Again)
# gui/main_window.py
# -*- coding: utf-8 -*-
"""
Main application window (QMainWindow) for the Fan & Battery Control GUI.
"""

import sys
if sys.platform == 'win32':
    import ctypes
    from ctypes.wintypes import MSG
import os
from typing import List, Optional, Any

from .qt import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFrame, QMessageBox,
    QSystemTrayIcon, QMenu, QStyle, Qt, QTimer, Signal, QLocale, QEvent,
    Slot, QByteArray, QIcon, QAction, QCloseEvent, QShowEvent, QHideEvent,
    QLabel, QPushButton, QComboBox, QSize, QPoint, QMouseEvent
)

from .lightweight_curve_canvas import LightweightCurveCanvas as CurveCanvas
from .StatusInfoPanel import StatusInfoPanel
from .CurveControlPanel import CurveControlPanel
from .FanControlPanel import FanControlPanel
from .BatteryControlPanel import BatteryControlPanel
from .custom_title_bar import CustomTitleBar

# --- ViewModel Imports Removed ---

from core.state import AppState # Import the main state object
from tools.localization import tr, get_available_languages, set_language, get_current_language
from tools.task_scheduler import create_startup_task, delete_startup_task, is_startup_task_registered
from config.settings import (
    APP_NAME, APP_ICON_NAME, DEFAULT_PROFILE_SETTINGS
)

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from main import AppRunner
    from core.app_services import AppServices

# AppStatus NamedTuple is removed, replaced by AppState.runtime

CurveType = str
FanTable = List[List[int]]

SLIDER_UPDATE_BLOCK_DURATION_MS = 1500

class MainWindow(QMainWindow):
    """Main application window."""

    # --- Signals to AppServices (via AppRunner) ---
    quit_requested = Signal()
    # curve_changed_signal will be removed, panels will call app_services directly
    language_changed_signal = Signal(str)
    background_state_changed = Signal(bool)
    window_geometry_changed = Signal(str)
    window_initialized_signal = Signal(int)

    def __init__(self,
                 app_runner: 'AppRunner',
                 app_services: 'AppServices',
                 start_minimized: bool = False):
        super().__init__()
        self.app_runner = app_runner
        self.app_services = app_services
        self.start_minimized = start_minimized

        # --- ViewModel Instances Removed ---

        # --- Internal State ---
        self.last_state: Optional[AppState] = None
        self.tray_icon: Optional[QSystemTrayIcon] = None
        self._is_quitting: bool = False
        self._is_window_visible: bool = not start_minimized
        self._is_showing_transient_status: bool = False
        self.command_poll_timer: Optional[QTimer] = None
        self._transient_status_timer: Optional[QTimer] = None
        self._is_initialized: bool = False # Flag to ensure HWND is sent only once

        # --- Panel Members ---
        self.title_bar: Optional[CustomTitleBar] = None
        self.status_info_panel: Optional[StatusInfoPanel] = None
        self.curve_control_panel: Optional[CurveControlPanel] = None
        self.fan_control_panel: Optional[FanControlPanel] = None
        self.battery_control_panel: Optional[BatteryControlPanel] = None
        self.curve_canvas: Optional[CurveCanvas] = None

        self._apply_locale(get_current_language())
        self.init_ui()
        self.init_tray_icon()
        self.apply_styles()
        # Geometry is now restored by AppRunner after window is created
        self.resize(1150, 700) # Set a default size

        if self.start_minimized:
            if self.tray_icon: self.tray_icon.show()
            self.background_state_changed.emit(True)
        else:
            self.show()
            self.background_state_changed.emit(False)

        self._start_command_poller()

    def restore_geometry_from_hex(self, geometry_hex: str):
        """Restores window geometry from a hex string."""
        try:
            self.restoreGeometry(QByteArray.fromHex(bytes(geometry_hex, 'utf-8')))
        except (ValueError, TypeError):
            print(f"Warning: Could not restore geometry from invalid hex: {geometry_hex}", file=sys.stderr)
            self.resize(1150, 700)

    def _apply_locale(self, lang_code: str):
        """Sets the Qt application locale."""
        try:
            QLocale.setDefault(QLocale(lang_code))
        except Exception as e:
            print(f"Warning: Could not set locale for '{lang_code}': {e}", file=sys.stderr)

    def init_ui(self):
        """Creates and lays out all UI widgets."""
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

        self.status_info_panel = StatusInfoPanel(self)
        main_layout.addWidget(self.status_info_panel)

        curve_area_frame = QFrame()
        curve_area_frame.setObjectName("curveFrame")
        curve_area_frame.setFrameShape(QFrame.Shape.StyledPanel)
        curve_area_layout = QVBoxLayout(curve_area_frame)
        curve_area_layout.setContentsMargins(15, 15, 15, 15)
        curve_area_layout.setSpacing(5)

        # The old ViewModel instantiation for CurveControlPanel is now removed.
        # self.curve_control_view_model = CurveControlViewModel(self.app_services)
        self.curve_control_panel = CurveControlPanel(self.app_services, self)
        curve_area_layout.addWidget(self.curve_control_panel)

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

        self.fan_control_panel = FanControlPanel(self.app_services, self)
        fan_battery_layout.addWidget(self.fan_control_panel)

        self.battery_control_panel = BatteryControlPanel(self.app_services, self)
        fan_battery_layout.addWidget(self.battery_control_panel)

        bottom_controls_layout.addLayout(fan_battery_layout, 1)
        main_layout.addWidget(bottom_controls_frame)

        self.connect_signals()

    # def _populate_language_combo(self): # Moved to SettingsPanel
    #     """Populates the language selection QComboBox."""
    #     self.language_combo.blockSignals(True) # Prevent signals during population
    #     self.language_combo.clear()
    #     current_lang_code = get_current_language()
    #     available_langs = get_available_languages() # Returns dict {code: display_name}
    #     current_idx = 0
    #     codes_in_order = sorted(available_langs.keys()) # Ensure consistent order
    #     for i, code in enumerate(codes_in_order):
    #         display_name = available_langs[code]
    #         self.language_combo.addItem(display_name, code) # Store code as item data
    #         if code == current_lang_code:
    #             current_idx = i
    #     self.language_combo.setCurrentIndex(current_idx)
    #     self.language_combo.blockSignals(False)

    def init_tray_icon(self):
        """Initializes the system tray icon and menu with a robust fallback mechanism."""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.tray_icon = None
            return

        self.tray_icon = QSystemTrayIcon(self)
        
        # --- Step 1: Attempt to load the external icon file ---
        # The base_dir is now accessed directly from app_services
        base_dir = self.app_services.base_dir
        external_icon_path = os.path.join(base_dir, APP_ICON_NAME)
        external_icon = QIcon(external_icon_path)

        final_icon = None
        if not external_icon.isNull():
            print(f"Successfully loaded external icon from: {external_icon_path}")
            final_icon = external_icon
        else:
            print("External icon not found or invalid. Falling back to window's default icon (from .exe).")
            window_icon = self.windowIcon()
            if not window_icon.isNull():
                final_icon = window_icon
            else:
                print("Warning: No valid embedded or external icon found. Using generic system icon.")
                default_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
                final_icon = default_icon

        self.setWindowIcon(final_icon)
        self.tray_icon.setIcon(final_icon)
        if self.title_bar:
            self.title_bar.icon_label.setPixmap(final_icon.pixmap(QSize(24, 24)))
 
        self.tray_icon.setToolTip(tr("window_title"))
 
        # Create tray menu
        tray_menu = QMenu(self)
        show_hide_action = QAction(tr("tray_menu_show_hide"), self)
        show_hide_action.triggered.connect(self.toggle_window_visibility)
        tray_menu.addAction(show_hide_action)
        tray_menu.addSeparator()
        quit_action = QAction(tr("tray_menu_quit"), self)
        quit_action.triggered.connect(self._request_quit)
        tray_menu.addAction(quit_action)
        self.tray_icon.setContextMenu(tray_menu)

        # Connect activation signal
        self.tray_icon.activated.connect(self.on_tray_icon_activated)

        # Show icon immediately unless starting minimized
        if not self.start_minimized:
            self.tray_icon.show()

    def _use_default_icon(self):
        """Sets a generic system icon as the last resort."""
        default_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        self.setWindowIcon(default_icon)
        if self.tray_icon:
            self.tray_icon.setIcon(default_icon)
        if self.title_bar:
            self.title_bar.icon_label.setPixmap(default_icon.pixmap(QSize(24, 24)))

    def connect_signals(self):
        """Connects signals from UI components to MainWindow's handlers or re-emits them."""
        if self.title_bar:
            self.title_bar.language_changed_signal.connect(self.language_changed_signal.emit)
            self.title_bar.minimize_button.clicked.connect(self.showMinimized)
            self.title_bar.maximize_button.clicked.connect(self._toggle_maximize)
            self.title_bar.close_button.clicked.connect(self.close)

        # --- Connect AppServices state changes to the main update slot ---
        self.app_services.state_changed.connect(self.on_state_changed)

        # --- Connect UI interactions to AppServices methods ---
        # (This will be done as panels are refactored. For now, we remove old VM connections)

        if self.curve_canvas:
            self.curve_canvas.point_dragged.connect(self.on_curve_point_dragged)
            self.curve_canvas.curve_changed.connect(self.on_curve_modified)

        if self.curve_control_panel:
            self.curve_control_panel.transient_status_signal.connect(self.set_transient_status)

    def apply_styles(self):
        """Applies the application stylesheet from an external file."""
        style_sheet_path = os.path.join(os.path.dirname(__file__), "style.qss")
        try:
            with open(style_sheet_path, "r", encoding="utf-8") as f:
                self.setStyleSheet(f.read())
        except FileNotFoundError:
            print(f"Warning: Stylesheet file not found at '{style_sheet_path}'.", file=sys.stderr)
        except Exception as e:
            print(f"Warning: Could not load stylesheet. Error: {e}", file=sys.stderr)

    # --- Public Slots for AppRunner ---

    @Slot(object)
    def on_state_changed(self, state: AppState):
        """The single slot to receive all state updates from AppServices."""
        self.last_state = state

        if not self._is_window_visible:
            return

        # Delegate state updates to each panel
        if self.status_info_panel:
            self.status_info_panel.update_state(state)

        if self.fan_control_panel:
            self.fan_control_panel.update_state(state) # Fan panel needs more context

        if self.battery_control_panel:
            self.battery_control_panel.update_state(state) # So does battery panel

        if self.curve_control_panel:
            self.curve_control_panel.update_state(state)

        # Update components owned by MainWindow
        if self.curve_canvas:
            self.curve_canvas.update_temp_indicators(state.cpu_temp, state.gpu_temp)
            self.curve_canvas.set_active_curve(state.active_curve_type)
            # Update curves if they have changed
            # This logic will be refined when panels are refactored
            active_profile = state.profiles.get(state.active_profile_name)
            if active_profile:
                 self.curve_canvas.update_plot(active_profile.cpu_fan_table, active_profile.gpu_fan_table)


        is_dragging = self.curve_canvas and self.curve_canvas._dragging_point_index is not None
        if not is_dragging and not self._is_showing_transient_status:
            status_key = state.controller_status_message
            if self.title_bar:
                self.title_bar.status_label.setText(tr(status_key) if status_key else "")


    @Slot(str, str)
    def show_error_message(self, title: str, message: str):
        """Displays an error message box."""
        if self._is_quitting: return # Don't show errors during shutdown
        QMessageBox.warning(self, title, message)
        # Optionally update status bar if window is visible and not showing transient message
        if self._is_window_visible:
            # Display the error in the main status label as a transient message
            self.set_transient_status(title)


    def set_controls_enabled_state(self, enabled: bool):
        """This method will be removed. Panel enable state will be derived from AppState."""
        # This method is now a NO-OP. The logic will be moved into each panel's
        # update_state method, where it can react to the overall state.
        pass


    # apply_profile_to_ui is removed. Its logic is now part of on_state_changed.

    # Removed update_profile_button_name.
    # This is now handled by CurveControlViewModel emitting profile_renamed_locally,
    # which CurveControlPanel connects to _update_profile_button_text_property.

    # --- Internal Event Handlers and Slots ---
    # Most old event handlers (on_fan_mode_toggled, on_manual_fan_slider_changed, etc.)
    # are removed as their logic is now encapsulated within the respective panel components.
    # Panels will emit higher-level signals that MainWindow connects to (see connect_signals).

    @Slot(str)
    def set_transient_status(self, message: str, duration_ms: int = 2000):
        """Public slot to show a temporary status message."""
        if self._is_window_visible and self.title_bar:
            self.title_bar.status_label.setText(message)
        
        self._is_showing_transient_status = True

        # Cancel any existing timer to avoid race conditions
        if self._transient_status_timer and self._transient_status_timer.isActive():
            self._transient_status_timer.stop()

        # Set up a one-shot timer to clear the transient status
        if not self._transient_status_timer:
            self._transient_status_timer = QTimer(self)
            self._transient_status_timer.setSingleShot(True)
            self._transient_status_timer.timeout.connect(self._clear_transient_status)
        
        self._transient_status_timer.start(duration_ms)

    @Slot(str, int, float, float)
    def on_curve_point_dragged(self, curve_type: str, index: int, new_temp: float, new_speed: float):
        """Updates status bar while dragging a curve point (signal from CurveCanvas)."""
        self.set_transient_status(tr("curve_point_tooltip", temp=int(new_temp), speed=int(new_speed)))

    @Slot(str)
    def on_curve_modified(self, curve_type: str):
        """Calls AppServices when a curve is modified (signal from CurveCanvas)."""
        if self.curve_canvas:
            final_table = self.curve_canvas.get_curve_data(curve_type)
            self.app_services.set_curve_data(curve_type, final_table)
            self.set_transient_status(tr("saving_config"))

    # Removed _handle_profile_save_request_from_panel.
    # CurveControlViewModel now signals AppRunner directly with profile_name.
    # AppRunner's handle_profile_save slot will call self._get_current_settings_from_ui().

    # Removed eventFilter and its handlers (handle_profile_button_right_click, handle_profile_button_double_click)
    # as this logic is now encapsulated in CurveControlPanel.

    # Removed on_language_changed - SettingsPanel emits language_changed_signal directly.
    # Removed on_start_on_boot_toggled - CurveControlPanel emits start_on_boot_changed_signal directly.

    # Removed individual slider/radio button handlers like:
    # on_fan_mode_toggled, on_charge_policy_toggled,
    # on_manual_fan_slider_pressed, on_manual_fan_slider_released, on_manual_fan_slider_changed,
    # _emit_fan_speed_change, _unblock_fan_slider_update,
    # on_charge_threshold_slider_pressed, on_charge_threshold_slider_released, on_charge_threshold_slider_changed,
    # _emit_threshold_change, _unblock_threshold_slider_update,
    # on_curve_type_button_clicked, on_profile_button_left_clicked.
    # Their functionality is now within the panels, which emit consolidated signals.

    def _clear_transient_status(self):
        """Clears the transient status message and restores the permanent one."""
        self._is_showing_transient_status = False
        # Trigger a refresh of the status display to show the correct permanent status
        if self.last_state:
            self.on_state_changed(self.last_state)
        elif self.title_bar:
            # If there's no status, clear the label
            self.title_bar.status_label.setText("")

    # Removed get_current_settings_for_profile.
    # This is now handled entirely within AppServices.

    # Removed update_start_on_boot_checkbox.
    # This is now handled by AppRunner updating CurveControlViewModel,
    # which emits start_on_boot_status_updated,
    # and CurveControlPanel connects to _update_start_on_boot_display.

    def retranslate_ui(self):
        """Retranslates all user-visible text in the UI by delegating to panels."""
        self.setWindowTitle(tr("window_title"))
        if self.title_bar:
            self.title_bar.retranslate_ui()

        if self.status_info_panel:
            self.status_info_panel.retranslate_ui()

        if self.curve_control_panel:
            self.curve_control_panel.retranslate_ui()

        if self.fan_control_panel:
            self.fan_control_panel.retranslate_ui()

        if self.battery_control_panel:
            self.battery_control_panel.retranslate_ui()

        if self.curve_canvas:
            self.curve_canvas.retranslate_ui()

        # Tray Menu (remains in MainWindow as it owns the tray icon)
        if self.tray_icon and self.tray_icon.contextMenu():
            menu = self.tray_icon.contextMenu()
            actions = menu.actions()
            if len(actions) >= 2: # Show/Hide, (Separator), Quit
                # This assumes a fixed order or identifiable actions.
                # A more robust approach would be to find actions by objectName if they were set.
                try:
                    actions[0].setText(tr("tray_menu_show_hide")) # Assuming first is Show/Hide
                    actions[-1].setText(tr("tray_menu_quit"))     # Assuming last is Quit
                except IndexError:
                    print("Warning: Could not retranslate all tray menu items.", file=sys.stderr)
        
        # After all panels and canvas have retranslated their static text,
        # if we have a last known state, tell panels to re-render dynamic data.
        # The `on_state_changed` method already delegates to panels,
        # and those panel methods should use `tr()` for units etc.
        if self.last_state:
            self.on_state_changed(self.last_state)
        else:
            # If there's no state yet, panels should show their initial translated placeholder texts.
            # This should be handled by each panel's retranslate_ui or their init.
            # MainWindow might set an initial global status message via StatusInfoPanel.
            if self.title_bar:
                self.title_bar.status_label.setText(tr("initializing"))
            self._is_showing_transient_status = True

        # Old logic for updating individual value labels (e.g. self.cpu_temp_value.setText)
        # and slider value labels (e.g. self.on_manual_fan_slider_changed(...)) during retranslate
        # is now handled within each panel's retranslate_ui or by the update_status_display call.

    # --- Command Polling ---

    def _start_command_poller(self):
        """Initializes and starts a QTimer to poll for commands in shared memory."""
        from tools.single_instance import read_command_from_shared_memory, write_command_to_shared_memory
        from config.settings import COMMAND_NONE

        self.command_poll_timer = QTimer(self)
        self.command_poll_timer.setInterval(250) # Check every 250ms

        def _check_for_commands():
            command = read_command_from_shared_memory()
            if command is not None and command != COMMAND_NONE:
                # Reset the command immediately to prevent re-triggering
                write_command_to_shared_memory(COMMAND_NONE)
                # Handle the command
                self._handle_command(command)

        self.command_poll_timer.timeout.connect(_check_for_commands)
        self.command_poll_timer.start()
        print("Shared memory command poller started.")

    def _handle_command(self, command: int):
        """Handles commands read from shared memory."""
        from config.settings import (
            COMMAND_QUIT, COMMAND_RELOAD_AND_SHOW, COMMAND_RELOAD_ONLY
        )
        if command == COMMAND_QUIT:
            print("Received quit command from shared memory. Initiating shutdown.")
            self._request_quit()
        elif command == COMMAND_RELOAD_AND_SHOW:
            print("Received show command. Ensuring window visibility.")
            # With the new state-centric architecture, reloading config from disk is unsafe
            # as it would overwrite the in-memory state. The primary instance is the
            # single source of truth. We just need to show the window.
            if not self.isVisible() or self.isMinimized():
                self.toggle_window_visibility()
        elif command == COMMAND_RELOAD_ONLY:
            # This command is now deprecated as reloading from disk is unsafe.
            print("Received reload-only command (deprecated). Ignoring.")
        else:
            print(f"Warning: Received unknown command '{command}' from shared memory.")

    # --- Window Event Handlers ---

    def showEvent(self, event: QShowEvent):
        """Called when the window becomes visible."""
        # This event can fire multiple times. We only want to handle initialization once.
        if not self._is_initialized:
            self._is_initialized = True
            
            def emit_hwnd():
                """Safely gets and emits the window handle."""
                try:
                    hwnd = int(self.winId())
                    if hwnd != 0:
                        self.window_initialized_signal.emit(hwnd)
                except Exception as e:
                    print(f"Warning: Could not get valid HWND on initial show event: {e}", file=sys.stderr)
            
            # Defer the HWND emission to the next event loop cycle.
            # This ensures the window is fully initialized and its handle is stable
            # before we send it to be written to shared memory.
            QTimer.singleShot(0, emit_hwnd)

        if not self._is_window_visible:
            self._is_window_visible = True
            if self.last_state:
                self.on_state_changed(self.last_state)
            self.background_state_changed.emit(False)
        
        super().showEvent(event)


    def hideEvent(self, event: QHideEvent):
        """Called when the window is hidden (e.g., minimized to tray)."""
        if self._is_window_visible:
            self._is_window_visible = False
            if self.title_bar and self.title_bar.status_label.text() != tr("shutting_down"):
                self.set_transient_status(tr("paused"))
            self.background_state_changed.emit(True)
        super().hideEvent(event)


    def _toggle_maximize(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    if sys.platform == 'win32':
        def nativeEvent(self, event_type: Any, message: int) -> tuple[bool, int]:
            """ Handles Windows native events to enable resizing and dragging. """
            # The return type needs to be compatible with the base class, which is complex.
            # We return a tuple, but the base class might return something else.
            # For practical purposes, we handle our cases and pass the rest to super.
            result = (False, 0) # Default result

            if event_type == b"windows_generic_MSG":
                msg = MSG.from_address(message.__int__())

                # WM_NCHITTEST
                if msg.message == 0x0084:
                    if self.isMaximized():
                        return True, 1 # HTCLIENT

                    # Get cursor coordinates from message
                    x = msg.lParam & 0xFFFF
                    y = (msg.lParam >> 16) & 0xFFFF
                    
                    # Map to local window coordinates
                    local_pos = self.mapFromGlobal(QPoint(x, y))
                    
                    border_width = 8
                    title_bar_height = 40

                    on_left = local_pos.x() < border_width
                    on_right = local_pos.x() > self.width() - border_width
                    on_top = local_pos.y() < border_width
                    on_bottom = local_pos.y() > self.height() - border_width

                    # Corners
                    if on_top and on_left: return True, 13
                    if on_top and on_right: return True, 14
                    if on_bottom and on_left: return True, 16
                    if on_bottom and on_right: return True, 17

                    # Edges
                    if on_left: return True, 10
                    if on_right: return True, 11
                    if on_top: return True, 12
                    if on_bottom: return True, 15

                    # Title bar for dragging
                    if local_pos.y() < title_bar_height:
                        if self.title_bar:
                             # Check if cursor is over a button on the title bar
                            child_widget = self.title_bar.childAt(self.title_bar.mapFrom(self, local_pos))
                            if isinstance(child_widget, (QPushButton, QComboBox)):
                                return super().nativeEvent(event_type, message) # type: ignore
                        return True, 2 # HTCAPTION
            
            # If not handled, call super and return its result
            return super().nativeEvent(event_type, message) # type: ignore

    @Slot(QSystemTrayIcon.ActivationReason)
    def on_tray_icon_activated(self, reason: QSystemTrayIcon.ActivationReason):
        """Handles clicks on the system tray icon."""
        if reason == QSystemTrayIcon.ActivationReason.Trigger or \
           reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.toggle_window_visibility()


    def toggle_window_visibility(self):
        """Shows or hides the main window."""
        # This logic is now more robust. It correctly handles three states:
        # 1. Visible and normal: Hides the window.
        # 2. Hidden in tray (isVisible is False): Shows the window.
        # 3. Minimized to taskbar (isVisible is True, isMinimized is True): Shows the window.
        if self.isVisible() and not self.isMinimized():
            self.hide() # Hides to tray if tray icon exists (triggers hideEvent)
        else:
            self.showNormal() # Restores from minimized or hidden state (triggers showEvent)
            self.activateWindow() # Bring to front
            self.raise_()


    def _request_quit(self):
        """Emits the quit_requested signal when quit is chosen from tray."""
        self.quit_requested.emit()


    def closeEvent(self, event: QCloseEvent):
        """Handles the window close event (X button or Alt+F4)."""
        if self._is_quitting:
            # Quit already initiated (e.g., from tray menu), allow close
            # Emit geometry so AppRunner can save it before shutdown.
            try:
                geometry_hex = self.saveGeometry().toHex().toStdString()
                self.window_geometry_changed.emit(geometry_hex)
            except Exception as e:
                print(f"Warning: Failed to save window geometry on close: {e}", file=sys.stderr)
            event.accept()
        else:
            # Default close action: hide to tray if tray icon is available
            if self.tray_icon and self.tray_icon.isVisible():
                self.hide() # Triggers hideEvent, which signals background state
                event.ignore() # Prevent actual closing
            else:
                # No tray icon, treat close as quit request
                self._is_quitting = True # Mark as quitting
                self.quit_requested.emit() # Signal AppRunner to handle shutdown
                event.accept() # Allow window to close after signal handling

