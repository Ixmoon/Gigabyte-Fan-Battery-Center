# -*- coding: utf-8 -*-
"""
提供功能以确保只有一个应用实例使用Windows上的命名互斥锁和共享内存运行。
处理现有窗口的激活和实例间通信。
"""

import sys
import os
import ctypes
from typing import Optional

# 从设置导入名称、大小、应用名称和命令
from config.settings import (
    MUTEX_NAME, SHARED_MEM_NAME, SHARED_MEM_SIZE, APP_NAME,
    SHARED_MEM_HWND_OFFSET, SHARED_MEM_HWND_SIZE, SHARED_MEM_COMMAND_OFFSET,
    COMMAND_NONE, COMMAND_RELOAD_AND_SHOW, COMMAND_RELOAD_ONLY
)
# 从本地化导入消息
from .localization import tr

# --- Win32 API 导入和设置 ---
_mutex_handle: Optional[int] = None
_shared_mem_handle: Optional[int] = None
_shared_mem_view: Optional[int] = None
_single_instance_check_enabled: bool = False

if os.name == 'nt':
    try:
        from ctypes import wintypes
        import win32con

        # 常量
        ERROR_ALREADY_EXISTS = 183
        INVALID_HANDLE_VALUE = -1
        PAGE_READWRITE = 0x04
        FILE_MAP_ALL_ACCESS = 0xF001F

        # 函数原型
        kernel32 = ctypes.windll.kernel32
        user32 = ctypes.windll.user32

        CreateMutexW = kernel32.CreateMutexW
        CreateMutexW.restype = wintypes.HANDLE
        CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]

        GetLastError = kernel32.GetLastError
        ReleaseMutex = kernel32.ReleaseMutex
        CloseHandle = kernel32.CloseHandle

        # 共享内存函数
        CreateFileMappingW = kernel32.CreateFileMappingW
        CreateFileMappingW.restype = wintypes.HANDLE
        CreateFileMappingW.argtypes = [wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.LPCWSTR]

        MapViewOfFile = kernel32.MapViewOfFile
        MapViewOfFile.restype = wintypes.LPVOID
        MapViewOfFile.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_size_t]

        UnmapViewOfFile = kernel32.UnmapViewOfFile
        UnmapViewOfFile.restype = wintypes.BOOL
        UnmapViewOfFile.argtypes = [wintypes.LPCVOID]

        # 激活函数
        IsWindow = user32.IsWindow
        SetForegroundWindow = user32.SetForegroundWindow
        ShowWindow = user32.ShowWindow
        SW_RESTORE = win32con.SW_RESTORE

        _single_instance_check_enabled = True

    except (ImportError, AttributeError, OSError) as e:
        print(f"警告: 加载用于单实例检查的Win32模块失败: {e}", file=sys.stderr)
        _single_instance_check_enabled = False
else:
    # 在非Windows系统上禁用此功能
    _single_instance_check_enabled = False

# --- 共享内存管理 ---

def _create_or_open_shared_memory() -> bool:
    """创建或打开命名共享内存块。"""
    global _shared_mem_handle, _shared_mem_view
    if not _single_instance_check_enabled: return False

    _shared_mem_handle = CreateFileMappingW(
        INVALID_HANDLE_VALUE, None, PAGE_READWRITE, 0, SHARED_MEM_SIZE, SHARED_MEM_NAME
    )
    if not _shared_mem_handle:
        return False

    _shared_mem_view = MapViewOfFile(_shared_mem_handle, FILE_MAP_ALL_ACCESS, 0, 0, SHARED_MEM_SIZE)
    if not _shared_mem_view:
        CloseHandle(_shared_mem_handle)
        _shared_mem_handle = None
        return False

    return True

def write_hwnd_to_shared_memory(hwnd: int):
    """将窗口句柄（HWND）写入共享内存的指定位置。"""
    global _shared_mem_view
    if not _single_instance_check_enabled or not _shared_mem_view:
        return

    try:
        hwnd_str = str(hwnd).encode('utf-8')
        if len(hwnd_str) >= SHARED_MEM_HWND_SIZE:
            raise ValueError("HWND字符串对于其共享内存块来说太大了")

        # 将HWND写入缓冲区的指定偏移量
        buffer = (ctypes.c_char * SHARED_MEM_HWND_SIZE).from_address(_shared_mem_view + SHARED_MEM_HWND_OFFSET)
        ctypes.memset(_shared_mem_view + SHARED_MEM_HWND_OFFSET, 0, SHARED_MEM_HWND_SIZE) # 先清零
        buffer.value = hwnd_str
    except Exception as e:
        print(f"写入HWND到共享内存时出错: {e}", file=sys.stderr)

def read_hwnd_from_shared_memory() -> Optional[int]:
    """从共享内存的指定位置读取窗口句柄（HWND）。"""
    global _shared_mem_view
    if not _single_instance_check_enabled or not _shared_mem_view:
        return None

    try:
        buffer = (ctypes.c_char * SHARED_MEM_HWND_SIZE).from_address(_shared_mem_view + SHARED_MEM_HWND_OFFSET)
        hwnd_str = buffer.value.decode('utf-8').strip('\x00')
        return int(hwnd_str) if hwnd_str else None
    except (ValueError, TypeError, UnicodeDecodeError) as e:
        print(f"从共享内存读取HWND时出错: {e}", file=sys.stderr)
        return None

def write_command_to_shared_memory(command: int):
    """将命令字节写入共享内存的指定位置。"""
    global _shared_mem_view
    if not _single_instance_check_enabled or not _shared_mem_view:
        return

    try:
        command_ptr = (ctypes.c_byte*1).from_address(_shared_mem_view + SHARED_MEM_COMMAND_OFFSET)
        command_ptr[0] = command
    except Exception as e:
        print(f"写入命令到共享内存时出错: {e}", file=sys.stderr)

def read_command_from_shared_memory() -> Optional[int]:
    """从共享内存的指定位置读取命令字节。"""
    global _shared_mem_view
    if not _single_instance_check_enabled or not _shared_mem_view:
        return None

    try:
        command_ptr = (ctypes.c_byte*1).from_address(_shared_mem_view + SHARED_MEM_COMMAND_OFFSET)
        return command_ptr[0]
    except Exception as e:
        print(f"从共享内存读取命令时出错: {e}", file=sys.stderr)
        return None

def close_shared_memory():
    """取消映射并关闭共享内存句柄。"""
    global _shared_mem_view, _shared_mem_handle
    if _shared_mem_view:
        UnmapViewOfFile(_shared_mem_view)
        _shared_mem_view = None
    if _shared_mem_handle:
        CloseHandle(_shared_mem_handle)
        _shared_mem_handle = None

# --- 单实例检查 ---

def check_single_instance(is_task_launch: bool = False) -> bool:
    """
    使用系统范围的互斥锁检查另一个实例。
    如果另一个实例存在，此函数会向其发送命令并返回False。
    否则，它会获取互斥锁并返回True。
    """
    global _mutex_handle, _single_instance_check_enabled
    if not _single_instance_check_enabled:
        return True # 在非Windows或API不可用时，总是允许运行

    _mutex_handle = CreateMutexW(None, True, MUTEX_NAME)
    last_error = GetLastError()

    if last_error == ERROR_ALREADY_EXISTS:
        # 已有实例在运行
        if _mutex_handle:
            CloseHandle(_mutex_handle) # 释放我们尝试创建但失败的句柄
        
        # 根据启动类型决定发送哪个命令
        command_to_send = COMMAND_RELOAD_ONLY if is_task_launch else COMMAND_RELOAD_AND_SHOW
        _send_command_and_exit(command_to_send)
        return False # 告知主程序退出

    if not _mutex_handle:
        # 这是一个严重错误，无法创建互斥锁
        ctypes.windll.user32.MessageBoxW(0, "无法创建互斥锁。应用可能无法正常运行。", "严重错误", 0x10)
        return True # 允许运行，但功能可能受限

    # 这是第一个实例
    _create_or_open_shared_memory()
    return True

def _send_command_and_exit(command: int):
    """
    连接到现有实例的共享内存，发送命令，（如果需要）激活窗口，然后退出。
    """
    if _create_or_open_shared_memory():
        hwnd = read_hwnd_from_shared_memory()
        if hwnd and IsWindow(hwnd):
            # 仅当命令要求时才激活窗口
            if command == COMMAND_RELOAD_AND_SHOW:
                _bring_window_to_front(hwnd)
        
        write_command_to_shared_memory(command)
        close_shared_memory()
    else:
        # 如果连共享内存都无法打开，显示一个回退消息框
        ctypes.windll.user32.MessageBoxW(0,
            tr("single_instance_error_msg", app_name=APP_NAME),
            tr("single_instance_error_title"), 0x40)

def _bring_window_to_front(hwnd: int):
    """使用可靠的方法将指定的窗口带到前台。"""
    try:
        # 步骤 1: 恢复窗口（处理最小化或隐藏的情况）
        ShowWindow(hwnd, SW_RESTORE)
        
        # 步骤 2: 将窗口设为前景，这比简单的 show() 更强大
        SetForegroundWindow(hwnd)
    except Exception as e:
        print(f"将窗口带到前台时出错: {e}", file=sys.stderr)

def release_mutex():
    """在应用退出时释放互斥锁和共享内存句柄。"""
    global _mutex_handle
    close_shared_memory()
    if _mutex_handle:
        ReleaseMutex(_mutex_handle)
        CloseHandle(_mutex_handle)
        _mutex_handle = None