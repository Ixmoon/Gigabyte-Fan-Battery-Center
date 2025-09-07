# -*- coding: utf-8 -*-
"""
提供一个中心化的服务层(AppServices)，将后端逻辑与UI解耦。
【最终优化】增加了优雅退出逻辑，在程序关闭时将风扇交还BIOS控制，并为崩溃安全机制记录当前风扇模式。
"""

import os
import sys
import time
import math
from typing import Optional, List, Any, Callable

from gui.qt import QObject, Slot, QTimer

from .wmi_interface import WMIInterface, WMIError
from .auto_temp_controller import AutoTemperatureController
from .state import AppState, ProfileState
from tools.localization import tr
from config.settings import (
    FAN_MODE_BIOS, FAN_MODE_AUTO, FAN_MODE_CUSTOM,
    CHARGE_POLICY_CUSTOM, BATTERY_POLICY_CODES, BATTERY_CODE_POLICIES, MIN_FAN_PERCENT,
    MAX_FAN_PERCENT, INIT_APPLIED_PERCENTAGE, TEMP_READ_ERROR_VALUE,
    SET_CUSTOM_FAN_STATUS, SET_SUPER_QUIET, SET_AUTO_FAN_STATUS,
    SET_STEP_FAN_STATUS, SET_CUSTOM_FAN_SPEED, SET_GPU_FAN_DUTY,
    SET_CHARGE_POLICY, SET_CHARGE_STOP
)

FanTable = List[List[int]]

class AppServices(QObject):
    """中心化服务层，管理所有后端控制器并响应应用状态的变化。"""

    def __init__(self, state: AppState, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._is_shutting_down = False
        self.state = state
        self._current_profile: Optional[ProfileState] = None
        self.wmi_interface = WMIInterface()
        self.auto_temp_controller = AutoTemperatureController()

        self.controller_timer = QTimer(self)
        self.controller_timer.timeout.connect(self._perform_control_cycle)

        self.state.set_controller_status_message(tr("initializing"))
        self._is_ui_visible: bool = False
        
        # 【新增】为崩溃安全机制定义状态文件路径
        self._last_mode_file_path = os.path.join(self.state.paths.base_dir, 'last_mode.state')
        
        self._connect_to_state_signals()

    def _connect_to_state_signals(self):
        self.state.active_profile_changed.connect(self._on_active_profile_changed)

    @Slot(ProfileState)
    def _on_active_profile_changed(self, profile: Optional[ProfileState]):
        if self._current_profile:
            try:
                self._current_profile.fan_mode_changed.disconnect(self.set_fan_mode)
                self._current_profile.custom_fan_speed_changed.disconnect(self.set_custom_fan_speed)
                self._current_profile.battery_charge_policy_changed.disconnect(self.set_battery_charge_policy)
                self._current_profile.battery_charge_threshold_changed.disconnect(self.set_battery_charge_threshold)
                self._current_profile.cpu_fan_table_changed.disconnect(self._update_controller_curves)
                self._current_profile.gpu_fan_table_changed.disconnect(self._update_controller_curves)
                self._current_profile.appearance_changed.disconnect(self._update_controller_settings)
            except (AttributeError, RuntimeError): pass

        self._current_profile = profile
        if not profile:
            self.controller_timer.stop()
            return

        profile.fan_mode_changed.connect(self.set_fan_mode)
        profile.custom_fan_speed_changed.connect(self.set_custom_fan_speed)
        profile.battery_charge_policy_changed.connect(self.set_battery_charge_policy)
        profile.battery_charge_threshold_changed.connect(self.set_battery_charge_threshold)
        profile.cpu_fan_table_changed.connect(self._update_controller_curves)
        profile.gpu_fan_table_changed.connect(self._update_controller_curves)
        profile.appearance_changed.connect(self._update_controller_settings)
        
        self._update_controller_curves()
        self._update_controller_settings()
        self.set_fan_mode(profile.get_fan_mode())
        self.set_battery_charge_policy(profile.get_battery_charge_policy())

    def _update_controller_curves(self):
        if self._current_profile:
            self.auto_temp_controller.update_curves(
                self._current_profile.get_cpu_fan_table(),
                self._current_profile.get_gpu_fan_table()
            )

    def _update_controller_settings(self):
        if self._current_profile:
            self.auto_temp_controller.update_auto_settings(self._current_profile)
            
            controller_interval = self._current_profile.get_value('controller_update_interval_ms')
            if self.controller_timer.interval() != controller_interval:
                self.controller_timer.setInterval(controller_interval)

    def initialize_wmi(self) -> bool:
        if not self.wmi_interface.start():
            init_error = self.wmi_interface.get_initialization_error()
            error_msg = tr("wmi_init_error_msg", error=str(init_error))
            self.state.set_controller_status_message(error_msg)
            return False
        self.state.set_controller_status_message("")
        return True

    def shutdown(self):
        """【优化】执行优雅关机程序。"""
        if self._is_shutting_down: return
        self._is_shutting_down = True
        self.controller_timer.stop()
        
        # 【新增】如果软件正在控制风扇，则在退出前将其交还给BIOS
        if self.state.get_applied_fan_mode() != FAN_MODE_BIOS:
            print("优雅退出：将风扇控制权交还给BIOS...")
            try:
                self._configure_bios_fan_control()
                print("优雅退出：风扇已设置为BIOS模式。")
            except WMIError as e:
                print(f"优雅退出：设置BIOS风扇模式失败: {e}", file=sys.stderr)
        
        if self.wmi_interface:
            self.wmi_interface.stop()

    def _configure_software_fan_control(self):
        """执行启用软件风扇控制所需的WMI命令序列。"""
        self.wmi_interface.execute_method(SET_CUSTOM_FAN_STATUS, Data=1.0)
        self.wmi_interface.execute_method(SET_SUPER_QUIET, Data=0.0)
        self.wmi_interface.execute_method(SET_AUTO_FAN_STATUS, Data=0.0)
        self.wmi_interface.execute_method(SET_STEP_FAN_STATUS, Data=0.0)

    def _configure_bios_fan_control(self):
        """执行将风扇控制权交还给BIOS所需的WMI命令序列。"""
        self.wmi_interface.execute_method(SET_AUTO_FAN_STATUS, Data=1.0)
        self.wmi_interface.execute_method(SET_CUSTOM_FAN_STATUS, Data=0.0)

    def _apply_fan_speed_percent(self, percent: int) -> bool:
        """将风扇速度百分比应用到硬件。"""
        percent_clamped = max(MIN_FAN_PERCENT, min(MAX_FAN_PERCENT, percent))
        raw_speed = float(math.ceil((percent_clamped / 100.0) * 229.0))
        
        self.wmi_interface.execute_method(SET_CUSTOM_FAN_SPEED, Data=raw_speed)
        self.wmi_interface.execute_method(SET_GPU_FAN_DUTY, Data=raw_speed)
        self.state.set_applied_fan_speed_percent(percent_clamped)
        return True
        
    def _write_last_mode_state(self, mode: str):
        """【新增】将当前风扇模式写入状态文件，用于崩溃恢复。"""
        try:
            with open(self._last_mode_file_path, 'w') as f:
                f.write(mode)
        except IOError as e:
            print(f"警告：无法写入 'last_mode.state' 文件: {e}", file=sys.stderr)

    @Slot(str)
    def set_fan_mode(self, mode: str):
        """设置风扇控制模式。这是核心业务逻辑之一。"""
        if not self._current_profile: return

        try:
            if mode == FAN_MODE_AUTO:
                if not self.controller_timer.isActive(): self.controller_timer.start()
                self._configure_software_fan_control()
                self.auto_temp_controller.reset_state()
                self.state.set_applied_fan_speed_percent(INIT_APPLIED_PERCENTAGE)
            else: 
                if self.controller_timer.isActive(): self.controller_timer.stop()
                if mode == FAN_MODE_CUSTOM:
                    self._configure_software_fan_control()
                    self._apply_fan_speed_percent(self._current_profile.get_custom_fan_speed())
                elif mode == FAN_MODE_BIOS:
                    self._configure_bios_fan_control()
                    self.state.set_applied_fan_speed_percent(INIT_APPLIED_PERCENTAGE)
            
            self.state.set_applied_fan_mode(mode)
            self.state.set_is_fan_control_panel_enabled((mode != FAN_MODE_BIOS))
            
            # 【新增】成功应用模式后，记录状态
            self._write_last_mode_state(mode)
        
        except WMIError as e:
            print(f"WMI操作在 'set_fan_mode' 中失败: {e}", file=sys.stderr)
            self.state.set_controller_status_message(tr("wmi_error"))
            self.state.set_applied_fan_mode(FAN_MODE_BIOS)
            # 如果设置失败，也记录为BIOS模式
            self._write_last_mode_state(FAN_MODE_BIOS)

    @Slot(int)
    def set_custom_fan_speed(self, speed: int):
        """仅在自定义模式下应用风扇速度。"""
        if not self._current_profile or self.state.get_applied_fan_mode() != FAN_MODE_CUSTOM: return
        try:
            self._apply_fan_speed_percent(speed)
        except WMIError as e:
            print(f"WMI操作在 'set_custom_fan_speed' 中失败: {e}", file=sys.stderr)
            self.state.set_controller_status_message(tr("wmi_error"))

    @Slot(str)
    def set_battery_charge_policy(self, policy_name: str):
        """设置电池充电策略。"""
        if not self._current_profile: return
        
        try:
            policy_code = BATTERY_POLICY_CODES.get(policy_name)
            if policy_code is None: return
            
            self.wmi_interface.execute_method(SET_CHARGE_POLICY, Data=float(policy_code))
            
            if policy_name == CHARGE_POLICY_CUSTOM:
                self.set_battery_charge_threshold(
                    self._current_profile.get_battery_charge_threshold(), 
                    force_apply=True
                )
            
            time.sleep(0.5) 
            self.perform_full_status_update()
        except WMIError as e:
            print(f"WMI操作在 'set_battery_charge_policy' 中失败: {e}", file=sys.stderr)
            self.state.set_controller_status_message(tr("wmi_error"))

    @Slot(int)
    def set_battery_charge_threshold(self, threshold: int, force_apply: bool = False):
        """设置电池充电阈值。"""
        if not force_apply and (not self._current_profile or self.state.get_applied_charge_policy() != CHARGE_POLICY_CUSTOM):
            return
        try:
            self.wmi_interface.execute_method(SET_CHARGE_STOP, Data=float(threshold))
        except WMIError as e:
            print(f"WMI操作在 'set_battery_charge_threshold' 中失败: {e}", file=sys.stderr)
            self.state.set_controller_status_message(tr("wmi_error"))

    @Slot()
    def _perform_control_cycle(self):
        """自动温控的核心循环。"""
        if self._is_shutting_down or not self.wmi_interface.is_running: return
        if self.state.get_applied_fan_mode() != FAN_MODE_AUTO: return

        try:
            temps = self.wmi_interface.get_temperatures_sync()
            cpu_temp = temps.get('cpu_temp', TEMP_READ_ERROR_VALUE)
            gpu_temp = temps.get('gpu_temp', TEMP_READ_ERROR_VALUE)
            
            if self._is_ui_visible:
                self.state.set_cpu_temp(cpu_temp)
                self.state.set_gpu_temp(gpu_temp)

            if cpu_temp != TEMP_READ_ERROR_VALUE or gpu_temp != TEMP_READ_ERROR_VALUE:
                speed_to_apply = self.auto_temp_controller.perform_adjustment_step(
                    current_applied_speed=self.state.get_applied_fan_speed_percent(),
                    cpu_temp=cpu_temp,
                    gpu_temp=gpu_temp
                )
                if speed_to_apply is not None:
                    self._apply_fan_speed_percent(speed_to_apply)
            
            if self._is_ui_visible:
                self.state.set_auto_fan_target_speed_percent(self.auto_temp_controller.get_last_theoretical_target())
        except WMIError as e:
            print(f"WMI操作在 '_perform_control_cycle' 中失败: {e}", file=sys.stderr)
            if self._is_ui_visible:
                self.state.set_cpu_temp(TEMP_READ_ERROR_VALUE)
                self.state.set_gpu_temp(TEMP_READ_ERROR_VALUE)

    @Slot()
    def on_gui_tick(self):
        """由UI定时器触发，用于刷新UI显示的传感器数据。"""
        if self._is_shutting_down or not self.wmi_interface.is_running or not self._is_ui_visible:
            return
        
        self.wmi_interface.request_core_sensor_poll()
        sensor_data = self.wmi_interface.get_latest_core_sensor_data()
        self._update_state_from_sensor_data(sensor_data)

    @Slot()
    def perform_full_status_update(self):
        """执行一次全局的、阻塞式的WMI查询。"""
        try:
            sensor_data = self.wmi_interface.get_all_sensors_sync()
            self._update_state_from_sensor_data(sensor_data)
        except WMIError as e:
            print(f"WMI操作在 'perform_full_status_update' 中失败: {e}", file=sys.stderr)
            self.state.set_controller_status_message(tr("wmi_error"))

    def _update_state_from_sensor_data(self, sensor_data: dict):
        """使用反射机制，并正确处理特殊映射，用从WMI获取的数据更新AppState。"""
        if not sensor_data: return
        
        key_map = {
            'charge_policy': 'applied_charge_policy',
            'charge_threshold': 'applied_charge_threshold'
        }

        for key, value in sensor_data.items():
            state_key = key_map.get(key, key)
            setter_name = f"set_{state_key}"
            
            if hasattr(self.state, setter_name):
                if state_key == 'applied_charge_policy':
                    value = BATTERY_CODE_POLICIES.get(value, "err")
                getattr(self.state, setter_name)(value)

    def set_ui_visibility(self, is_visible: bool):
        """当UI可见性变化时调用。"""
        self._is_ui_visible = is_visible
        if is_visible:
            self.perform_full_status_update()