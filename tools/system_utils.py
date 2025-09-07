# -*- coding: utf-8 -*-
"""
OS级别的工具函数，主要用于Windows特定的操作。
移除了不可靠的路径辅助函数，逻辑现在更集中和健壮。
"""

import sys
import os
import ctypes
import subprocess

from .localization import tr

def is_admin() -> bool:
    """检查脚本是否在Windows上以管理员权限运行。"""
    if os.name == 'nt':
        try:
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except AttributeError:
            print("警告: 无法通过ctypes确定管理员状态。", file=sys.stderr)
            return False
    else:
        return True

def run_as_admin(executable_path: str, base_dir: str):
    """
    尝试在Windows上以管理员权限重新启动应用。
    """
    if os.name != 'nt':
        return

    if is_admin():
        return

    error_title = tr("elevation_error_title")
    error_msg_base = tr("elevation_error_msg")

    try:
        is_script_mode = os.path.basename(executable_path).lower() in ('python.exe', 'pythonw.exe')

        if is_script_mode:
            # 在脚本模式下，我们需要找到主脚本的路径
            main_script_path = os.path.abspath(sys.argv[0])
            params = f'"{main_script_path}" {subprocess.list2cmdline(sys.argv[1:])}'
        else:
            params = subprocess.list2cmdline(sys.argv[1:])

        result = ctypes.windll.shell32.ShellExecuteW(None, "runas", executable_path, params, base_dir, 1)

        if result <= 32:
            if result == 1223:
                sys.exit(1)
            else:
                detailed_error = f"ShellExecuteW failed with code: {result}."
                final_error_msg = f"{error_msg_base}\n\n{detailed_error}"
                ctypes.windll.user32.MessageBoxW(0, final_error_msg, error_title, 0x10 | 0x1000)
                sys.exit(1)
        else:
            sys.exit(0)

    except Exception as e:
        detailed_error = f"Unexpected error during elevation: {e}"
        final_error_msg = f"{error_msg_base}\n\n{detailed_error}"
        ctypes.windll.user32.MessageBoxW(0, final_error_msg, error_title, 0x10 | 0x1000)
        sys.exit(1)

# 删除了 get_application_executable_path 和 get_application_script_path_for_task
# 这两个函数是导致路径问题的根源，所有路径现在都应从 PathManager 获取。