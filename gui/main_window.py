# File: 9 gui/main_window.py (Modified Again)
# gui/main_window.py
# -*- coding: utf-8 -*-
"""
Main application window (QMainWindow) for the Fan & Battery Control GUI.
"""

import sys
import os
from typing import List, Optional, NamedTuple

from .qt import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFrame, QMessageBox,
    QSystemTrayIcon, QMenu, QStyle, Qt, QTimer, Signal, QLocale, QEvent,
    Slot, QByteArray, QIcon, QAction, QCloseEvent, QShowEvent, QHideEvent
)

from .curve_canvas import CurveCanvas
# --- MODIFICATION: Import new panel components ---
from .StatusInfoPanel import StatusInfoPanel
from .CurveControlPanel import CurveControlPanel
from .FanControlPanel import FanControlPanel
from .BatteryControlPanel import BatteryControlPanel
from .SettingsPanel import SettingsPanel
# --- END MODIFICATION ---

# --- ViewModel Imports ---
from viewmodels.fan_control_viewmodel import FanControlViewModel
from viewmodels.battery_control_viewmodel import BatteryControlViewModel
from viewmodels.curve_control_viewmodel import CurveControlViewModel
# --- END ViewModel Imports ---

from tools.config_manager import ConfigManager, ProfileSettings
from tools.localization import tr, get_available_languages, set_language, get_current_language # get_available_languages, get_current_language might be removed if SettingsPanel handles all
from tools.task_scheduler import create_startup_task, delete_startup_task, is_startup_task_registered
from config.settings import (
    APP_NAME, APP_ICON_NAME, DEFAULT_PROFILE_SETTINGS
)

# --- MODIFICATION: Forward declare AppRunner for type hint ---
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from run import AppRunner
# --- END MODIFICATION ---

class AppStatus(NamedTuple): # This might be passed TO ViewModels, or ViewModels might define their own data structures
    cpu_temp: float
    gpu_temp: float
    fan1_rpm: int
    fan2_rpm: int
    current_fan_mode: str # 'auto', 'fixed', 'unknown'
    applied_fan_percentage: int # Current speed %
    theoretical_target_percentage: int # Target % based on temp/curve (if auto)
    current_charge_policy: Optional[str] # 'standard', 'custom', None if unknown
    current_charge_threshold: int # Current limit %
    controller_status_message: str # e.g., "Ready", "WMI Error", "Initializing"


CurveType = str
FanTable = List[List[int]]

# --- NEW: Define update block duration ---
SLIDER_UPDATE_BLOCK_DURATION_MS = 1500 # Block updates for 1.5 seconds after user change
# --- END NEW ---

class MainWindow(QMainWindow):
    """Main application window."""

    # --- Signals to AppRunner ---
    quit_requested = Signal()
    # fan_mode_changed_signal, fixed_speed_changed_signal are removed (handled by FanControlViewModel -> AppRunner)
    # charge_policy_changed_signal, charge_threshold_changed_signal are removed (handled by BatteryControlViewModel -> AppRunner)
    curve_changed_signal = Signal(str, object) # curve_type (str), new_data (list/object) - From CurveCanvas
    # profile_activated_signal, profile_save_requested_signal, profile_rename_requested_signal, start_on_boot_changed_signal
    # are removed (handled by CurveControlViewModel -> AppRunner)
    language_changed_signal = Signal(str) # lang_code - From SettingsPanel
    # --- NEW: Signal for background state change ---
    background_state_changed = Signal(bool) # True if entering background, False if entering foreground
    # --- END NEW ---


    background_state_changed = Signal(bool) # True if entering background, False if entering foreground
    # --- END NEW ---


    # --- MODIFICATION: Added app_runner and ViewModel parameters ---
    def __init__(self,
                 app_runner: 'AppRunner',
                 config_manager: ConfigManager,
                 fan_control_vm: FanControlViewModel,
                 battery_control_vm: BatteryControlViewModel,
                 curve_control_vm: CurveControlViewModel,
                 start_minimized: bool = False):
        super().__init__()
        self.app_runner = app_runner # Store reference to AppRunner
        self.config_manager = config_manager
        self.start_minimized = start_minimized

        # --- ViewModel Instances (passed in) ---
        self.fan_control_vm = fan_control_vm
        self.battery_control_vm = battery_control_vm
        self.curve_control_vm = curve_control_vm
        # --- END ViewModel Instances ---

        # Internal state
        self.last_status: Optional[AppStatus] = None # Will be used to update panels
        self.tray_icon: Optional[QSystemTrayIcon] = None
        self._is_quitting: bool = False
        self._is_window_visible: bool = not start_minimized # Track visibility state
        self._current_gui_update_interval_ms: int = DEFAULT_PROFILE_SETTINGS['GUI_UPDATE_INTERVAL_MS']
        self._is_showing_transient_status: bool = False
        self.command_poll_timer: Optional[QTimer] = None

        # Panel members are declared below
        # Old UI element attributes (sliders, specific buttons, interaction flags, timers) are removed
        # as they are now encapsulated within their respective panel components.

        # --- NEW: Declare panel members ---
        self.status_info_panel: Optional[StatusInfoPanel] = None
        self.curve_control_panel: Optional[CurveControlPanel] = None
        self.fan_control_panel: Optional[FanControlPanel] = None
        self.battery_control_panel: Optional[BatteryControlPanel] = None
        self.settings_panel: Optional[SettingsPanel] = None
        # self.curve_canvas is initialized in init_ui as before
        # --- END NEW ---

        # Apply initial locale based on config (which should be loaded by AppRunner before this)
        self._apply_locale(get_current_language())

        # Initialize UI elements
        self.init_ui() # Creates widgets and connects signals internally
        self.init_tray_icon()
        self.apply_styles()

        # Restore geometry if available
        geometry_hex = self.config_manager.get("window_geometry")
        if geometry_hex:
            try:
                self.restoreGeometry(QByteArray.fromHex(bytes(geometry_hex, 'utf-8')))
            except (ValueError, TypeError):
                self.resize(1150, 700) # Default size on error
        else:
            self.resize(1150, 700) # Default size

        # Set initial status message (will be done by StatusInfoPanel, or MainWindow needs to tell it)
        # self.status_label.setText(tr("initializing")) # This self.status_label will be from StatusInfoPanel
        # self._is_showing_transient_status = True # Initializing is transient

        # Show window or tray icon based on start_minimized flag
        if self.start_minimized:
            if self.tray_icon: self.tray_icon.show()
            self.background_state_changed.emit(True)
        else:
            self.show()
            self.background_state_changed.emit(False)

        # Start the command poller
        self._start_command_poller()

    def _apply_locale(self, lang_code: str):
        """Sets the Qt application locale."""
        try:
            locale = QLocale(lang_code)
            QLocale.setDefault(locale)
        except Exception as e:
            print(f"Warning: Could not set application locale for '{lang_code}': {e}", file=sys.stderr)

    def init_ui(self):
        """Creates and lays out all UI widgets."""
        self.setWindowTitle(tr("window_title"))
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)

        # --- Status Info Panel ---
        self.status_info_panel = StatusInfoPanel(self)
        main_layout.addWidget(self.status_info_panel)
        # self.status_label is now part of self.status_info_panel

        # --- Curve Graph Area ---
        curve_area_layout = QVBoxLayout() # This layout will hold CurveControlPanel and CurveCanvas
        curve_area_layout.setSpacing(5)

        # Instantiate CurveControlPanel
        # It needs profile names, active profile name, and startup task status
        # profile_names = self.config_manager.get_profile_names() # ViewModel will get this from AppRunner/ConfigManager
        # active_profile_name = self.config_manager.get_active_profile_name() # ViewModel will get this
        # is_startup_reg = is_startup_task_registered() # ViewModel will get this
        self.curve_control_panel = CurveControlPanel(self.curve_control_vm, self)
        curve_area_layout.addWidget(self.curve_control_panel)

        # Curve Canvas (remains a direct member of MainWindow, placed under its controls)
        self.curve_canvas = CurveCanvas(self, width=7, height=4, dpi=100)
        curve_area_layout.addWidget(self.curve_canvas)
        
        main_layout.addLayout(curve_area_layout)
        main_layout.setStretchFactor(curve_area_layout, 1) # Allow canvas area to expand vertically

        # --- Control Panels (Fan, Battery, Settings) ---
        # Use a QFrame to group these, similar to the old 'controlFrame'
        bottom_controls_frame = QFrame()
        bottom_controls_frame.setObjectName("controlFrame") # Keep old name for styling if needed
        bottom_controls_frame.setFrameShape(QFrame.Shape.StyledPanel)
        bottom_controls_layout = QHBoxLayout(bottom_controls_frame)
        bottom_controls_layout.setContentsMargins(10, 10, 10, 10)
        bottom_controls_layout.setSpacing(20)

        # Left side for Fan and Battery controls
        left_fan_battery_layout = QVBoxLayout()
        left_fan_battery_layout.setSpacing(10)

        # Instantiate FanControlPanel - now takes ViewModel
        # initial_fan_mode = self.config_manager.get_active_profile_setting("fan_mode", DEFAULT_PROFILE_SETTINGS["fan_mode"]) # ViewModel handles initial state
        # initial_fixed_speed = self.config_manager.get_active_profile_setting("fixed_fan_speed", DEFAULT_PROFILE_SETTINGS["fixed_fan_speed"]) # ViewModel handles initial state
        self.fan_control_panel = FanControlPanel(self.fan_control_vm, self)
        left_fan_battery_layout.addWidget(self.fan_control_panel)

        # Instantiate BatteryControlPanel - now takes ViewModel
        # initial_charge_policy = self.config_manager.get_active_profile_setting("charge_policy", DEFAULT_PROFILE_SETTINGS["charge_policy"]) # ViewModel handles initial state
        # initial_charge_threshold = self.config_manager.get_active_profile_setting("charge_threshold", DEFAULT_PROFILE_SETTINGS["charge_threshold"]) # ViewModel handles initial state
        self.battery_control_panel = BatteryControlPanel(self.battery_control_vm, self)
        left_fan_battery_layout.addWidget(self.battery_control_panel)
        
        bottom_controls_layout.addLayout(left_fan_battery_layout, 1) # Left side takes expanding space

        # Right side for Settings Panel (e.g., Language)
        self.settings_panel = SettingsPanel(self)
        # Wrap settings_panel in a QVBoxLayout to control its vertical alignment if needed, or add directly
        right_settings_wrapper_layout = QVBoxLayout()
        right_settings_wrapper_layout.addWidget(self.settings_panel)
        right_settings_wrapper_layout.addStretch(1) # Push settings panel to the top of its allocated space
        bottom_controls_layout.addLayout(right_settings_wrapper_layout)


        main_layout.addWidget(bottom_controls_frame)

        # Connect signals AFTER all widgets are created (will be refactored in next step)
        self.connect_signals()

        # Apply initial state from config (will be refined by first status update)
        # This will now involve calling methods on the new panels
        self.apply_profile_to_ui(self.config_manager.get_active_profile())
        # self.update_control_enable_states() # This will also be refactored to use panels

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
        external_icon_path = os.path.join(self.config_manager.base_dir, APP_ICON_NAME)
        external_icon = QIcon(external_icon_path)

        if not external_icon.isNull():
            # External icon loaded successfully, apply it everywhere.
            print(f"Successfully loaded external icon from: {external_icon_path}")
            self.setWindowIcon(external_icon)
            self.tray_icon.setIcon(external_icon)
        else:
            # --- Step 2: Fallback to the window's default icon (provided by OS from .exe) ---
            # If the external icon fails, we don't try to load anything else.
            # We assume the OS has already set the window's icon from the embedded resource.
            # We just grab that icon and apply it to the tray.
            print("External icon not found or invalid. Falling back to window's default icon (from .exe).")
            window_icon = self.windowIcon() # Get the icon set by the OS
            if not window_icon.isNull():
                self.tray_icon.setIcon(window_icon)
            else:
                # --- Step 3: Ultimate fallback to a generic system icon ---
                # This happens if the .exe has no embedded icon AND external icon is missing.
                print("Warning: No valid embedded or external icon found. Using generic system icon.")
                self._use_default_icon()

        self.tray_icon.setToolTip(APP_NAME)

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

    def connect_signals(self):
        """Connects signals from UI components to MainWindow's handlers or re-emits them."""
        # Signals from FanControlPanel and BatteryControlPanel are now handled by their ViewModels
        # which call AppRunner directly. Transient status signals can remain if panels define them.
        if self.fan_control_panel and hasattr(self.fan_control_panel, 'transient_status_signal'):
            self.fan_control_panel.transient_status_signal.connect(self._set_transient_status)

        if self.battery_control_panel and hasattr(self.battery_control_panel, 'transient_status_signal'):
            self.battery_control_panel.transient_status_signal.connect(self._set_transient_status)

        # Signals from CurveControlPanel
        if self.curve_control_panel:
            # Curve type selection still directly affects CurveCanvas managed by MainWindow
            if self.curve_canvas and hasattr(self.curve_control_panel.view_model, 'active_curve_type_updated'): # Check VM signal
                 self.curve_control_panel.view_model.active_curve_type_updated.connect(self.curve_canvas.set_active_curve)
            
            # Reset curve request from panel now goes through its ViewModel to AppRunner
            # self.curve_control_panel.reset_curve_signal.connect(self.on_reset_curve_requested_from_panel) # Old connection
            # New: on_reset_curve_requested_from_panel will be triggered differently if kept, or logic moved to AppRunner.
            # For now, assuming CurveControlPanel's reset button calls a VM method, which signals AppRunner.
            # MainWindow's on_reset_curve_requested_from_panel might be triggered by AppRunner if confirmation is needed here.

            # Profile activation, save, rename, start_on_boot are handled by CurveControlViewModel -> AppRunner.
            # Transient status signal can remain if panel defines it.
            if hasattr(self.curve_control_panel, 'transient_status_signal'):
                self.curve_control_panel.transient_status_signal.connect(self._set_transient_status)


        # Signals from SettingsPanel
        if self.settings_panel:
            self.settings_panel.language_changed_signal.connect(self.language_changed_signal) # Re-emit to AppRunner
            if hasattr(self.settings_panel, 'transient_status_signal'):
                 self.settings_panel.transient_status_signal.connect(self._set_transient_status)

        # Signals from CurveCanvas (still directly managed by MainWindow for data changes)
        if self.curve_canvas:
            self.curve_canvas.point_dragged.connect(self.on_curve_point_dragged) # For transient status
            self.curve_canvas.curve_changed.connect(self.on_curve_modified)     # For data persistence to AppRunner

    def apply_styles(self):
        """Applies the application stylesheet."""
        # Stylesheet (same as original, slightly formatted)
        dark_stylesheet = """
            QMainWindow { background-color: #2E3135; }
            QWidget { color: #E0E0E0; font-family: 'Segoe UI', Arial, sans-serif; font-size: 10pt; }
            QFrame#infoFrame, QFrame#controlFrame {
                background-color: #33373B; border-radius: 5px; border: 1px solid #45494D;
            }
            QLabel { color: #C0C0C0; padding-top: 2px; }
            QLabel#cpu_temp_value, QLabel#gpu_temp_value, QLabel#fan1_rpm_value,
            QLabel#fan2_rpm_value, QLabel#applied_target_value, QLabel#battery_info_value,
            QLabel#manual_speed_value_label, QLabel#charge_threshold_value_label {
                color: #FFFFFF; font-weight: bold;
            }
            QLabel#status_label { color: #FFA500; font-style: italic; } /* Orange for status */
            QPushButton {
                background-color: #4A5055; color: #E0E0E0; border: 1px solid #5A6065;
                padding: 5px 10px; border-radius: 3px; min-height: 20px;
            }
            QPushButton:hover { background-color: #5A6065; border: 1px solid #6A7075; }
            QPushButton:pressed { background-color: #3A4045; }
            QPushButton:checked { /* General checked state */
                background-color: #0078D7; border: 1px solid #005A9E; color: #FFFFFF;
            }
            QPushButton[objectName^="profileButton_"]:checked { /* Specific style for active profile */
                background-color: #1E90FF; border: 1px solid #4682B4; font-weight: bold;
            }
            QPushButton#resetCurveButton {
                background-color: #8B0000; color: #FFFFFF; border: 1px solid #A52A2A; /* Dark Red */
            }
            QPushButton#resetCurveButton:hover { background-color: #A52A2A; border: 1px solid #CD5C5C; }
            QPushButton#resetCurveButton:pressed { background-color: #500000; }
            QRadioButton, QCheckBox { spacing: 5px; margin-right: 10px; }
            QRadioButton::indicator, QCheckBox::indicator { width: 13px; height: 13px; }
            QRadioButton::indicator::unchecked, QCheckBox::indicator::unchecked {
                border: 1px solid #6A7075; background-color: #33373B; border-radius: 6px;
            }
            QRadioButton::indicator::checked, QCheckBox::indicator::checked {
                border: 1px solid #0078D7; background-color: #0078D7; border-radius: 6px;
            }
            QRadioButton::indicator::checked:hover, QCheckBox::indicator::checked:hover {
                background-color: #1085E0; border: 1px solid #1085E0;
            }
            QRadioButton::indicator::unchecked:hover, QCheckBox::indicator::unchecked:hover {
                border: 1px solid #7A8085;
            }
            QCheckBox::indicator { border-radius: 3px; } /* Square checkbox */
            QSlider::groove:horizontal {
                border: 1px solid #45494D; height: 4px; background: #45494D;
                margin: 2px 0; border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #0078D7; border: 1px solid #005A9E; width: 16px;
                margin: -6px 0; border-radius: 8px; /* Negative margin to overlap groove */
            }
            QSlider::handle:horizontal:hover { background: #1085E0; border: 1px solid #1085E0; }
            QSlider::handle:horizontal:disabled { background: #5A6065; border: 1px solid #45494D; }
            QSlider::sub-page:horizontal { /* Part filled */
                background: #0078D7; border: 1px solid #45494D; height: 4px;
                margin: 2px 0; border-radius: 2px;
            }
            QSlider::add-page:horizontal { /* Part empty */
                background: #45494D; border: 1px solid #45494D; height: 4px;
                margin: 2px 0; border-radius: 2px;
            }
            QComboBox {
                border: 1px solid #5A6065; border-radius: 3px; padding: 3px 18px 3px 5px;
                min-width: 6em; background-color: #4A5055;
            }
            QComboBox:hover { border: 1px solid #6A7075; }
            QComboBox::drop-down {
                subcontrol-origin: padding; subcontrol-position: top right; width: 15px;
                border-left-width: 1px; border-left-color: #5A6065; border-left-style: solid;
                border-top-right-radius: 3px; border-bottom-right-radius: 3px;
            }
            QComboBox::down-arrow { image: url(:/qt-project.org/styles/commonstyle/images/downarraow-16.png); } /* Standard Qt arrow */
            QComboBox::down-arrow:on { top: 1px; left: 1px; } /* Small shift when dropdown open */
            QComboBox QAbstractItemView { /* Dropdown list */
                border: 1px solid #6A7075; background-color: #33373B;
                selection-background-color: #0078D7; color: #E0E0E0;
            }
            QToolTip {
                color: #FFFFFF; background-color: #2A2D30; border: 1px solid #3A4045;
                border-radius: 3px; opacity: 230; /* Slightly transparent */
            }
            QMenu { background-color: #33373B; border: 1px solid #45494D; color: #E0E0E0; }
            QMenu::item:selected { background-color: #0078D7; color: #FFFFFF; }
            QMenu::separator { height: 1px; background-color: #45494D; margin: 5px 5px 5px 5px; }
        """
        self.setStyleSheet(dark_stylesheet)

    # --- Public Slots for AppRunner ---

    @Slot(object) # Accepts AppStatus named tuple
    def update_status_display(self, status: AppStatus):
        """Updates all status labels and relevant controls based on AppStatus."""
        self.last_status = status # Store for later use (e.g., redraw on show)

        if not self._is_window_visible:
            return

        # --- MODIFICATION: Delegate updates to panels ---
        if self.status_info_panel:
            # Pass relevant parts of AppStatus or the whole thing if StatusInfoPanel can handle it
            status_info_data = {
                'cpu_temp': status.cpu_temp, 'gpu_temp': status.gpu_temp,
                'fan1_rpm': status.fan1_rpm, 'fan2_rpm': status.fan2_rpm,
                'applied_fan_percentage': status.applied_fan_percentage,
                'theoretical_target_percentage': status.theoretical_target_percentage,
                'current_fan_mode': status.current_fan_mode,
                'current_charge_policy': status.current_charge_policy,
                'current_charge_threshold': status.current_charge_threshold,
                'controller_status_message': status.controller_status_message
            }
            self.status_info_panel.update_status(status_info_data)

        # FanControlPanel and BatteryControlPanel are now updated via their ViewModels.
        # AppRunner directly calls ViewModel's update_X_from_status methods.
        # ViewModels then emit signals that their respective Panels are connected to.
        # So, MainWindow no longer needs to directly call set_X methods on these panels here.

        # Example (old code that is being removed):
        # if self.fan_control_panel:
        #     self.fan_control_panel.set_fan_mode(status.current_fan_mode)
        #     self.fan_control_panel.set_fixed_speed(
        #         status.applied_fan_percentage if status.current_fan_mode == "fixed" else self.fan_control_panel.manual_fan_speed_slider.value(),
        #         status.applied_fan_percentage
        #     )
        # if self.battery_control_panel:
        #     self.battery_control_panel.set_charge_policy(status.current_charge_policy or "standard")
        #     self.battery_control_panel.set_charge_threshold(
        #         status.current_charge_threshold if status.current_charge_policy == "custom" else self.battery_control_panel.charge_threshold_slider.value(),
        #         status.current_charge_threshold
        #     )
        # --- END MODIFICATION ---

        # Update Curve Indicators (still relevant for MainWindow to manage)
        if self.curve_canvas:
            self.curve_canvas.update_temp_indicators(status.cpu_temp, status.gpu_temp)

        # Update main status label (only if not showing a transient message)
        # This logic might move to StatusInfoPanel or be controlled by a ViewModel
        is_dragging = self.curve_canvas and self.curve_canvas._dragging_point_index is not None
        if not is_dragging and not self._is_showing_transient_status and self.status_info_panel:
             # Assuming StatusInfoPanel has a way to show the main controller_status_message
             # For now, this part of status_info_panel.update_status handles it.
             pass


    # --- REMOVED DEPRECATED METHODS ---
    # _update_controls_from_status and update_control_enable_states are removed.
    # Their logic is now handled by panels internally or by update_status_display delegating to panels.


    @Slot(str, str)
    def show_error_message(self, title: str, message: str):
        """Displays an error message box."""
        if self._is_quitting: return # Don't show errors during shutdown
        QMessageBox.warning(self, title, message)
        # Optionally update status bar if window is visible and not showing transient message
        if self._is_window_visible and self.status_info_panel:
            current_main_status = self.status_info_panel.get_main_status_message()
            if current_main_status not in [tr("initializing"), tr("shutting_down"), tr("paused"), tr("wmi_error")]: # Avoid re-setting wmi_error if already set
                # Avoid overwriting specific error messages already set by update_status_display
                if current_main_status == tr("ready"): # Only set wmi_error if status was 'ready'
                    self._set_transient_status(tr("wmi_error")) # Generic error indication


    @Slot(bool)
    def set_controls_enabled_state(self, enabled: bool):
        """Globally enables or disables interactive controls by delegating to panels."""
        if self.status_info_panel:
            # StatusInfoPanel is mostly display, but might have interactive elements later
            self.status_info_panel.set_panel_enabled(enabled) # Assumes StatusInfoPanel has this method

        if self.curve_control_panel:
            self.curve_control_panel.set_panel_enabled(enabled) # Assumes CurveControlPanel has this method

        if self.fan_control_panel:
            self.fan_control_panel.set_panel_enabled(enabled) # Assumes FanControlPanel has this method

        if self.battery_control_panel:
            self.battery_control_panel.set_panel_enabled(enabled) # Assumes BatteryControlPanel has this method

        if self.settings_panel:
            self.settings_panel.set_panel_enabled(enabled) # Assumes SettingsPanel has this method

        if self.curve_canvas:
            self.curve_canvas.setEnabled(enabled) # Canvas has a direct setEnabled

        # If 'enabled' is True, panels will internally decide which of their sub-controls
        # should be active based on their current mode/policy (e.g. manual fan slider
        # only enabled if fan mode is 'fixed' AND global 'enabled' is True).
        # If 'enabled' is False, panels should disable all their interactive elements.
        # The old self.update_control_enable_states() is removed as panels handle this internally.


    @Slot(object) # Accepts ProfileSettings dictionary (passed as object)
    def apply_profile_to_ui(self, profile_settings_obj: Optional[object]):
        """Updates the UI elements to reflect the given profile settings by delegating to panels."""
        profile_settings = profile_settings_obj if isinstance(profile_settings_obj, dict) else None

        if profile_settings is None:
            profile_settings = DEFAULT_PROFILE_SETTINGS.copy()

        # Fan Settings: FanControlPanel is updated via its ViewModel signals
        # when AppRunner calls FanControlViewModel.apply_profile_settings.
        # No direct call from MainWindow to FanControlPanel.apply_profile_settings is needed.

        # Battery Settings: BatteryControlPanel is updated via its ViewModel signals
        # when AppRunner calls BatteryControlViewModel.apply_profile_settings.
        # No direct call from MainWindow to BatteryControlPanel.apply_profile_settings is needed.

        # Curve Settings & Appearance (Canvas and related controls in CurveControlPanel)
        if self.curve_canvas:
            self.curve_canvas.blockSignals(True) # MainWindow manages canvas signal blocking for this
            cpu_curve: FanTable = profile_settings.get("cpu_fan_table", DEFAULT_PROFILE_SETTINGS["cpu_fan_table"])
            gpu_curve: FanTable = profile_settings.get("gpu_fan_table", DEFAULT_PROFILE_SETTINGS["gpu_fan_table"])
            self.curve_canvas.apply_appearance_settings(profile_settings)
            self.curve_canvas.update_plot(cpu_curve, gpu_curve)
            self.curve_canvas.blockSignals(False)

        if self.curve_control_panel:
            # Active profile button indication in CurveControlPanel is updated
            # via CurveControlViewModel.active_profile_updated signal,
            # which AppRunner should trigger by updating the ViewModel.
            # Start on boot is a global setting, updated by AppRunner via CurveControlViewModel.
            pass

        # Settings Panel (e.g. Language) - Language is global, not typically per-profile.
        # If SettingsPanel had per-profile settings, it would also need an apply_profile_settings call.

        # Update GUI update interval if changed (MainWindow still manages this for now)
        new_interval = profile_settings.get("GUI_UPDATE_INTERVAL_MS", DEFAULT_PROFILE_SETTINGS['GUI_UPDATE_INTERVAL_MS'])
        if self._current_gui_update_interval_ms != new_interval:
            self._current_gui_update_interval_ms = new_interval
            # TODO: Consider if a signal should be emitted to AppRunner if it dynamically adjusts its loop.
            # self.gui_update_interval_changed_signal.emit(new_interval)

        # The old self.update_control_enable_states() call is removed.
        # Panels manage their own enable states based on the applied settings.
        # Global enable/disable (e.g., WMI error) is handled by set_controls_enabled_state.

    # Removed update_profile_button_name.
    # This is now handled by CurveControlViewModel emitting profile_renamed_locally,
    # which CurveControlPanel connects to _update_profile_button_text_property.

    # --- Internal Event Handlers and Slots ---
    # Most old event handlers (on_fan_mode_toggled, on_manual_fan_slider_changed, etc.)
    # are removed as their logic is now encapsulated within the respective panel components.
    # Panels will emit higher-level signals that MainWindow connects to (see connect_signals).

    def _set_transient_status(self, message: str):
        """Sets a transient status message via StatusInfoPanel."""
        if self._is_window_visible and self.status_info_panel:
            self.status_info_panel.set_main_status_message(message) # is_transient is handled by usage context
        self._is_showing_transient_status = True # Still used by update_status_display logic

    @Slot(str) # curve_type from CurveControlPanel's reset_curve_signal
    def on_reset_curve_requested_from_panel(self, active_curve_type: str):
        """Handles reset curve request from CurveControlPanel."""
        curve_name = active_curve_type.upper()
        reply = QMessageBox.question(self, tr("reset_curve_confirm_title"),
                                     tr("reset_curve_confirm_msg", curve_type=curve_name),
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            # Instead of emitting curve_changed_signal, tell the ViewModel to signal AppRunner
            if self.curve_control_vm: # Check if VM exists
                self.curve_control_vm.request_reset_active_curve() # VM will emit signal to AppRunner
            self._set_transient_status(tr("applying_settings"))

    @Slot(str, int, float, float) # curve_type, index, new_temp, new_speed
    def on_curve_point_dragged(self, curve_type: str, index: int, new_temp: float, new_speed: float):
        """Updates status bar while dragging a curve point (signal from CurveCanvas)."""
        self._set_transient_status(tr("curve_point_tooltip", temp=int(new_temp), speed=int(new_speed)))

    @Slot(str) # curve_type
    def on_curve_modified(self, curve_type: str):
        """Emits signal when a curve is modified (signal from CurveCanvas)."""
        if self.curve_canvas:
            final_table = self.curve_canvas.get_curve_data(curve_type)
            self.curve_changed_signal.emit(curve_type, final_table)
            self._set_transient_status(tr("saving_config")) # Or "applying_settings"

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

    def _get_current_settings_from_ui(self) -> ProfileSettings:
        """Reads current UI state by querying panels and returns it as a ProfileSettings dictionary."""
        # Start with a copy of the currently active profile's settings from config_manager
        # This ensures non-UI-managed settings (like appearance, update interval) are preserved.
        current_profile_name = self.config_manager.get_active_profile_name()
        settings = self.config_manager.get_profile_settings(current_profile_name)

        if settings is None: # Should ideally not happen if a profile is always active
            settings = DEFAULT_PROFILE_SETTINGS.copy()
        else:
            settings = settings.copy() # Work on a copy

        # Get settings from ViewModels
        if self.fan_control_vm:
            fan_settings = self.fan_control_vm.get_current_settings_for_profile()
            if fan_settings: settings.update(fan_settings)

        if self.battery_control_vm:
            battery_settings = self.battery_control_vm.get_current_settings_for_profile()
            if battery_settings: settings.update(battery_settings)
        
        if self.curve_control_vm:
            # CurveControlViewModel might provide some settings, but curve data is separate
            curve_vm_settings = self.curve_control_vm.get_current_settings_for_profile()
            if curve_vm_settings: settings.update(curve_vm_settings)

        # Get curve data from CurveCanvas
        if self.curve_canvas:
            settings["cpu_fan_table"] = self.curve_canvas.get_curve_data('cpu')
            settings["gpu_fan_table"] = self.curve_canvas.get_curve_data('gpu')
            # Curve appearance settings are part of the profile but not directly settable via UI elements
            # other than loading a profile that contains them. They are preserved by starting with current profile.

        # GUI_UPDATE_INTERVAL_MS is still managed by MainWindow or AppRunner, read from existing settings.
        # It's already in 'settings' if loaded from config_manager, or defaults.
        # If MainWindow directly modifies it and it needs to be saved, ensure it's in 'settings'.
        settings["GUI_UPDATE_INTERVAL_MS"] = self._current_gui_update_interval_ms

        return settings

    # Removed update_start_on_boot_checkbox.
    # This is now handled by AppRunner updating CurveControlViewModel,
    # which emits start_on_boot_status_updated,
    # and CurveControlPanel connects to _update_start_on_boot_display.

    def retranslate_ui(self):
        """Retranslates all user-visible text in the UI by delegating to panels."""
        self.setWindowTitle(tr("window_title"))

        if self.status_info_panel:
            self.status_info_panel.retranslate_ui() # Assumes StatusInfoPanel has retranslate_ui

        if self.curve_control_panel:
            self.curve_control_panel.retranslate_ui() # Assumes CurveControlPanel has retranslate_ui

        if self.fan_control_panel:
            self.fan_control_panel.retranslate_ui() # Assumes FanControlPanel has retranslate_ui

        if self.battery_control_panel:
            self.battery_control_panel.retranslate_ui() # Assumes BatteryControlPanel has retranslate_ui

        if self.settings_panel:
            self.settings_panel.retranslate_ui() # Assumes SettingsPanel has retranslate_ui (handles language combo)

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
        # if we have a last known status, tell panels to re-render dynamic data.
        # The `update_status_display` method already delegates to panels,
        # and those panel methods should use `tr()` for units etc.
        if self.last_status:
            self.update_status_display(self.last_status)
        else:
            # If there's no status yet, panels should show their initial translated placeholder texts.
            # This should be handled by each panel's retranslate_ui or their init.
            # MainWindow might set an initial global status message via StatusInfoPanel.
            if self.status_info_panel:
                 self.status_info_panel.set_main_status_message(tr("initializing"), is_transient=True)
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
        from config.settings import COMMAND_QUIT, COMMAND_SHOW
        if command == COMMAND_QUIT:
            print("Received quit command from shared memory. Initiating shutdown.")
            self._request_quit()
        elif command == COMMAND_SHOW:
            print("Received show command from shared memory. Activating window.")
            self.toggle_window_visibility()
        else:
            print(f"Warning: Received unknown command '{command}' from shared memory.")

    # --- Window Event Handlers ---

    def showEvent(self, event: QShowEvent):
        """Called when the window becomes visible."""
        if not self._is_window_visible:
            self._is_window_visible = True
            # Refresh display with last known status if available
            if self.last_status:
                self.update_status_display(self.last_status)
            # --- NEW: Signal AppRunner we are entering foreground ---
            self.background_state_changed.emit(False)
            # --- END NEW ---
        super().showEvent(event)


    def hideEvent(self, event: QHideEvent):
        """Called when the window is hidden (e.g., minimized to tray)."""
        if self._is_window_visible:
            self._is_window_visible = False
            if self.status_info_panel and self.status_info_panel.get_main_status_message() != tr("shutting_down"):
                self._set_transient_status(tr("paused"))
            # --- NEW: Signal AppRunner we are entering background ---
            self.background_state_changed.emit(True)
            # --- END NEW ---
        super().hideEvent(event)


    def changeEvent(self, event: QEvent):
        """Handles window state changes (minimize/restore)."""
        if event.type() == QEvent.Type.WindowStateChange:
            if self.windowState() & Qt.WindowState.WindowMinimized:
                # Standard minimize (not hide to tray)
                if self._is_window_visible:
                    self._is_window_visible = False
                    if self.status_info_panel and self.status_info_panel.get_main_status_message() != tr("shutting_down"):
                        self._set_transient_status(tr("paused"))
                    # --- NEW: Signal AppRunner we are entering background ---
                    self.background_state_changed.emit(True)
                    # --- END NEW ---
            elif not (self.windowState() & Qt.WindowState.WindowMinimized) and self.isVisible():
                 # Restored from minimized state
                 if not self._is_window_visible:
                    self._is_window_visible = True
                    if self.last_status: self.update_status_display(self.last_status)
                    # --- NEW: Signal AppRunner we are entering foreground ---
                    self.background_state_changed.emit(False)
                    # --- END NEW ---
        super().changeEvent(event)


    @Slot(QSystemTrayIcon.ActivationReason)
    def on_tray_icon_activated(self, reason: QSystemTrayIcon.ActivationReason):
        """Handles clicks on the system tray icon."""
        if reason == QSystemTrayIcon.ActivationReason.Trigger or \
           reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.toggle_window_visibility()


    def toggle_window_visibility(self):
        """Shows or hides the main window."""
        if self.isVisible() and self.isActiveWindow():
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
            # Save geometry just before closing
            try:
                geometry_hex = self.saveGeometry().toHex().data().decode('utf-8')
                self.config_manager.set("window_geometry", geometry_hex)
                # Config saving is handled by AppRunner during shutdown sequence
            except Exception as e:
                print(f"Warning: Failed to save window geometry: {e}", file=sys.stderr)
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

