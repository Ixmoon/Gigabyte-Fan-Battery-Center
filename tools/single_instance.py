# tools/single_instance.py
# -*- coding: utf-8 -*-
"""
Provides functionality to ensure only one instance of the application runs
using a named mutex and shared memory on Windows. Handles activation of
the existing window and attempts recovery from crashes.
"""

import sys
import os
import ctypes
from typing import Optional

# Import settings for names, size, app name, startup argument
from config.settings import (
    MUTEX_NAME, SHARED_MEM_NAME, SHARED_MEM_SIZE, APP_NAME, STARTUP_ARG_MINIMIZED,
    SHARED_MEM_HWND_OFFSET, SHARED_MEM_HWND_SIZE, SHARED_MEM_COMMAND_OFFSET,
    COMMAND_QUIT, COMMAND_RELOAD_AND_SHOW, COMMAND_RELOAD_ONLY
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
    Checks for another instance using a system-wide mutex. This is the definitive method.
    If another instance exists, this function sends it a command and returns False.
    Otherwise, it acquires the mutex and returns True.
    """
    global _mutex_handle, _single_instance_check_enabled, _is_primary_instance
    if not _single_instance_check_enabled:
        return True

    _is_primary_instance = False
    try:
        # The CreateMutexW function is atomic. It's the only reliable way to check.
        _mutex_handle = CreateMutexW(None, True, MUTEX_NAME) # Request initial ownership
        last_error = GetLastError()

        if _mutex_handle and last_error == 0:
            # Case 1: Success. We created the mutex and are the primary instance.
            print("Mutex acquired. This is the primary instance.")
            _is_primary_instance = True
            if not _create_or_open_shared_memory():
                print("Warning: Failed to create shared memory for primary instance.", file=sys.stderr)
            # We successfully acquired the mutex, so we don't release it here.
            # It will be released on application exit.
            return True

        elif last_error == ERROR_ALREADY_EXISTS:
            # Case 2: The mutex already exists. Another instance is running.
            # We do not need to check its state. We just send a command and exit.
            if _mutex_handle:
                # On ERROR_ALREADY_EXISTS, CreateMutexW returns a handle to the existing mutex.
                # We must close it as we are not going to use it.
                CloseHandle(_mutex_handle)
                _mutex_handle = None

            print("Existing instance found. Sending command and exiting.")
            command_to_send = COMMAND_RELOAD_ONLY if is_task_launch else COMMAND_RELOAD_AND_SHOW
            _send_command_and_exit(command_to_send)
            return False # This instance MUST exit.

        else:
            # Case 3: A more serious error occurred creating the mutex.
            print(f"Warning: Failed to create mutex (Error: {last_error}). Disabling single-instance check.", file=sys.stderr)
            if _mutex_handle:
                CloseHandle(_mutex_handle)
            _mutex_handle = None
            _single_instance_check_enabled = False
            return True # Allow execution to continue, but without single-instance guarantees.

    except Exception as e:
        print(f"Critical error during single instance check: {e}. Disabling check.", file=sys.stderr)
        _single_instance_check_enabled = False
        if _mutex_handle:
            release_mutex() # Attempt to clean up
        return True

def _send_command_and_exit(command: int):
    """
    Reads HWND, activates the window, sends a command, and exits.
    This is the correct place to activate the window, as this process has foreground focus.
    """
    if _create_or_open_shared_memory():
        # Step 1: Activate the existing window.
        hwnd = read_hwnd_from_shared_memory()
        if hwnd and IsWindow(hwnd):
            _bring_window_to_front(hwnd)
        
        # Step 2: Send the command to the primary instance.
        write_command_to_shared_memory(command)
        close_shared_memory()
    else:
        print("Error: Could not open shared memory to send command. Exiting.", file=sys.stderr)

def _bring_window_to_front(hwnd: int):
    """Forcefully brings the specified window to the foreground."""
    try:
        # Restore if minimized
        if IsIconic(hwnd):
            ShowWindow(hwnd, SW_RESTORE)
        
        # The key call: this process has focus, so it can yield it.
        SetForegroundWindow(hwnd)
    except Exception as e:
        print(f"Error bringing window to front: {e}", file=sys.stderr)

def is_primary() -> bool:
    """Returns True if this instance is determined to be the primary one."""
    return _is_primary_instance

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