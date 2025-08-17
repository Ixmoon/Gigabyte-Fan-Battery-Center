# main.py
# -*- coding: utf-8 -*-
"""
Application Entry Point for Fan & Battery Control.

Handles initialization, single instance check, admin rights check,
creates the main application runner, and starts the Qt event loop.
"""

import sys
import os
import json
import traceback
import atexit
import ctypes # For admin check message box fallback
from typing import Optional, Dict, Any

# --- Early Setup: Define Base Directory (Robust Method) ---
# This logic correctly handles script, standalone, and onefile modes.
try:
    if getattr(sys, 'frozen', False):
        # Packaged mode (Nuitka/PyInstaller)
        # sys.argv[0] is the reliable path to the original executable
        BASE_DIR = os.path.dirname(os.path.abspath(sys.argv[0]))
    else:
        # Script mode
        # __file__ is the path to the current script
        BASE_DIR = os.path.dirname(os.path.abspath(__file__))
except Exception:
    # Fallback for environments where __file__ or sys.argv[0] might be missing
    BASE_DIR = os.getcwd()

# --- Change Working Directory ---
# This is CRITICAL for onefile mode to find external config/language files.
try:
    os.chdir(BASE_DIR)
except Exception as e:
    print(f"Fatal: Could not change working directory to '{BASE_DIR}'. External files will not be found. Error: {e}", file=sys.stderr)

# --- Import Project Modules ---
from gui.qt import QApplication, QMessageBox, QCoreApplication, QTimer, QMetaObject, Qt, QObject, Slot

from config.settings import (
    APP_NAME, APP_ORGANIZATION_NAME, APP_INTERNAL_NAME, STARTUP_ARG_MINIMIZED,
    LANGUAGES_JSON_NAME, CONFIG_FILE_NAME
)
from tools.localization import load_translations, tr, DEFAULT_ENGLISH_TRANSLATIONS, DEFAULT_LANGUAGE, set_language, \
    _translations_loaded # Use internal flag name
from tools.system_utils import is_admin, run_as_admin
# --- MODIFICATION: Import new functions ---
from tools.single_instance import (
    check_single_instance, release_mutex, is_primary, write_hwnd_to_shared_memory,
    IsWindow # Import IsWindow directly if needed for validation in main
)
# --- END MODIFICATION ---
# from run import AppRunner # AppRunner now creates MainWindow
from core.app_services import AppServices
from gui.main_window import MainWindow

# --- Global Variables ---
app_services_instance: Optional[AppServices] = None
app_runner_instance: Optional['AppRunner'] = None
app_instance: Optional[QApplication] = None

# --- Matplotlib Font Setup (Now removed as it's a dependency we got rid of) ---
# This section is intentionally left blank.

# ==============================================================================
# Configuration Management
# ==============================================================================

def load_config(path: str) -> Dict[str, Any]:
    """Loads the configuration file from the given path."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Warning: Could not load config file '{path}'. Using default values. Error: {e}", file=sys.stderr)
        return {} # Return empty dict to use defaults

def save_config(path: str, data: Dict[str, Any]):
    """Saves the configuration data to the given path."""
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
        print(f"Configuration saved to '{path}'")
    except Exception as e:
        print(f"Error: Could not save config file to '{path}'. Error: {e}", file=sys.stderr)

# ==============================================================================
# AppRunner Class
# ==============================================================================

class AppRunner(QObject):
    """
    Orchestrates the UI layer (MainWindow) and connects it to the backend
    services provided by AppServices. It also manages config saving.
    """

    def __init__(self, app_services: AppServices, start_minimized: bool):
        super().__init__()
        self.app_services = app_services
        self.start_minimized = start_minimized
        self._is_shutting_down = False
        self._is_in_background = start_minimized
        self.config_path = os.path.join(BASE_DIR, CONFIG_FILE_NAME)

        # --- Instantiate GUI (now passing AppServices directly) ---
        self.main_window = MainWindow(
            app_runner=self,
            app_services=self.app_services,
            start_minimized=self.start_minimized
        )

        # --- Connect Signals ---
        self._connect_signals()

        # --- Initial UI State Sync ---
        self.load_window_geometry()

    def _connect_signals(self):
        """Connect signals between AppServices and MainWindow."""
        # --- AppServices to AppRunner ---
        self.app_services.config_save_requested.connect(self._save_config_on_request)

        # --- MainWindow to AppRunner ---
        self.main_window.quit_requested.connect(self.shutdown)
        self.main_window.language_changed_signal.connect(self.handle_language_change)
        self.main_window.background_state_changed.connect(self.set_background_state)
        self.main_window.window_geometry_changed.connect(self.save_window_geometry)
        self.main_window.window_initialized_signal.connect(self._handle_window_initialized)

    @Slot(dict)
    def _save_config_on_request(self, config_data: Dict[str, Any]):
        """Saves the configuration when requested by AppServices."""
        save_config(self.config_path, config_data)

    @Slot(int)
    def _handle_window_initialized(self, hwnd: int):
        """Handles writing the main window HWND to shared memory for single instance control."""
        if os.name == 'nt' and is_primary():
            if IsWindow(hwnd):
                print(f"Main window HWND obtained via signal: {hwnd}")
                write_hwnd_to_shared_memory(hwnd)
            else:
                print(f"Warning: Received invalid HWND ({hwnd}) from main window.", file=sys.stderr)

    def save_window_geometry(self, geometry_hex: str):
        """Saves the window geometry to the config."""
        # Convert hex string to bytes for saving in state
        self.app_services.set_window_geometry(geometry_hex.encode('utf-8'))

    def load_window_geometry(self):
        """Loads and applies window geometry from the config."""
        geometry_bytes = self.app_services.state.window_geometry
        if geometry_bytes:
            # Decode bytes back to hex string for the UI method
            self.main_window.restore_geometry_from_hex(geometry_bytes.decode('utf-8'))

    @Slot(str)
    def handle_language_change(self, lang_code: str):
        """Handles language change, saves it, and retranstales the UI."""
        set_language(lang_code)
        self.app_services.set_language(lang_code)
        self.main_window.retranslate_ui()

    @Slot(bool)
    def set_background_state(self, is_background: bool):
        """Handles transitions between foreground and background operation."""
        if self._is_shutting_down or self._is_in_background == is_background:
            return
        self._is_in_background = is_background
        # Use the new public method to control the service's update loop
        self.app_services.set_active_updates(not is_background)

    @Slot()
    def shutdown(self):
        """Initiates a graceful shutdown via AppServices and quits the app."""
        if self._is_shutting_down:
            return
        self._is_shutting_down = True
        print("AppRunner: Initiating shutdown...")

        # AppServices handles the core component shutdown
        self.app_services.shutdown()

        # Quit the application
        app = QApplication.instance()
        if app:
            print("AppRunner: Quitting QApplication.")
            QTimer.singleShot(0, app.quit)

# --- Exception Handling Hook ---
def handle_exception(exc_type, exc_value, exc_traceback):
    """Global exception handler to log errors and show a message."""
    error_msg_detail = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    print(f"Unhandled Exception:\n{error_msg_detail}", file=sys.stderr)

    try:
        title_key = "unhandled_exception_title"
        title = tr(title_key) if '_translations_loaded' in globals() and _translations_loaded else "Unhandled Exception"
        msg = f"An unexpected critical error occurred:\n\n{exc_value}\n\nPlease report this issue."

        app = QApplication.instance() or QApplication([])
        msg_box = QMessageBox()
        msg_box.setIcon(QMessageBox.Icon.Critical)
        msg_box.setWindowTitle(title)
        msg_box.setText(msg)
        msg_box.exec()
    except Exception as e:
        print(f"Error showing exception message box: {e}", file=sys.stderr)
        if os.name == 'nt':
            try:
                ctypes.windll.user32.MessageBoxW(0, f"Unhandled Exception:\n{exc_value}", "Critical Error", 0x10 | 0x1000)
            except Exception: pass

    print("Attempting cleanup after unhandled exception...")
    perform_cleanup()
    print("Forcing exit after exception.")
    os._exit(1)

# --- Cleanup Function ---
_cleanup_called = False
def perform_cleanup():
    """Performs application cleanup actions on exit."""
    global app_services_instance, _cleanup_called
    if _cleanup_called:
        return
    _cleanup_called = True
    print("Performing cleanup...")

    # 1. Shutdown AppServices (handles all backend cleanup)
    if app_services_instance:
        print("Shutting down AppServices...")
        try:
            app_services_instance.shutdown()
        except Exception as e:
            print(f"Error during AppServices shutdown: {e}", file=sys.stderr)
        app_services_instance = None
        print("AppServices shutdown completed.")
    else:
        print("AppServices instance not found for shutdown.")

    # 2. Release Mutex and Shared Memory
    print("Releasing mutex and shared memory...")
    release_mutex()
    print("Mutex and shared memory released.")

    print("Cleanup finished.")

# --- Main Execution ---
def main():
    """Main application function."""
    global app_services_instance, app_runner_instance, app_instance

    sys.excepthook = handle_exception
    atexit.register(perform_cleanup)

    languages_json_path = os.path.join(BASE_DIR, LANGUAGES_JSON_NAME)
    load_translations(languages_json_path)

    if os.name == 'nt':
        if not is_admin():
            run_as_admin(BASE_DIR)
            sys.exit(1)
        is_task_launch = STARTUP_ARG_MINIMIZED in sys.argv
        if not check_single_instance(is_task_launch=is_task_launch):
            print("Another instance is running or takeover failed. Exiting.")
            sys.exit(0)

    QCoreApplication.setOrganizationName(APP_ORGANIZATION_NAME)
    QCoreApplication.setApplicationName(APP_INTERNAL_NAME)
    app_instance = QApplication(sys.argv)
    app_instance.setQuitOnLastWindowClosed(False)
    app_instance.aboutToQuit.connect(perform_cleanup)

    # --- Load Configuration ---
    config_path = os.path.join(BASE_DIR, CONFIG_FILE_NAME)
    config_data = load_config(config_path)

    # --- Initialize Service Layer ---
    app_services_instance = AppServices(config_data=config_data, base_dir=BASE_DIR)
    if not app_services_instance.initialize():
        QMessageBox.critical(None, tr("initialization_error_title"), tr("initialization_error_msg"))
        sys.exit(1)

    # --- Initialize UI Layer (AppRunner) ---
    start_minimized = STARTUP_ARG_MINIMIZED in sys.argv
    try:
        # Inject the services into the UI orchestrator
        app_runner_instance = AppRunner(app_services_instance, start_minimized)
    except Exception as init_error:
        handle_exception(type(init_error), init_error, init_error.__traceback__)
        sys.exit(1)

    # --- Start the Qt Event Loop ---
    # HWND is now written to shared memory via a signal from MainWindow to AppRunner,
    # making the logic more robust and removing the need for a timer here.
    print(f"Starting {APP_NAME} event loop...")
    exit_code = app_instance.exec()
    print(f"Application event loop finished with exit code: {exit_code}")
    sys.exit(exit_code)


if __name__ == "__main__":
    main()