# tools/system_utils.py
# -*- coding: utf-8 -*-
"""
OS-level utility functions, primarily for Windows-specific operations.
"""

import sys
import os
import ctypes
import subprocess

# Import localization for error messages
from .localization import tr
# Import settings for base directory (needed for relaunch)

def is_admin() -> bool:
    """Checks if the script is running with Administrator privileges on Windows."""
    if os.name == 'nt':
        try:
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except AttributeError:
            # Could happen if shell32 is unavailable or IsUserAnAdmin is missing
            print("Warning: Could not determine administrator status via ctypes.", file=sys.stderr)
            return False # Assume not admin if check fails
    else:
        # On non-Windows systems, this concept doesn't directly apply in the same way.
        # For simplicity, return True, assuming privilege checks are handled differently.
        return True

def run_as_admin(base_dir: str):
    """
    Attempts to relaunch the application with administrator privileges on Windows.
    If successful, the current non-admin instance exits.
    If elevation fails or is cancelled, it shows an error and exits.
    """
    if os.name != 'nt':
        print("run_as_admin is only applicable on Windows.", file=sys.stderr)
        return # No-op on other platforms

    if is_admin():
        return # Already admin

    # Use localization for error messages
    error_title = tr("elevation_error_title")
    error_msg_base = tr("elevation_error_msg")

    try:
        executable = sys.executable
        # Ensure parameters are correctly quoted, especially paths
        # Use sys.argv directly as they should be the command line args passed to the script
        params_list = sys.argv # Includes the script name itself
        # Reconstruct the command line arguments string
        # Quote each argument that contains spaces
        params = subprocess.list2cmdline(params_list)
        # The first argument (sys.executable) is the command, the rest are parameters
        # ShellExecuteW needs the script path as the file and the rest as parameters
        script_path = get_application_script_path_for_task() # Get the .py file path if running as script
        if script_path:
            # Running as script: executable is python, file is script, params are args *after* script
            python_exe = executable
            script_file = script_path
            script_params_list = sys.argv[1:] # Arguments after the script name
            script_params = subprocess.list2cmdline(script_params_list)
            # ShellExecuteW call for scripts
            result = ctypes.windll.shell32.ShellExecuteW(
                None,           # hwnd
                "runas",        # lpOperation
                python_exe,     # lpFile (the interpreter)
                f'"{script_file}" {script_params}', # lpParameters (quoted script path + args)
                base_dir,       # lpDirectory (working directory)
                1               # nShowCmd (SW_SHOWNORMAL)
            )
        else:
            # Running as frozen executable: executable is the .exe, file is the .exe, params are args
            exe_file = executable
            exe_params_list = sys.argv[1:] # Arguments after the exe name
            exe_params = subprocess.list2cmdline(exe_params_list)
            # ShellExecuteW call for executables
            result = ctypes.windll.shell32.ShellExecuteW(
                None,           # hwnd
                "runas",        # lpOperation
                exe_file,       # lpFile (the executable)
                exe_params,     # lpParameters (arguments passed to the exe)
                base_dir,       # lpDirectory (working directory)
                1               # nShowCmd
            )

        if result <= 32:
            # Error codes are <= 32. Common errors:
            # 0: Out of memory/resources
            # 2: File not found (ERROR_FILE_NOT_FOUND)
            # 3: Path not found (ERROR_PATH_NOT_FOUND)
            # 5: Access denied (ERROR_ACCESS_DENIED) - Should not happen with 'runas' unless blocked by policy
            # 8: Not enough memory (ERROR_NOT_ENOUGH_MEMORY)
            # 11: Bad format (ERROR_BAD_FORMAT)
            # 26: End of file (ERROR_HANDLE_EOF) - Unlikely
            # 27: Write fault (ERROR_WRITE_FAULT) - Unlikely
            # 31: General failure (ERROR_GEN_FAILURE)
            # 32: Sharing violation (ERROR_SHARING_VIOLATION)
            # 1223: Operation cancelled by user (ERROR_CANCELLED) - UAC prompt denied
            error_code = result
            if error_code == 1223:
                # User cancelled UAC prompt, exit silently
                sys.exit(1)
            else:
                detailed_error = f"ShellExecuteW failed with error code: {error_code}"
                final_error_msg = f"{error_msg_base}\n\n{detailed_error}"
                ctypes.windll.user32.MessageBoxW(0, final_error_msg, error_title, 0x10 | 0x1000)
                sys.exit(1) # Exit after showing error
        else:
            # Elevation successful (or UAC prompt shown), exit the non-admin instance
            sys.exit(0)

    except Exception as e:
        # Catch any other exceptions during the elevation attempt
        detailed_error = f"Unexpected error during elevation: {e}"
        final_error_msg = f"{error_msg_base}\n\n{detailed_error}"
        try:
            ctypes.windll.user32.MessageBoxW(0, final_error_msg, error_title, 0x10 | 0x1000)
        except Exception:
             print(f"Error: {final_error_msg}", file=sys.stderr) # Console fallback
        sys.exit(1) # Exit after showing error

def get_application_executable_path() -> str:
    """Gets the full path to the currently running executable (python.exe or the frozen .exe)."""
    # sys.executable is reliable for both script and frozen modes
    return sys.executable

def get_application_script_path_for_task() -> str:
    """
    Gets the absolute path to the main Python script file.
    Returns an empty string if running as a frozen executable.
    Needed for Task Scheduler when running non-frozen.
    """
    if getattr(sys, 'frozen', False):
        # Running as a PyInstaller bundle, no script path needed for task command
        return ""
    else:
        # Running as a script, sys.argv[0] should be the script path
        # Use os.path.abspath to ensure it's an absolute path
        return os.path.abspath(sys.argv[0])