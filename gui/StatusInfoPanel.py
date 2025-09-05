# -*- coding: utf-8 -*-
"""
状态信息面板QFrame - 一个自包含的视图组件。
该面板通过直接连接到AppState的信号来响应式地更新其内容。
"""
from .qt import *
from core.state import AppState, ProfileState
from tools.localization import tr
from config.settings import (
    TEMP_READ_ERROR_VALUE, RPM_READ_ERROR_VALUE,
    FAN_MODE_AUTO, FAN_MODE_CUSTOM, CHARGE_POLICY_CUSTOM
)

class StatusInfoPanel(QFrame):
    """显示系统状态的自包含视图组件。"""
    def __init__(self, state: AppState, parent=None):
        super().__init__(parent)
        self.state = state
        self.setObjectName("infoFrame")
        self._init_ui()
        self._connect_signals()

        # 初始状态设置 - 状态面板应始终启用
        self.setEnabled(True)
        self._update_all_displays()

    def _init_ui(self):
        """创建并布局此面板的UI控件。"""
        layout = QGridLayout(self)
        layout.setContentsMargins(10, 5, 10, 10); layout.setSpacing(10)
        
        self.cpu_temp_label = QLabel(tr("cpu_temp_label"))
        self.cpu_temp_value = QLabel()
        self.gpu_temp_label = QLabel(tr("gpu_temp_label"))
        self.gpu_temp_value = QLabel()
        self.cpu_fan_rpm_label = QLabel(tr("cpu_fan_rpm_label"))
        self.cpu_fan_rpm_value = QLabel()
        self.gpu_fan_rpm_label = QLabel(tr("gpu_fan_rpm_label"))
        self.gpu_fan_rpm_value = QLabel()
        self.applied_target_label = QLabel(tr("applied_target_label"))
        self.applied_target_value = QLabel()
        self.battery_info_label = QLabel(tr("battery_info_label"))
        self.battery_info_value = QLabel()

        layout.addWidget(self.cpu_temp_label, 0, 0); layout.addWidget(self.cpu_temp_value, 0, 1)
        layout.addWidget(self.gpu_temp_label, 0, 2); layout.addWidget(self.gpu_temp_value, 0, 3)
        layout.addWidget(self.cpu_fan_rpm_label, 1, 0); layout.addWidget(self.cpu_fan_rpm_value, 1, 1)
        layout.addWidget(self.gpu_fan_rpm_label, 1, 2); layout.addWidget(self.gpu_fan_rpm_value, 1, 3)
        layout.addWidget(self.applied_target_label, 2, 0); layout.addWidget(self.applied_target_value, 2, 1)
        layout.addWidget(self.battery_info_label, 2, 2); layout.addWidget(self.battery_info_value, 2, 3)
        
        layout.setColumnStretch(1, 1); layout.setColumnStretch(3, 1)

    def _connect_signals(self):
        """将UI更新槽函数连接到AppState的特定信号。"""
        # 【修复】移除对 is_fan_control_panel_enabled_changed 的监听，状态面板不应被禁用。
        
        # 连接传感器信号
        self.state.cpu_temp_changed.connect(self._update_cpu_temp)
        self.state.gpu_temp_changed.connect(self._update_gpu_temp)
        self.state.cpu_fan_rpm_changed.connect(self._update_cpu_rpm)
        self.state.gpu_fan_rpm_changed.connect(self._update_gpu_rpm)

        # 连接需要组合逻辑的信号
        self.state.active_profile_changed.connect(self._update_fan_and_battery_display)
        self.state.applied_fan_mode_changed.connect(self._update_fan_and_battery_display)
        self.state.applied_fan_speed_percent_changed.connect(self._update_fan_and_battery_display)
        self.state.auto_fan_target_speed_percent_changed.connect(self._update_fan_and_battery_display)
        self.state.applied_charge_policy_changed.connect(self._update_fan_and_battery_display)
        self.state.applied_charge_threshold_changed.connect(self._update_fan_and_battery_display)

    def _update_all_displays(self):
        """一次性更新所有显示的值，用于初始化和语言切换。"""
        self._update_cpu_temp(self.state.get_cpu_temp())
        self._update_gpu_temp(self.state.get_gpu_temp())
        self._update_cpu_rpm(self.state.get_cpu_fan_rpm())
        self._update_gpu_rpm(self.state.get_gpu_fan_rpm())
        self._update_fan_and_battery_display()

    @Slot(float)
    def _update_cpu_temp(self, temp: float):
        self.cpu_temp_value.setText(f"{temp:.1f}{tr('celsius_unit')}" if temp != TEMP_READ_ERROR_VALUE else tr("temp_error"))

    @Slot(float)
    def _update_gpu_temp(self, temp: float):
        self.gpu_temp_value.setText(f"{temp:.1f}{tr('celsius_unit')}" if temp != TEMP_READ_ERROR_VALUE else tr("temp_error"))

    @Slot(int)
    def _update_cpu_rpm(self, rpm: int):
        self.cpu_fan_rpm_value.setText(f"{rpm}{tr('rpm_unit')}" if rpm != RPM_READ_ERROR_VALUE else tr("rpm_error"))

    @Slot(int)
    def _update_gpu_rpm(self, rpm: int):
        self.gpu_fan_rpm_value.setText(f"{rpm}{tr('rpm_unit')}" if rpm != RPM_READ_ERROR_VALUE else tr("rpm_error"))

    @Slot()
    def _update_fan_and_battery_display(self):
        """更新风扇和电池的组合显示文本。"""
        fan_mode = self.state.get_applied_fan_mode()
        if fan_mode == FAN_MODE_AUTO:
            fan_display = tr("fan_display_auto_format", applied=self.state.get_applied_fan_speed_percent(), target=self.state.get_auto_fan_target_speed_percent())
        elif fan_mode == FAN_MODE_CUSTOM:
            fan_display = f"{self.state.get_applied_fan_speed_percent()}{tr('percent_unit')}"
        else:
            fan_display = tr('mode_bios')
        self.applied_target_value.setText(fan_display)

        policy_str = tr("mode_custom") if self.state.get_applied_charge_policy() == CHARGE_POLICY_CUSTOM else tr("mode_bios")
        limit_str = f"{self.state.get_applied_charge_threshold()}{tr('percent_unit')}"
        self.battery_info_value.setText(tr("battery_display_format", policy=policy_str, limit=limit_str))

    def retranslate_ui(self):
        """重新翻译面板中所有用户可见的文本。"""
        self.cpu_temp_label.setText(tr("cpu_temp_label"))
        self.gpu_temp_label.setText(tr("gpu_temp_label"))
        self.cpu_fan_rpm_label.setText(tr("cpu_fan_rpm_label"))
        self.gpu_fan_rpm_label.setText(tr("gpu_fan_rpm_label"))
        self.applied_target_label.setText(tr("applied_target_label"))
        self.battery_info_label.setText(tr("battery_info_label"))
        self._update_all_displays()