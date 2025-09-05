# -*- coding: utf-8 -*-
"""
负责管理与配置文件无关的全局应用设置。
"""
import os
import sys
from typing import Optional

from gui.qt import QObject, Signal
from .state import AppState
from .profile_manager import ProfileManager
from tools.task_scheduler import create_startup_task, delete_startup_task

class SettingsManager(QObject):
    """管理全局应用设置的类。"""
    
    def __init__(self, app_state: AppState, profile_manager: ProfileManager, parent: Optional[QObject] = None):
        """
        初始化SettingsManager。
        
        Args:
            app_state: 对应用全局状态对象的引用。
            profile_manager: ProfileManager实例，用于触发保存操作。
        """
        super().__init__(parent)
        self.state = app_state
        self.profile_manager = profile_manager

    def set_language(self, lang_code: str):
        """设置应用语言并保存配置。"""
        if self.state.get_language() != lang_code:
            self.state.set_language(lang_code)
            self.profile_manager.save_config()

    def set_start_on_boot(self, enabled: bool):
        """启用或禁用开机启动任务。"""
        if os.name != 'nt': return
        try:
            if enabled:
                create_startup_task(self.state.paths)
            else:
                delete_startup_task()
            
            if self.state.get_start_on_boot() != enabled:
                self.state.set_start_on_boot(enabled)
                self.profile_manager.save_config()

        except Exception as e:
            print(f"设置开机启动时出错: {e}", file=sys.stderr)
            # 如果失败，将UI状态恢复
            self.state.set_start_on_boot(not enabled)
            
    def set_window_geometry(self, geometry: str):
        """设置窗口几何信息并保存配置。"""
        if self.state.window_geometry != geometry:
            self.state.window_geometry = geometry
            self.profile_manager.save_config()

    def set_active_curve_type(self, curve_type: str):
        """设置在UI中显示的活动曲线类型。"""
        self.state.set_active_curve_type(curve_type)