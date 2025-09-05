# -*- coding: utf-8 -*-
"""
提供一个中心化的服务层(AppServices)，将后端逻辑与UI解耦。
此类作为协调器，通过监听响应式状态对象(AppState)的变化来与硬件接口(WMIInterface)交互。
"""

import os
import sys
import time
import math
from typing import Optional, List, Any, Callable
from functools import wraps

from gui.qt import QObject, Slot, QTimer

from .wmi_interface import WMIInterface, WMIError
from .auto_temp_controller import AutoTemperatureController
from .state import AppState, ProfileState
from tools.localization import tr
from config.settings import (
    FAN_MODE_BIOS, FAN_MODE_AUTO, FAN_MODE_CUSTOM,
    CHARGE_POLICY_CUSTOM, BATTERY_POLICY_CODES, BATTERY_CODE_POLICIES, MIN_FAN_PERCENT,
    MAX_FAN_PERCENT, INIT_APPLIED_PERCENTAGE, TEMP_READ_ERROR_VALUE
)

FanTable = List[List[int]]

def _handle_wmi_errors(func: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(func)
    def wrapper(self: 'AppServices', *args: Any, **kwargs: Any) -> Any:
        try:
            return func(self, *args, **kwargs)
        except WMIError as e:
            print(f"WMI操作在 '{func.__name__}' 中失败: {e}", file=sys.stderr)
            self.state.set_controller_status_message(tr("wmi_error"))
            return_annotation = func.__annotations__.get('return')
            if return_annotation == bool:
                return False
            return None
    return wrapper

class AppServices(QObject):
    """中心化服务层，管理所有后端控制器并响应应用状态的变化。"""

    def __init__(self, state: AppState, base_dir: str, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._is_shutting_down = False
        self.base_dir = base_dir

        self.state = state
        self._current_profile: Optional[ProfileState] = None
        self.wmi_interface = WMIInterface()
        self.auto_temp_controller = AutoTemperatureController()

        self.controller_timer = QTimer(self)
        self.controller_timer.timeout.connect(self._perform_control_cycle)

        self.state.set_controller_status_message(tr("initializing"))
        self._is_ui_visible: bool = False
        
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
            new_interval = self._current_profile.get_value('controller_update_interval_ms')
            if self.controller_timer.interval() != new_interval:
                self.controller_timer.setInterval(new_interval)

    def initialize_wmi(self) -> bool:
        if not self.wmi_interface.start():
            init_error = self.wmi_interface.get_initialization_error()
            error_msg = tr("wmi_init_error_msg", error=str(init_error))
            self.state.set_controller_status_message(error_msg)
            return False
        self.state.set_controller_status_message("")
        return True

    def shutdown(self):
        if self._is_shutting_down: return
        self._is_shutting_down = True
        self.controller_timer.stop()
        if self.wmi_interface:
            self.wmi_interface.stop()
        
    def _percent_to_raw(self, percent: int) -> float:
        percent = max(MIN_FAN_PERCENT, min(MAX_FAN_PERCENT, percent))
        return float(math.ceil((percent / 100.0) * 229.0))

    @_handle_wmi_errors
    def _apply_fan_speed_percent(self, percent: int) -> bool:
        percent_clamped = max(MIN_FAN_PERCENT, min(MAX_FAN_PERCENT, percent))
        raw_speed = self._percent_to_raw(percent_clamped)
        if self.wmi_interface.set_fan_speed_raw(raw_speed):
            self.state.set_applied_fan_speed_percent(percent_clamped)
            return True
        return False
        
    @Slot(str)
    @_handle_wmi_errors
    def set_fan_mode(self, mode: str) -> bool:
        if not self._current_profile: return False

        if mode == FAN_MODE_AUTO:
            if not self.controller_timer.isActive(): self.controller_timer.start()
        else:
            if self.controller_timer.isActive(): self.controller_timer.stop()

        success = False
        if mode == FAN_MODE_AUTO:
            if self.wmi_interface.configure_custom_fan_control():
                self.auto_temp_controller.reset_state()
                self.state.set_applied_fan_speed_percent(INIT_APPLIED_PERCENTAGE)
                success = True
        elif mode == FAN_MODE_CUSTOM:
            if self.wmi_interface.configure_custom_fan_control():
                success = self._apply_fan_speed_percent(self._current_profile.get_custom_fan_speed())
        elif mode == FAN_MODE_BIOS:
            if self.wmi_interface.configure_bios_fan_control():
                self.state.set_applied_fan_speed_percent(INIT_APPLIED_PERCENTAGE)
                success = True
        
        if success:
            self.state.set_applied_fan_mode(mode)
            # 【修复】现在只设置与风扇相关的面板启用状态
            self.state.set_is_fan_control_panel_enabled((mode != FAN_MODE_BIOS))
        else:
            self.state.set_applied_fan_mode(FAN_MODE_BIOS)
        return success

    @Slot(int)
    @_handle_wmi_errors
    def set_custom_fan_speed(self, speed: int) -> bool:
        if not self._current_profile or self.state.get_applied_fan_mode() != FAN_MODE_CUSTOM: return True
        return self._apply_fan_speed_percent(speed)

    @Slot(str)
    @_handle_wmi_errors
    def set_battery_charge_policy(self, policy_name: str) -> bool:
        if not self._current_profile: return False
        policy_code = BATTERY_POLICY_CODES.get(policy_name)
        if policy_code is None: return False
        
        if self.wmi_interface.set_battery_charge_policy(policy_code):
            if policy_name == CHARGE_POLICY_CUSTOM:
                self.set_battery_charge_threshold(
                    self._current_profile.get_battery_charge_threshold(), 
                    force_apply=True
                )
            time.sleep(0.5)
            self.perform_full_status_update()
            return True
        return False

    @Slot(int)
    @_handle_wmi_errors
    def set_battery_charge_threshold(self, threshold: int, force_apply: bool = False) -> bool:
        if not force_apply and (not self._current_profile or self.state.get_applied_charge_policy() != CHARGE_POLICY_CUSTOM):
            return True
        return self.wmi_interface.set_battery_charge_threshold(threshold)

    @Slot()
    def _perform_control_cycle(self):
        if self._is_shutting_down or not self.wmi_interface.is_running: return
        if self.state.get_applied_fan_mode() != FAN_MODE_AUTO: return

        cpu_temp = self.wmi_interface.get_cpu_temperature()
        gpu_temp = self.wmi_interface.get_gpu_temperature()
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
        
        self.state.set_auto_fan_target_speed_percent(self.auto_temp_controller.get_last_theoretical_target())

    @Slot()
    def on_gui_tick(self):
        if self._is_shutting_down or not self.wmi_interface.is_running or not self._is_ui_visible:
            return
        if self.state.get_applied_fan_mode() == FAN_MODE_AUTO:
            self._update_non_temp_sensors()
        else:
            self.perform_full_status_update()

    def perform_full_status_update(self):
        sensor_data = self.wmi_interface.get_all_sensors()
        self._update_state_from_sensor_data(sensor_data)

    def _update_non_temp_sensors(self):
        sensor_data = self.wmi_interface.get_non_temp_sensors()
        self._update_state_from_sensor_data(sensor_data)

    def _update_state_from_sensor_data(self, sensor_data: dict):
        if 'cpu_temp' in sensor_data: self.state.set_cpu_temp(sensor_data['cpu_temp'])
        if 'gpu_temp' in sensor_data: self.state.set_gpu_temp(sensor_data['gpu_temp'])
        if 'fan1_rpm' in sensor_data: self.state.set_cpu_fan_rpm(sensor_data['fan1_rpm'])
        if 'fan2_rpm' in sensor_data: self.state.set_gpu_fan_rpm(sensor_data['fan2_rpm'])
        if 'charge_policy' in sensor_data:
            self.state.set_applied_charge_policy(BATTERY_CODE_POLICIES.get(sensor_data['charge_policy'], "err"))
        if 'charge_threshold' in sensor_data:
            self.state.set_applied_charge_threshold(sensor_data['charge_threshold'])

    def set_ui_visibility(self, is_visible: bool):
        self._is_ui_visible = is_visible
        if is_visible:
            self.on_gui_tick()