# tools/single_instance.py
# -*- coding: utf-8 -*-
"""
Provides functionality to ensure only one instance of the application runs
using a named mutex and shared memory on Windows. Handles activation of
the existing window and attempts recovery from crashes.
"""

import sys
import os
import time # For potential delays
from typing import Optional, Tuple

# Import settings for names, size, app name, startup argument
from config.settings import (
    MUTEX_NAME, SHARED_MEM_NAME, SHARED_MEM_SIZE, APP_NAME, STARTUP_ARG_MINIMIZED
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
        import win32gui # Still useful for activation
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

        ShowWindow = user32.ShowWindow
        ShowWindow.restype = wintypes.BOOL
        ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]

        IsIconic = user32.IsIconic
        IsIconic.restype = wintypes.BOOL
        IsIconic.argtypes = [wintypes.HWND]

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
    """Writes the HWND (as string) to the shared memory."""
    global _shared_mem_view
    if not _single_instance_check_enabled or not _shared_mem_view:
        print("Warning: Cannot write HWND, shared memory not initialized.", file=sys.stderr)
        return

    try:
        hwnd_str = str(hwnd).encode('utf-8')
        if len(hwnd_str) >= SHARED_MEM_SIZE:
            raise ValueError("HWND string representation too large for shared memory")

        # Create a buffer from the mapped view
        buffer = (ctypes.c_char * SHARED_MEM_SIZE).from_address(_shared_mem_view)
        # Clear buffer first
        ctypes.memset(_shared_mem_view, 0, SHARED_MEM_SIZE)
        # Copy HWND string into buffer
        buffer.value = hwnd_str
        print(f"HWND {hwnd} written to shared memory.") # Debug
    except Exception as e:
        print(f"Error writing HWND to shared memory: {e}", file=sys.stderr)

def read_hwnd_from_shared_memory() -> Optional[int]:
    """Reads the HWND (as string) from shared memory and converts to int."""
    global _shared_mem_view
    if not _single_instance_check_enabled or not _shared_mem_view:
        return None

    try:
        buffer = (ctypes.c_char * SHARED_MEM_SIZE).from_address(_shared_mem_view)
        hwnd_str = buffer.value.decode('utf-8')
        if hwnd_str:
            return int(hwnd_str)
        else:
            return None
    except (ValueError, TypeError, UnicodeDecodeError) as e:
        print(f"Error reading or converting HWND from shared memory: {e}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Unexpected error reading HWND from shared memory: {e}", file=sys.stderr)
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

def check_single_instance() -> bool:
    """
    Checks for another instance using Mutex and Shared Memory.
    Handles activation and crash recovery.

    Returns:
        bool: True if this instance should continue (is primary or recovered),
              False if another *running* instance was activated and this one should exit.
    """
    global _mutex_handle, _single_instance_check_enabled, _is_primary_instance
    if not _single_instance_check_enabled:
        return True # Allow continuation if check is disabled

    _is_primary_instance = False # Reset flag

    try:
        # 1. Try to create the mutex
        _mutex_handle = CreateMutexW(None, False, MUTEX_NAME)
        last_error = GetLastError()

        if _mutex_handle and last_error == 0:
            # 2. Success: This is the first instance.
            print("Mutex created. This is the primary instance.")
            _is_primary_instance = True
            # Create or open shared memory (will create it here)
            if not _create_or_open_shared_memory():
                 print("Warning: Failed to create shared memory for primary instance.", file=sys.stderr)
                 # Continue anyway, but activation won't work for subsequent instances
            return True # Continue execution

        elif last_error == ERROR_ALREADY_EXISTS:
            # 3. Mutex already exists. Try to open it and check state.
            print("Mutex exists. Checking state of existing instance...")
            if _mutex_handle: # Close the handle returned by CreateMutexW when it fails
                CloseHandle(_mutex_handle)
                _mutex_handle = None

            existing_mutex = OpenMutexW(MUTEX_ALL_ACCESS, False, MUTEX_NAME)
            if not existing_mutex:
                # Failed to open existing mutex - unusual, maybe permissions? Assume crash.
                print(f"Warning: Could not open existing mutex (Error: {GetLastError()}). Assuming previous instance crashed.")
                # Try to forcefully create our own mutex now? Risky.
                # Let's proceed as if we are the primary, but without holding the mutex.
                _is_primary_instance = True # Act as primary for shared mem creation
                if not _create_or_open_shared_memory():
                     print("Warning: Failed to create shared memory after failing to open mutex.", file=sys.stderr)
                return True # Continue execution

            # Check if the mutex is abandoned (previous owner crashed)
            wait_result = WaitForSingleObject(existing_mutex, 0)

            if wait_result == WAIT_ABANDONED:
                # 4. Mutex abandoned: Previous instance crashed. This instance takes over.
                print("Existing mutex is abandoned. Assuming previous instance crashed. Taking over.")
                # We now implicitly own the mutex. Keep the handle.
                _mutex_handle = existing_mutex
                _is_primary_instance = True
                # Create/overwrite shared memory
                if not _create_or_open_shared_memory():
                     print("Warning: Failed to create/overwrite shared memory after abandoned mutex.", file=sys.stderr)
                return True # Continue execution

            elif wait_result == WAIT_TIMEOUT:
                # 5. Mutex held: Previous instance likely running. Activate it.
                print("Existing mutex is held. Attempting to activate existing window.")
                CloseHandle(existing_mutex) # Close the handle we opened for checking
                existing_mutex = None

                # Open shared memory to read HWND
                if not _create_or_open_shared_memory():
                    print("Error: Failed to open shared memory to read HWND.", file=sys.stderr)
                    # Cannot activate, show message and exit
                    _show_activation_fallback_message()
                    return False # Exit this instance

                hwnd = read_hwnd_from_shared_memory()
                if hwnd and IsWindow(hwnd):
                    print(f"Found valid HWND {hwnd} in shared memory. Activating.")
                    try:
                        if IsIconic(hwnd):
                            ShowWindow(hwnd, SW_RESTORE)
                        SetForegroundWindow(hwnd)
                        # Give focus some time? Might not be necessary.
                        # time.sleep(0.1)
                    except Exception as activation_error:
                         print(f"Error activating window {hwnd}: {activation_error}", file=sys.stderr)
                         _show_activation_fallback_message()
                else:
                    print("Warning: Could not read valid HWND from shared memory or window no longer exists.")
                    _show_activation_fallback_message()

                # Regardless of activation success/failure, this instance should exit.
                close_shared_memory() # Clean up handles for this instance
                return False # Exit this instance

            elif wait_result == WAIT_OBJECT_0:
                 # Should not happen if CreateMutex failed with ERROR_ALREADY_EXISTS
                 # but means mutex was signaled. Treat as running.
                 print("Warning: Mutex check returned WAIT_OBJECT_0 unexpectedly. Assuming running instance.")
                 ReleaseMutex(existing_mutex) # Release the ownership we just got
                 CloseHandle(existing_mutex)
                 # Try activating
                 if _create_or_open_shared_memory():
                     hwnd = read_hwnd_from_shared_memory()
                     if hwnd and IsWindow(hwnd): _activate_window(hwnd)
                     else: _show_activation_fallback_message()
                     close_shared_memory()
                 else:
                     _show_activation_fallback_message()
                 return False # Exit this instance

            else: # WAIT_FAILED or other error
                print(f"Warning: WaitForSingleObject failed (Result: {wait_result}, Error: {GetLastError()}). Assuming running instance.")
                CloseHandle(existing_mutex)
                # Try activating as a best guess
                if _create_or_open_shared_memory():
                    hwnd = read_hwnd_from_shared_memory()
                    if hwnd and IsWindow(hwnd): _activate_window(hwnd)
                    else: _show_activation_fallback_message()
                    close_shared_memory()
                else:
                    _show_activation_fallback_message()
                return False # Exit this instance

        else:
            # 6. CreateMutexW failed for a reason other than ERROR_ALREADY_EXISTS
            print(f"Warning: Failed to create mutex (Error code: {last_error}). Single instance check disabled.", file=sys.stderr)
            _single_instance_check_enabled = False
            if _mutex_handle: CloseHandle(_mutex_handle) # Should be null, but safety
            _mutex_handle = None
            return True # Allow continuation

    except Exception as e:
        print(f"Error during single instance check: {e}. Disabling check.", file=sys.stderr)
        _single_instance_check_enabled = False
        release_mutex() # Clean up any handles acquired before the error
        return True # Allow continuation

def is_primary() -> bool:
    """Returns True if this instance is determined to be the primary one."""
    return _is_primary_instance

def _activate_window(hwnd: int):
    """Helper function to bring a window to the foreground."""
    try:
        if IsIconic(hwnd):
            ShowWindow(hwnd, SW_RESTORE)
        SetForegroundWindow(hwnd)
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