# -*- coding: utf-8 -*-
"""
OS级别的工具函数，主要用于Windows特定的操作。
"""

import sys
import os
import ctypes
import subprocess

# 从本地化导入错误消息
from .localization import tr

def is_admin() -> bool:
    """检查脚本是否在Windows上以管理员权限运行。"""
    if os.name == 'nt':
        try:
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except AttributeError:
            print("警告: 无法通过ctypes确定管理员状态。", file=sys.stderr)
            return False # 如果检查失败，则假定不是管理员
    else:
        return True

def run_as_admin(base_dir: str):
    """
    尝试在Windows上以管理员权限重新启动应用。
    如果成功，当前的非管理员实例将退出。
    如果提权失败或被取消，它会显示一个错误并退出。
    """
    if os.name != 'nt':
        return

    if is_admin():
        return

    error_title = tr("elevation_error_title")
    error_msg_base = tr("elevation_error_msg")

    try:
        executable = sys.executable
        script_path = get_application_script_path_for_task()
        
        if script_path:
            # 作为脚本运行：可执行文件是python，文件是脚本
            params = f'"{script_path}" {subprocess.list2cmdline(sys.argv[1:])}'
            result = ctypes.windll.shell32.ShellExecuteW(None, "runas", executable, params, base_dir, 1)
        else:
            # 作为冻结的可执行文件运行
            params = subprocess.list2cmdline(sys.argv[1:])
            result = ctypes.windll.shell32.ShellExecuteW(None, "runas", executable, params, base_dir, 1)

        if result <= 32:
            # 错误代码 <= 32。常见错误：1223 (用户取消)
            if result == 1223:
                sys.exit(1) # 用户取消UAC，静默退出
            else:
                detailed_error = f"ShellExecuteW failed with code: {result}"
                final_error_msg = f"{error_msg_base}\n\n{detailed_error}"
                ctypes.windll.user32.MessageBoxW(0, final_error_msg, error_title, 0x10 | 0x1000)
                sys.exit(1)
        else:
            # 提权成功，退出非管理员实例
            sys.exit(0)

    except Exception as e:
        detailed_error = f"Unexpected error during elevation: {e}"
        final_error_msg = f"{error_msg_base}\n\n{detailed_error}"
        ctypes.windll.user32.MessageBoxW(0, final_error_msg, error_title, 0x10 | 0x1000)
        sys.exit(1)

def get_application_executable_path() -> str:
    """获取当前运行的可执行文件（python.exe或冻结的.exe）的完整路径。"""
    return sys.executable

def get_application_script_path_for_task() -> str:
    """
    获取主Python脚本文件的绝对路径。
    如果作为冻结的可执行文件运行，则返回空字符串。
    在非冻结状态下为任务计划程序所需。
    """
    if getattr(sys, 'frozen', False):
        return ""
    else:
        return os.path.abspath(sys.argv[0])