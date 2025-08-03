# tools/single_instance.py
# -*- coding: utf-8 -*-
"""
Provides functionality to ensure only one instance of the application runs
using a named mutex and shared memory on Windows. Handles activation of
the existing window and attempts recovery from crashes.
"""

import sys
import os
from typing import Optional

# Import settings for names, size, app name, startup argument
from config.settings import (
    MUTEX_NAME, SHARED_MEM_NAME, SHARED_MEM_SIZE, APP_NAME, STARTUP_ARG_MINIMIZED,
    SHARED_MEM_HWND_OFFSET, SHARED_MEM_HWND_SIZE, SHARED_MEM_COMMAND_OFFSET,
    COMMAND_QUIT, COMMAND_SHOW
)
# Import localization for messages
from .localization import tr

# --- Win32 API Imports and Setup ---
_mutex_handle: Optional[int] = None
_shared_mem_handle: Optional[int] = None
_shared_mem_view: Optional[int] = None
_single_instance_check_enabled: bool = False
_is_primary_instance: bool = False # Flag to indicate if this instance acquired the mutex first

if os.name == 'nt':
    try:
        import ctypes
        from ctypes import wintypes
        import win32con

        # Constants
        ERROR_ALREADY_EXISTS = 183
        SYNCHRONIZE = 0x00100000
        MUTANT_QUERY_STATE = 0x0001
        STANDARD_RIGHTS_REQUIRED = 0x000F0000
        MUTEX_ALL_ACCESS = STANDARD_RIGHTS_REQUIRED | SYNCHRONIZE | MUTANT_QUERY_STATE
        WAIT_OBJECT_0 = 0x00000000
        WAIT_TIMEOUT = 0x00000102
        WAIT_ABANDONED = 0x00000080
        WAIT_FAILED = 0xFFFFFFFF
        INVALID_HANDLE_VALUE = -1
        PAGE_READWRITE = 0x04
        FILE_MAP_READ = 0x0004
        FILE_MAP_WRITE = 0x0002
        FILE_MAP_ALL_ACCESS = FILE_MAP_WRITE | FILE_MAP_READ

        # Function Prototypes
        kernel32 = ctypes.windll.kernel32
        user32 = ctypes.windll.user32

        CreateMutexW = kernel32.CreateMutexW
        CreateMutexW.restype = wintypes.HANDLE
        CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]

        OpenMutexW = kernel32.OpenMutexW
        OpenMutexW.restype = wintypes.HANDLE
        OpenMutexW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]

        WaitForSingleObject = kernel32.WaitForSingleObject
        WaitForSingleObject.restype = wintypes.DWORD
        WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]

        GetLastError = kernel32.GetLastError
        GetLastError.restype = wintypes.DWORD

        ReleaseMutex = kernel32.ReleaseMutex
        ReleaseMutex.restype = wintypes.BOOL
        ReleaseMutex.argtypes = [wintypes.HANDLE]

        CloseHandle = kernel32.CloseHandle
        CloseHandle.restype = wintypes.BOOL
        CloseHandle.argtypes = [wintypes.HANDLE]

        # Shared Memory Functions
        CreateFileMappingW = kernel32.CreateFileMappingW
        CreateFileMappingW.restype = wintypes.HANDLE
        CreateFileMappingW.argtypes = [wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.LPCWSTR]

        OpenFileMappingW = kernel32.OpenFileMappingW
        OpenFileMappingW.restype = wintypes.HANDLE
        OpenFileMappingW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]

        MapViewOfFile = kernel32.MapViewOfFile
        MapViewOfFile.restype = wintypes.LPVOID
        MapViewOfFile.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_size_t]

        UnmapViewOfFile = kernel32.UnmapViewOfFile
        UnmapViewOfFile.restype = wintypes.BOOL
        UnmapViewOfFile.argtypes = [wintypes.LPCVOID]

        # Activation functions
        IsWindow = user32.IsWindow
        IsWindow.restype = wintypes.BOOL
        IsWindow.argtypes = [wintypes.HWND]

        SetForegroundWindow = user32.SetForegroundWindow
        SetForegroundWindow.restype = wintypes.BOOL
        SetForegroundWindow.argtypes = [wintypes.HWND]

        AllowSetForegroundWindow = user32.AllowSetForegroundWindow
        AllowSetForegroundWindow.restype = wintypes.BOOL
        AllowSetForegroundWindow.argtypes = [wintypes.DWORD]
        ASFW_ANY = -1

        ShowWindow = user32.ShowWindow
        ShowWindow.restype = wintypes.BOOL
        ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]

        IsIconic = user32.IsIconic
        IsIconic.restype = wintypes.BOOL
        IsIconic.argtypes = [wintypes.HWND]

        IsWindowVisible = user32.IsWindowVisible
        IsWindowVisible.restype = wintypes.BOOL
        IsWindowVisible.argtypes = [wintypes.HWND]

        SW_RESTORE = win32con.SW_RESTORE

        _single_instance_check_enabled = True

    except (ImportError, AttributeError, OSError) as e:
        print(f"Warning: Failed to load Win32 modules for single instance check: {e}", file=sys.stderr)
        _single_instance_check_enabled = False
else:
    _single_instance_check_enabled = False

# --- Shared Memory Management ---

def _create_or_open_shared_memory() -> bool:
    """Creates or opens the named shared memory block."""
    global _shared_mem_handle, _shared_mem_view
    if not _single_instance_check_enabled: return False

    # Try to create first (primary instance)
    _shared_mem_handle = CreateFileMappingW(
        INVALID_HANDLE_VALUE, None, PAGE_READWRITE, 0, SHARED_MEM_SIZE, SHARED_MEM_NAME
    )
    last_error = GetLastError()

    if not _shared_mem_handle:
        print(f"Error: CreateFileMappingW failed with error code {last_error}", file=sys.stderr)
        return False

    # If it already existed, CreateFileMappingW returns a handle but sets ERROR_ALREADY_EXISTS
    # If it was newly created, last_error will be 0.
    is_newly_created = (last_error == 0)

    # Map the view
    _shared_mem_view = MapViewOfFile(_shared_mem_handle, FILE_MAP_ALL_ACCESS, 0, 0, SHARED_MEM_SIZE)
    if not _shared_mem_view:
        print(f"Error: MapViewOfFile failed with error code {GetLastError()}", file=sys.stderr)
        CloseHandle(_shared_mem_handle)
        _shared_mem_handle = None
        return False

    # If newly created, initialize memory (optional, but good practice)
    if is_newly_created:
        try:
            ctypes.memset(_shared_mem_view, 0, SHARED_MEM_SIZE)
        except Exception as e:
            print(f"Warning: Failed to zero initialize shared memory: {e}", file=sys.stderr)

    return True

def write_hwnd_to_shared_memory(hwnd: int):
    """Writes the HWND (as string) to its designated block in shared memory."""
    global _shared_mem_view
    if not _single_instance_check_enabled or not _shared_mem_view:
        return

    try:
        hwnd_str = str(hwnd).encode('utf-8')
        if len(hwnd_str) >= SHARED_MEM_HWND_SIZE:
            raise ValueError("HWND string is too large for its shared memory block")

        # Create a buffer pointing to the start of the HWND block
        buffer = (ctypes.c_char * SHARED_MEM_HWND_SIZE).from_address(_shared_mem_view + SHARED_MEM_HWND_OFFSET)
        # Clear only the HWND block
        ctypes.memset(_shared_mem_view + SHARED_MEM_HWND_OFFSET, 0, SHARED_MEM_HWND_SIZE)
        # Write the HWND string
        buffer.value = hwnd_str
        print(f"HWND {hwnd} written to shared memory.")
    except Exception as e:
        print(f"Error writing HWND to shared memory: {e}", file=sys.stderr)

def read_hwnd_from_shared_memory() -> Optional[int]:
    """Reads the HWND from its designated block in shared memory."""
    global _shared_mem_view
    if not _single_instance_check_enabled or not _shared_mem_view:
        return None

    try:
        buffer = (ctypes.c_char * SHARED_MEM_HWND_SIZE).from_address(_shared_mem_view + SHARED_MEM_HWND_OFFSET)
        hwnd_str = buffer.value.decode('utf-8').strip('\x00')
        return int(hwnd_str) if hwnd_str else None
    except (ValueError, TypeError, UnicodeDecodeError) as e:
        print(f"Error reading HWND from shared memory: {e}", file=sys.stderr)
        return None

def write_command_to_shared_memory(command: int):
    """Writes a command byte to its designated block in shared memory."""
    global _shared_mem_view
    if not _single_instance_check_enabled or not _shared_mem_view:
        return

    try:
        # Create a pointer to the command byte location
        command_ptr = (ctypes.c_byte*1).from_address(_shared_mem_view + SHARED_MEM_COMMAND_OFFSET)
        command_ptr[0] = command
        # print(f"Command {command} written to shared memory.") # Verbose
    except Exception as e:
        print(f"Error writing command to shared memory: {e}", file=sys.stderr)

def read_command_from_shared_memory() -> Optional[int]:
    """Reads the command byte from its designated block in shared memory."""
    global _shared_mem_view
    if not _single_instance_check_enabled or not _shared_mem_view:
        return None

    try:
        command_ptr = (ctypes.c_byte*1).from_address(_shared_mem_view + SHARED_MEM_COMMAND_OFFSET)
        return command_ptr[0]
    except Exception as e:
        print(f"Error reading command from shared memory: {e}", file=sys.stderr)
        return None

def close_shared_memory():
    """Unmaps and closes shared memory handles."""
    global _shared_mem_view, _shared_mem_handle
    if _shared_mem_view:
        try: UnmapViewOfFile(_shared_mem_view)
        except Exception as e: print(f"Error unmapping shared memory view: {e}", file=sys.stderr)
        _shared_mem_view = None
    if _shared_mem_handle:
        try: CloseHandle(_shared_mem_handle)
        except Exception as e: print(f"Error closing shared memory handle: {e}", file=sys.stderr)
        _shared_mem_handle = None

# --- Single Instance Check ---

def check_single_instance(is_task_launch: bool = False) -> bool:
    """
    Checks for another instance, with different logic for manual vs. task launches.

    - Manual Launch: Activates the existing window and exits the new instance.
    - Task Launch: Signals the existing instance to gracefully quit, waits for it
      to exit, and then takes over as the primary instance.

    Returns:
        bool: True if this instance should continue, False if it should exit.
    """
    global _mutex_handle, _single_instance_check_enabled, _is_primary_instance
    if not _single_instance_check_enabled:
        return True

    _is_primary_instance = False
    try:
        _mutex_handle = CreateMutexW(None, False, MUTEX_NAME)
        last_error = GetLastError()

        if _mutex_handle and last_error == 0:
            # This is the first and only instance.
            print("Mutex created. This is the primary instance.")
            _is_primary_instance = True
            if not _create_or_open_shared_memory():
                print("Warning: Failed to create shared memory for primary instance.", file=sys.stderr)
            return True

        elif last_error == ERROR_ALREADY_EXISTS:
            # Another instance exists.
            print("Mutex exists. Checking state of existing instance...")
            if _mutex_handle:
                CloseHandle(_mutex_handle)
                _mutex_handle = None

            existing_mutex = OpenMutexW(MUTEX_ALL_ACCESS, False, MUTEX_NAME)
            if not existing_mutex:
                print(f"Warning: Could not open existing mutex (Error: {GetLastError()}). Assuming crash.")
                return _handle_crashed_instance()

            wait_result = WaitForSingleObject(existing_mutex, 0)

            if wait_result == WAIT_ABANDONED:
                print("Existing mutex is abandoned. Assuming crash.")
                _mutex_handle = existing_mutex # We now own it
                return _handle_crashed_instance()

            elif wait_result == WAIT_TIMEOUT:
                # Mutex is held, instance is running.
                if is_task_launch:
                    # Task Launch: Signal old instance to quit, then take over.
                    print("Task Launch: Signaling existing instance to quit.")
                    return _signal_and_takeover(existing_mutex)
                else:
                    # Manual Launch: Activate old instance, then exit.
                    print("Manual Launch: Activating existing instance.")
                    _activate_and_exit(existing_mutex)
                    return False # This instance must exit
            else:
                # Unexpected state, play it safe.
                print(f"Warning: Mutex check had unexpected result {wait_result}. Activating and exiting.")
                ReleaseMutex(existing_mutex)
                CloseHandle(existing_mutex)
                _activate_and_exit(None) # Try to activate without mutex handle
                return False

        else:
            # CreateMutexW failed for another reason.
            print(f"Warning: Failed to create mutex (Error: {last_error}). Disabling check.", file=sys.stderr)
            _single_instance_check_enabled = False
            if _mutex_handle: CloseHandle(_mutex_handle)
            _mutex_handle = None
            return True

    except Exception as e:
        print(f"Error during single instance check: {e}. Disabling check.", file=sys.stderr)
        _single_instance_check_enabled = False
        release_mutex()
        return True

def _handle_crashed_instance() -> bool:
    """Handles logic for taking over from a crashed instance."""
    global _is_primary_instance
    _is_primary_instance = True
    if not _create_or_open_shared_memory():
        print("Warning: Failed to create/overwrite shared memory after crash.", file=sys.stderr)
    return True

def _activate_and_exit(existing_mutex_handle: Optional[int]):
    """Activates the existing window and ensures the current process will exit."""
    if existing_mutex_handle:
        CloseHandle(existing_mutex_handle)
    if _create_or_open_shared_memory():
        hwnd = read_hwnd_from_shared_memory()
        if hwnd and IsWindow(hwnd):
            _activate_window(hwnd)
            # After activating, send a command to ensure it shows itself, in case it was hidden.
            write_command_to_shared_memory(COMMAND_SHOW)
        else:
            _show_activation_fallback_message()
        close_shared_memory()
    else:
        _show_activation_fallback_message()

def _signal_and_takeover(existing_mutex: int) -> bool:
    """Writes a quit command to shared memory and waits to take over the mutex."""
    global _mutex_handle, _is_primary_instance
    if not _create_or_open_shared_memory():
        print("Error: Cannot open shared memory to signal. Aborting.", file=sys.stderr)
        CloseHandle(existing_mutex)
        return False

    # Write the quit command and immediately close our view of the memory.
    write_command_to_shared_memory(COMMAND_QUIT)
    close_shared_memory()

    print("Waiting for existing instance to release mutex...")
    wait_result = WaitForSingleObject(existing_mutex, 5000) # 5-second timeout

    if wait_result == WAIT_OBJECT_0 or wait_result == WAIT_ABANDONED:
        print("Mutex acquired. Taking over as primary instance.")
        _mutex_handle = existing_mutex
        _is_primary_instance = True
        if not _create_or_open_shared_memory():
            print("Warning: Failed to create shared memory after takeover.", file=sys.stderr)
        return True
    else:
        error_code = GetLastError()
        print(f"Error: Timed out waiting for mutex (Result: {wait_result}, Err: {error_code}).", file=sys.stderr)
        CloseHandle(existing_mutex)
        return False

def is_primary() -> bool:
    """Returns True if this instance is determined to be the primary one."""
    return _is_primary_instance

def _activate_window(hwnd: int):
    """Helper function to reliably bring a window to the foreground."""
    try:
        # Allow any process to set the foreground window. This is the key.
        AllowSetForegroundWindow(ASFW_ANY)

        # If the window is hidden or minimized, the show command will handle it.
        # Here, we just need to ensure it gets focus when it does show.
        # If it's already visible, this brings it to the front.
        if IsWindowVisible(hwnd):
             if IsIconic(hwnd):
                ShowWindow(hwnd, SW_RESTORE)
             SetForegroundWindow(hwnd)
        else:
            # If window is not visible (hidden to tray), SetForegroundWindow won't work.
            # The COMMAND_SHOW sent later will trigger the GUI to unhide itself,
            # and at that point it should grab focus.
            print("Window is not visible, relying on COMMAND_SHOW to restore.")

    except Exception as activation_error:
        print(f"Error activating window {hwnd}: {activation_error}", file=sys.stderr)
        _show_activation_fallback_message()

def _show_activation_fallback_message():
    """Shows a message box indicating activation failed."""
    is_task_launch = STARTUP_ARG_MINIMIZED in sys.argv
    if is_task_launch:
        print("Failed to activate existing window during task launch.")
        return # Don't show message box for automated launch

    try:
        msg = tr("single_instance_fallback_msg")
        title = tr("single_instance_error_title")
        user32.MessageBoxW(0, msg, title, 0x30 | 0x1000) # WARNING icon
    except Exception as mb_error:
        print(f"Error showing fallback message: {mb_error}", file=sys.stderr)

def release_mutex():
    """Releases the mutex and closes shared memory handles."""
    global _mutex_handle, _single_instance_check_enabled, _is_primary_instance

    # Close shared memory first
    close_shared_memory()

    # Release mutex if held
    if _single_instance_check_enabled and _mutex_handle:
        try:
            ReleaseMutex(_mutex_handle)
            CloseHandle(_mutex_handle)
            # print("Mutex released and closed.") # Debug
        except Exception as e:
            print(f"Error releasing mutex: {e}", file=sys.stderr)

    _mutex_handle = None
    _is_primary_instance = False # Reset flag on release