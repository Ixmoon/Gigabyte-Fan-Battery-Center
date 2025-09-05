# -*- coding: utf-8 -*-
"""
应用入口，负责初始化、单例检查、管理员权限检查，并启动Qt事件循环。
"""

import sys
import os
import traceback
import atexit
import ctypes
from typing import Optional

# --- 早期设置: 定义基础目录 (健壮的方法) ---
# 该逻辑能正确处理脚本、独立可执行文件和单文件模式。
try:
    if os.name == 'nt':
        # 使用 Windows API 获取可执行文件路径，这是最可靠的方法
        buffer = ctypes.create_unicode_buffer(2048)
        ctypes.windll.kernel32.GetModuleFileNameW(None, buffer, len(buffer))
        BASE_DIR = os.path.dirname(buffer.value)
    else:
        # 为非 Windows 系统提供回退
        if getattr(sys, 'frozen', False):
            BASE_DIR = os.path.dirname(sys.executable)
        else:
            BASE_DIR = os.path.dirname(os.path.abspath(__file__))
except Exception:
    # 最终回退方案
    BASE_DIR = os.getcwd()

# --- 更改工作目录 ---
# 这对于单文件模式下查找外部配置文件/语言文件至关重要。
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

# --- 全局变量 ---
# 该变量在 main 函数作用域内管理，并直接传递给清理函数。
_app_services_for_cleanup: Optional[AppServices] = None

# --- 全局异常处理 ---
def handle_exception(exc_type, exc_value, exc_traceback):
    """全局异常处理器，用于记录错误并显示消息框。"""
    error_msg_detail = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    print(f"未处理的异常:\n{error_msg_detail}", file=sys.stderr)

    try:
        title = tr("unhandled_exception_title") if '_translations_loaded' in globals() and _translations_loaded else "Unhandled Exception"
        msg = f"发生意外的关键错误:\n\n{exc_value}\n\nPlease report this issue."

        # 确保QApplication实例存在
        app = QApplication.instance() or QApplication([])
        QMessageBox.critical(None, title, msg)
    except Exception as e:
        print(f"显示异常消息框时出错: {e}", file=sys.stderr)
        if os.name == 'nt':
            try:
                # 如果Qt消息框失败，回退到Windows原生消息框
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

    # 1. 关闭 AppServices (处理所有后端清理)
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

    # 2. 释放互斥锁和共享内存
    print("正在释放互斥锁和共享内存...")
    release_mutex()
    print("互斥锁和共享内存已释放。")

    print("清理完成。")

# --- 主函数 ---
def main():
    """主应用函数。"""
    global _app_services_for_cleanup

    # 注册全局异常处理器和退出清理函数
    sys.excepthook = handle_exception
    atexit.register(perform_cleanup)

    # --- 初始化核心服务 ---
    # 1. 创建路径管理器，这是所有路径的唯一来源
    path_manager = PathManager(base_dir=BASE_DIR)

    # 2. 加载翻译文件
    load_translations(path_manager.languages)

    # 3. Windows平台特定检查
    if os.name == 'nt':
        # 1. 检查管理员权限
        if not is_admin():
            run_as_admin(BASE_DIR)
            sys.exit(1)
        
        # 2. 检查是否已有实例在运行
        # 传递 is_task_launch 参数，以决定发送哪个命令
        is_task_launch = STARTUP_ARG_MINIMIZED in sys.argv
        if not check_single_instance(is_task_launch=is_task_launch):
            print("另一个实例正在运行。已发送命令，本实例将退出。")
            sys.exit(0)

    # 初始化Qt应用
    QCoreApplication.setOrganizationName(APP_ORGANIZATION_NAME)
    QCoreApplication.setApplicationName(APP_INTERNAL_NAME)
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.aboutToQuit.connect(perform_cleanup)

    # --- 初始化各层 ---
    try:
        # 【修复】调整了初始化顺序以解决启动时控制无效的问题
        # 1. 创建状态和管理器实例
        app_state = AppState(path_manager=path_manager)
        profile_manager = ProfileManager(app_state=app_state)
        settings_manager = SettingsManager(app_state=app_state, profile_manager=profile_manager)
        
        # 2. 创建 AppServices，它会立即开始监听 AppState 的变化
        app_services = AppServices(state=app_state)
        _app_services_for_cleanup = app_services

        # 3. **关键修复**：在加载任何配置文件之前，必须先初始化WMI接口。
        #    这确保了当 load_config() 触发信号时，AppServices 能够成功执行硬件命令。
        if not app_services.initialize_wmi():
            error_title = tr("wmi_init_error_title")
            error_text = app_state.get_controller_status_message()
            QMessageBox.critical(None, error_title, error_text)
            sys.exit(1)

        # 4. 现在可以安全地加载配置了。
        #    这将设置初始配置文件名，触发 active_profile_changed 信号，
        #    AppServices 会捕获此信号并正确应用所有初始硬件设置。
        profile_manager.load_config()
        set_language(app_state.get_language())
        
        # 5. 创建主窗口
        start_minimized = STARTUP_ARG_MINIMIZED in sys.argv
        main_window = MainWindow(
            app_services=app_services, 
            state=app_state,
            profile_manager=profile_manager,
            settings_manager=settings_manager,
            start_minimized=start_minimized
        )

        # 6. 将主窗口句柄写入共享内存
        if os.name == 'nt':
            main_window.window_initialized_signal.connect(write_hwnd_to_shared_memory)

    except Exception as init_error:
        handle_exception(type(init_error), init_error, init_error.__traceback__)
        sys.exit(1)

    # --- 启动Qt事件循环 ---
    print(f"启动 {APP_NAME} 事件循环...")
    exit_code = app.exec()
    print(f"应用事件循环结束，退出代码: {exit_code}")
    sys.exit(exit_code)


if __name__ == "__main__":
    main()