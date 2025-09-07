# -*- coding: utf-8 -*-
"""
应用入口，负责初始化、单例检查、管理员权限检查，并启动Qt事件循环。
【最终优化】通过启动一个独立的进程来执行崩溃安全机制，彻底解决了COM重入死锁问题。
"""

import sys
import os
import traceback
import atexit
import ctypes
import subprocess # 【新增】用于启动独立进程
from typing import Optional

# 该逻辑能正确处理脚本、独立可执行文件和单文件模式。
try:
    if os.name == 'nt':
        buffer = ctypes.create_unicode_buffer(2048)
        ctypes.windll.kernel32.GetModuleFileNameW(None, buffer, len(buffer))
        EXECUTABLE_PATH = buffer.value
        
        executable_name = os.path.basename(EXECUTABLE_PATH).lower()
        if executable_name in ('python.exe', 'pythonw.exe'):
            BASE_DIR = os.path.dirname(os.path.abspath(__file__))
        else:
            BASE_DIR = os.path.dirname(EXECUTABLE_PATH)
    else:
        if getattr(sys, 'frozen', False):
            EXECUTABLE_PATH = sys.executable
            BASE_DIR = os.path.dirname(EXECUTABLE_PATH)
        else:
            script_path = __file__ if "__file__" in locals() else sys.argv[0]
            EXECUTABLE_PATH = os.path.abspath(script_path)
            BASE_DIR = os.path.dirname(EXECUTABLE_PATH)
except Exception:
    BASE_DIR = os.getcwd()
    EXECUTABLE_PATH = sys.executable

try:
    os.chdir(BASE_DIR)
except Exception as e:
    print(f"致命错误: 无法将工作目录更改为 '{BASE_DIR}'。外部文件将无法找到。错误: {e}", file=sys.stderr)

# --- 导入项目模块 ---
from gui.qt import QApplication, QMessageBox, QCoreApplication

from config.settings import (
    APP_NAME, APP_ORGANIZATION_NAME, APP_INTERNAL_NAME, STARTUP_ARG_MINIMIZED
)
from tools.localization import load_translations, tr, set_language, _translations_loaded
from tools.system_utils import is_admin, run_as_admin
from tools.single_instance import (
    check_single_instance, release_mutex, write_hwnd_to_shared_memory
)
from core.app_services import AppServices
from core.state import AppState
from core.path_manager import PathManager
from core.profile_manager import ProfileManager
from core.settings_manager import SettingsManager
from gui.main_window import MainWindow

_app_services_for_cleanup: Optional[AppServices] = None

# --- 崩溃安全机制 ---
def _trigger_emergency_fan_setter():
    """
    【最终优化】通过启动一个独立的、隔离的进程来设置紧急风扇速度。
    这可以完全避免在主应用崩溃时发生COM重入死锁。
    """
    print("CRASH HANDLER: 检测到自动模式，正在尝试启动紧急风扇设置进程...")
    try:
        # 确定紧急脚本的路径
        emergency_script_path = os.path.join(BASE_DIR, 'emergency_fan_setter.py')
        if not os.path.exists(emergency_script_path):
            print(f"CRASH HANDLER: 紧急脚本 '{emergency_script_path}' 未找到。", file=sys.stderr)
            return

        # 使用 sys.executable (通常是 pythonw.exe) 来无窗口运行脚本
        # Popen 是非阻塞的，它会立即返回，允许主程序继续其崩溃流程
        subprocess.Popen([sys.executable, emergency_script_path], creationflags=subprocess.CREATE_NO_WINDOW)
        print("CRASH HANDLER: 紧急风扇设置进程已成功启动。")

    except Exception as e:
        print(f"CRASH HANDLER: 启动紧急风扇设置进程失败: {e}", file=sys.stderr)

def handle_exception(exc_type, exc_value, exc_traceback):
    """全局异常处理器，增加了崩溃安全机制。"""
    try:
        last_mode_file = os.path.join(BASE_DIR, 'last_mode.state')
        if os.path.exists(last_mode_file):
            with open(last_mode_file, 'r') as f:
                last_mode = f.read().strip()
            if last_mode == 'auto':
                _trigger_emergency_fan_setter()
    except Exception as safety_e:
        print(f"CRASH HANDLER: 在执行安全机制时发生错误: {safety_e}", file=sys.stderr)

    error_msg_detail = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    print(f"未处理的异常:\n{error_msg_detail}", file=sys.stderr)

    try:
        title = tr("unhandled_exception_title") if '_translations_loaded' in globals() and _translations_loaded else "Unhandled Exception"
        msg = f"发生意外的关键错误:\n\n{exc_value}\n\nPlease report this issue."
        app = QApplication.instance() or QApplication([])
        QMessageBox.critical(None, title, msg)
    except Exception as e:
        print(f"显示异常消息框时出错: {e}", file=sys.stderr)
        if os.name == 'nt':
            try:
                ctypes.windll.user32.MessageBoxW(0, f"未处理的异常:\n{exc_value}", "关键错误", 0x10)
            except Exception: pass

    print("在未处理的异常后尝试清理...")
    perform_cleanup()
    print("异常后强制退出。")
    os._exit(1)

# --- 清理函数 ---
_cleanup_called = False
def perform_cleanup():
    """在退出时执行应用清理操作。"""
    global _app_services_for_cleanup, _cleanup_called
    if _cleanup_called:
        return
    _cleanup_called = True
    print("正在执行清理...")

    if _app_services_for_cleanup:
        print("正在关闭 AppServices...")
        try:
            _app_services_for_cleanup.shutdown()
        except Exception as e:
            print(f"AppServices 关闭期间出错: {e}", file=sys.stderr)
        _app_services_for_cleanup = None
        print("AppServices 关闭完成。")
    else:
        print("未找到 AppServices 实例进行关闭。")

    print("正在释放互斥锁和共享内存...")
    release_mutex()
    print("互斥锁和共享内存已释放。")

    print("清理完成。")

# --- 主函数 ---
def main():
    """主应用函数。"""
    global _app_services_for_cleanup

    sys.excepthook = handle_exception
    atexit.register(perform_cleanup)

    path_manager = PathManager(base_dir=BASE_DIR)
    load_translations(path_manager.languages)

    if os.name == 'nt':
        if not is_admin():
            run_as_admin(EXECUTABLE_PATH, BASE_DIR)
            sys.exit(1)
        
        is_task_launch = STARTUP_ARG_MINIMIZED in sys.argv
        if not check_single_instance(is_task_launch=is_task_launch):
            print("另一个实例正在运行。已发送命令，本实例将退出。")
            sys.exit(0)

    QCoreApplication.setOrganizationName(APP_ORGANIZATION_NAME)
    QCoreApplication.setApplicationName(APP_INTERNAL_NAME)
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.aboutToQuit.connect(perform_cleanup)

    try:
        app_state = AppState(path_manager=path_manager)
        profile_manager = ProfileManager(app_state=app_state)
        settings_manager = SettingsManager(app_state=app_state, profile_manager=profile_manager)
        
        app_services = AppServices(state=app_state)
        _app_services_for_cleanup = app_services

        if not app_services.initialize_wmi():
            error_title = tr("wmi_init_error_title")
            error_text = app_state.get_controller_status_message()
            QMessageBox.critical(None, error_title, error_text)
            sys.exit(1)

        profile_manager.load_config()
        set_language(app_state.get_language())
        
        start_minimized = STARTUP_ARG_MINIMIZED in sys.argv
        main_window = MainWindow(
            app_services=app_services, 
            state=app_state,
            profile_manager=profile_manager,
            settings_manager=settings_manager,
            start_minimized=start_minimized
        )

        if os.name == 'nt':
            main_window.window_initialized_signal.connect(write_hwnd_to_shared_memory)

    except Exception as init_error:
        handle_exception(type(init_error), init_error, init_error.__traceback__)
        sys.exit(1)

    print(f"启动 {APP_NAME} 事件循环...")
    exit_code = app.exec()
    print(f"应用事件循环结束，退出代码: {exit_code}")
    sys.exit(exit_code)


if __name__ == "__main__":
    main()