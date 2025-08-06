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
from typing import Optional

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
from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtCore import QCoreApplication, QTimer, QMetaObject, Qt # Added QMetaObject, Qt

from config.settings import (
    APP_NAME, APP_ORGANIZATION_NAME, APP_INTERNAL_NAME, STARTUP_ARG_MINIMIZED,
    LANGUAGES_JSON_NAME, CONFIG_FILE_NAME, PREFERRED_FONTS
)
from tools.localization import load_translations, tr, DEFAULT_ENGLISH_TRANSLATIONS, DEFAULT_LANGUAGE, \
    _translations_loaded # Use internal flag name
from tools.system_utils import is_admin, run_as_admin
# --- MODIFICATION: Import new functions ---
from tools.single_instance import (
    check_single_instance, release_mutex, is_primary, write_hwnd_to_shared_memory,
    IsWindow # Import IsWindow directly if needed for validation in main
)
# --- END MODIFICATION ---
from tools.config_manager import ConfigManager
from run import AppRunner # AppRunner now creates MainWindow

# --- Global Variables ---
app_runner_instance: Optional[AppRunner] = None
app_instance: Optional[QApplication] = None # Keep track of QApplication

# --- Matplotlib Font Setup ---
try:
    import matplotlib.pyplot as plt
    plt.rcParams['font.sans-serif'] = PREFERRED_FONTS
    plt.rcParams['axes.unicode_minus'] = False
except Exception as e:
    print(f"Warning: Could not set preferred fonts for Matplotlib: {e}", file=sys.stderr)
    try:
        plt.rcParams['font.sans-serif'] = ['sans-serif']
        plt.rcParams['axes.unicode_minus'] = True
    except Exception:
        print("Error: Matplotlib font configuration failed.", file=sys.stderr)


# --- Exception Handling Hook ---
def handle_exception(exc_type, exc_value, exc_traceback):
    """Global exception handler to log errors and show a message."""
    error_msg_detail = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    print(f"Unhandled Exception:\n{error_msg_detail}", file=sys.stderr)

    try:
        # Use translations if available, otherwise fallback
        title_key = "unhandled_exception_title"
        title = tr(title_key) if '_translations_loaded' in globals() and _translations_loaded else DEFAULT_ENGLISH_TRANSLATIONS.get(title_key, "Unhandled Exception")
        msg = f"An unexpected critical error occurred:\n\n{exc_value}\n\nPlease report this issue."

        # Ensure QApplication exists for the message box
        app = QApplication.instance()
        temp_app = None
        if not app:
            # Create a temporary minimal app instance if none exists
            temp_app = QApplication.instance() or QApplication([]) # Reuse or create

        msg_box = QMessageBox()
        msg_box.setIcon(QMessageBox.Icon.Critical)
        msg_box.setWindowTitle(title)
        msg_box.setText(msg)
        # msg_box.setDetailedText(error_msg_detail) # Optional
        msg_box.exec()

        # Clean up temporary app if created
        # if temp_app and not QApplication.instance(): temp_app.quit() # Not reliable

    except Exception as e:
        print(f"Error showing exception message box: {e}", file=sys.stderr)
        if os.name == 'nt':
            try:
                ctypes.windll.user32.MessageBoxW(0, f"Unhandled Exception:\n{exc_value}", "Critical Error", 0x10 | 0x1000)
            except Exception: pass

    # --- MODIFICATION: Ensure cleanup runs before forced exit ---
    print("Attempting cleanup after unhandled exception...")
    perform_cleanup()
    print("Forcing exit after exception.")
    os._exit(1) # Force exit

# --- Cleanup Function ---
_cleanup_called = False # Prevent double execution
def perform_cleanup():
    """Performs application cleanup actions on exit."""
    global app_runner_instance, _cleanup_called
    if _cleanup_called:
        # print("Cleanup already called, skipping.") # Debug
        return
    _cleanup_called = True
    print("Performing cleanup...")

    # 1. Shutdown AppRunner (stops timer, WMI, saves config)
    if app_runner_instance:
        print("Shutting down AppRunner...")
        try:
            app_runner_instance.shutdown()
        except Exception as e:
            print(f"Error during AppRunner shutdown: {e}", file=sys.stderr)
        app_runner_instance = None # Clear reference
        print("AppRunner shutdown completed.")
    else:
        print("AppRunner instance not found for shutdown.")

    # 2. Release Mutex and Shared Memory
    print("Releasing mutex and shared memory...")
    release_mutex() # This now handles both
    print("Mutex and shared memory released.")

    print("Cleanup finished.")

# --- Main Execution ---
def main():
    """Main application function."""
    global app_runner_instance, app_instance

    # 1. Set global exception hook
    sys.excepthook = handle_exception

    # 2. Register cleanup function (atexit is crucial for non-Qt exits)
    atexit.register(perform_cleanup)

    # 3. Construct absolute paths
    languages_json_path = os.path.join(BASE_DIR, LANGUAGES_JSON_NAME)

    # 4. Load translations early
    load_translations(languages_json_path)

    # 4. Check for Administrator Privileges (Windows only)
    if os.name == 'nt':
        if not is_admin():
            run_as_admin(BASE_DIR) # Shows message, attempts elevation, exits if needed
            sys.exit(1) # Exit if not elevated

    # 5. Check for Single Instance (Windows only)
    if os.name == 'nt':
        # Determine launch mode to handle single-instance logic correctly
        is_task_launch = STARTUP_ARG_MINIMIZED in sys.argv
        should_continue = check_single_instance(is_task_launch=is_task_launch)
        if not should_continue:
            print("Another instance is running or takeover failed. Exiting.")
            sys.exit(0)
        # If should_continue is True, this instance is now the primary.

    # 6. Initialize QApplication
    QCoreApplication.setOrganizationName(APP_ORGANIZATION_NAME)
    QCoreApplication.setApplicationName(APP_INTERNAL_NAME)
    # --- MODIFICATION: Store app instance ---
    app_instance = QApplication(sys.argv)
    app_instance.setQuitOnLastWindowClosed(False)

    # Connect aboutToQuit for Qt-triggered exits
    app_instance.aboutToQuit.connect(perform_cleanup)
    # --- END MODIFICATION ---

    # 7. Initialize Configuration Manager
    config_manager = ConfigManager(base_dir=BASE_DIR)
    config_manager.load_config() # Sets language

    # 8. Determine if starting minimized
    start_minimized = STARTUP_ARG_MINIMIZED in sys.argv

    # 9. Initialize and Run the Application Orchestrator
    # --- MODIFICATION: AppRunner now creates MainWindow ---
    try:
        app_runner_instance = AppRunner(config_manager, start_minimized)
    except Exception as init_error:
         handle_exception(type(init_error), init_error, init_error.__traceback__)
         sys.exit(1) # Should be caught by hook, but safety exit
    # --- END MODIFICATION ---

    # --- MODIFICATION: Write HWND to Shared Memory if Primary Instance ---
    if os.name == 'nt' and is_primary():
        print("This is the primary instance. Attempting to write HWND to shared memory.")
        # Need to wait slightly for the window to be fully created and get a valid HWND
        # Using a QTimer is safer than time.sleep() within the main thread before exec()
        def write_hwnd_task():
            if app_runner_instance and app_runner_instance.main_window:
                try:
                    # Ensure window exists and has a valid ID
                    main_window = app_runner_instance.main_window
                    # Check if window handle is valid before getting winId
                    # winId() returns WId, which is platform specific. On Windows, it's HWND.
                    # We need to cast it correctly for ctypes.
                    hwnd = int(main_window.winId()) # Cast QWidget.winId() to int for HWND
                    if hwnd != 0 and IsWindow(hwnd): # Check if HWND is non-zero and valid
                        print(f"Main window HWND obtained: {hwnd}")
                        write_hwnd_to_shared_memory(hwnd)
                    else:
                        print(f"Warning: Could not get valid HWND ({hwnd}) after delay. Shared memory not updated.")
                except Exception as e:
                    print(f"Error getting main window HWND or writing to shared memory: {e}", file=sys.stderr)
            else:
                print("Warning: AppRunner or MainWindow not available when attempting to write HWND.", file=sys.stderr)

        # Schedule the task to run shortly after the event loop starts
        QTimer.singleShot(500, write_hwnd_task) # Delay 500ms
    # --- END MODIFICATION ---

    # 10. Start the Qt Event Loop
    print(f"Starting {APP_NAME} event loop...")
    exit_code = app_instance.exec()
    print(f"Application event loop finished with exit code: {exit_code}")

    # 11. Explicit cleanup call (optional, belt-and-suspenders)
    # perform_cleanup() # atexit and aboutToQuit should handle this

    sys.exit(exit_code)


if __name__ == "__main__":
    main()