# main.py
# -*- coding: utf-8 -*-
"""
Application Entry Point for Fan & Battery Control.

Handles initialization, single instance check, admin rights check,
creates the main application runner, and starts the Qt event loop.
"""

import sys
import os
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
from gui.qt import QApplication, QMessageBox, QCoreApplication

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
# These are now managed within the main function's scope
# and passed to the cleanup function directly.
_app_services_for_cleanup: Optional[AppServices] = None

# --- Matplotlib Font Setup (Now removed as it's a dependency we got rid of) ---
# This section is intentionally left blank.


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
    global _app_services_for_cleanup, _cleanup_called
    if _cleanup_called:
        return
    _cleanup_called = True
    print("Performing cleanup...")

    # 1. Shutdown AppServices (handles all backend cleanup)
    if _app_services_for_cleanup:
        print("Shutting down AppServices...")
        try:
            _app_services_for_cleanup.shutdown()
        except Exception as e:
            print(f"Error during AppServices shutdown: {e}", file=sys.stderr)
        _app_services_for_cleanup = None
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
    global _app_services_for_cleanup

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
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.aboutToQuit.connect(perform_cleanup)

    # --- Initialize Layers ---
    app_services = AppServices(base_dir=BASE_DIR)
    _app_services_for_cleanup = app_services

    start_minimized = STARTUP_ARG_MINIMIZED in sys.argv
    try:
        # --- Synchronous Initialization ---
        # The new model initializes WMI and applies settings before showing the window.
        if not app_services.initialize_and_apply_settings():
            # If WMI initialization fails, show an error and exit.
            # The error message is set within AppServices.
            error_title = tr("wmi_init_error_title")
            error_text = app_services.state.controller_status_message
            QMessageBox.critical(None, error_title, error_text)
            sys.exit(1)

        main_window = MainWindow(app_services, start_minimized)
    except Exception as init_error:
        handle_exception(type(init_error), init_error, init_error.__traceback__)
        sys.exit(1)

    # --- Start the Qt Event Loop ---
    print(f"Starting {APP_NAME} event loop...")
    exit_code = app.exec()
    print(f"Application event loop finished with exit code: {exit_code}")
    sys.exit(exit_code)


if __name__ == "__main__":
    main()