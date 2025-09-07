# -*- coding: utf-8 -*-
"""
提供一个中心化的服务层(AppServices)，将后端逻辑与UI解耦。
此类作为协调器，通过监听响应式状态对象(AppState)的变化来与硬件接口(WMIInterface)交互。
【重构】此类现在是所有硬件控制业务逻辑的唯一中心，直接调用扁平化的WMI接口。
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
    MAX_FAN_PERCENT, INIT_APPLIED_PERCENTAGE, TEMP_READ_ERROR_VALUE,
    WMI_SET_CUSTOM_FAN_STATUS, WMI_SET_SUPER_QUIET, WMI_SET_AUTO_FAN_STATUS,
    WMI_SET_STEP_FAN_STATUS, WMI_SET_CUSTOM_FAN_SPEED, WMI_SET_GPU_FAN_DUTY,
    WMI_SET_CHARGE_POLICY, WMI_SET_CHARGE_STOP
)

FanTable = List[List[int]]

def _handle_wmi_errors(func: Callable[..., Any]) -> Callable[..., Any]:
    """装饰器，用于捕获WMIError并更新控制器状态，提供统一的错误处理。"""
    @wraps(func)
    def wrapper(self: 'AppServices', *args: Any, **kwargs: Any) -> Any:
        try:
            return func(self, *args, **kwargs)
        except WMIError as e:
            print(f"WMI操作在 '{func.__name__}' 中失败: {e}", file=sys.stderr)
            self.state.set_controller_status_message(tr("wmi_error"))
            # 根据函数预期的返回类型返回一个安全的默认值
            return_annotation = func.__annotations__.get('return')
            if return_annotation == bool:
                return False
            return None
    return wrapper

class AppServices(QObject):
    """中心化服务层，管理所有后端控制器并响应应用状态的变化。"""

    def __init__(self, state: AppState, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._is_shutting_down = False
        self.state = state
        self._current_profile: Optional[ProfileState] = None
        self.wmi_interface = WMIInterface()
        self.auto_temp_controller = AutoTemperatureController()

        # 用于自动温控模式的定时器
        self.controller_timer = QTimer(self)
        self.controller_timer.timeout.connect(self._perform_control_cycle)

        self.state.set_controller_status_message(tr("initializing"))
        self._is_ui_visible: bool = False
        
        self._connect_to_state_signals()

    def _connect_to_state_signals(self):
        """连接到AppState中的核心信号。"""
        self.state.active_profile_changed.connect(self._on_active_profile_changed)

    @Slot(ProfileState)
    def _on_active_profile_changed(self, profile: Optional[ProfileState]):
        """当活动配置文件更改时，重新连接所有与配置文件相关的信号。"""
        # 断开旧配置文件的连接
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

        # 连接新配置文件的信号
        profile.fan_mode_changed.connect(self.set_fan_mode)
        profile.custom_fan_speed_changed.connect(self.set_custom_fan_speed)
        profile.battery_charge_policy_changed.connect(self.set_battery_charge_policy)
        profile.battery_charge_threshold_changed.connect(self.set_battery_charge_threshold)
        profile.cpu_fan_table_changed.connect(self._update_controller_curves)
        profile.gpu_fan_table_changed.connect(self._update_controller_curves)
        profile.appearance_changed.connect(self._update_controller_settings)
        
        # 立即应用新配置文件的设置
        self._update_controller_curves()
        self._update_controller_settings()
        self.set_fan_mode(profile.get_fan_mode())
        self.set_battery_charge_policy(profile.get_battery_charge_policy())

    def _update_controller_curves(self):
        """从当前配置文件更新自动温度控制器中的风扇曲线。"""
        if self._current_profile:
            self.auto_temp_controller.update_curves(
                self._current_profile.get_cpu_fan_table(),
                self._current_profile.get_gpu_fan_table()
            )

    def _update_controller_settings(self):
        """从当前配置文件更新自动温度控制器的控制参数（如迟滞、步长）。"""
        if self._current_profile:
            self.auto_temp_controller.update_auto_settings(self._current_profile)
            new_interval = self._current_profile.get_value('controller_update_interval_ms')
            if self.controller_timer.interval() != new_interval:
                self.controller_timer.setInterval(new_interval)

    def initialize_wmi(self) -> bool:
        """启动WMI接口并处理初始化错误。"""
        if not self.wmi_interface.start():
            init_error = self.wmi_interface.get_initialization_error()
            error_msg = tr("wmi_init_error_msg", error=str(init_error))
            self.state.set_controller_status_message(error_msg)
            return False
        self.state.set_controller_status_message("")
        return True

    def shutdown(self):
        """在应用关闭时，安全地停止所有后台服务。"""
        if self._is_shutting_down: return
        self._is_shutting_down = True
        self.controller_timer.stop()
        if self.wmi_interface:
            self.wmi_interface.stop()
        
    def _percent_to_raw(self, percent: int) -> float:
        """将风扇速度百分比转换为硬件所需的原始值 (0-229)。"""
        percent = max(MIN_FAN_PERCENT, min(MAX_FAN_PERCENT, percent))
        return float(math.ceil((percent / 100.0) * 229.0))

    @_handle_wmi_errors
    def _apply_fan_speed_percent(self, percent: int) -> bool:
        """将风扇速度百分比应用到硬件。"""
        percent_clamped = max(MIN_FAN_PERCENT, min(MAX_FAN_PERCENT, percent))
        raw_speed = self._percent_to_raw(percent_clamped)
        # 【重构】直接调用WMI方法
        self.wmi_interface.execute_method(WMI_SET_CUSTOM_FAN_SPEED, Data=raw_speed)
        self.wmi_interface.execute_method(WMI_SET_GPU_FAN_DUTY, Data=raw_speed)
        self.state.set_applied_fan_speed_percent(percent_clamped)
        return True
        
    @Slot(str)
    @_handle_wmi_errors
    def set_fan_mode(self, mode: str) -> bool:
        """
        设置风扇控制模式。这是核心业务逻辑之一。
        【重构】所有WMI调用序列现在都内聚在此方法中。
        """
        if not self._current_profile: return False

        # 根据模式启动或停止自动温控定时器
        if mode == FAN_MODE_AUTO:
            if not self.controller_timer.isActive(): self.controller_timer.start()
        else:
            if self.controller_timer.isActive(): self.controller_timer.stop()

        success = False
        if mode in [FAN_MODE_AUTO, FAN_MODE_CUSTOM]:
            # --- 切换到软件控制模式的WMI调用序列 ---
            self.wmi_interface.execute_method(WMI_SET_CUSTOM_FAN_STATUS, Data=1.0)
            self.wmi_interface.execute_method(WMI_SET_SUPER_QUIET, Data=0.0)
            self.wmi_interface.execute_method(WMI_SET_AUTO_FAN_STATUS, Data=0.0)
            self.wmi_interface.execute_method(WMI_SET_STEP_FAN_STATUS, Data=0.0)
            
            if mode == FAN_MODE_AUTO:
                self.auto_temp_controller.reset_state()
                self.state.set_applied_fan_speed_percent(INIT_APPLIED_PERCENTAGE)
            else: # FAN_MODE_CUSTOM
                self._apply_fan_speed_percent(self._current_profile.get_custom_fan_speed())
            success = True

        elif mode == FAN_MODE_BIOS:
            # --- 切换回BIOS控制模式的WMI调用序列 ---
            self.wmi_interface.execute_method(WMI_SET_AUTO_FAN_STATUS, Data=1.0)
            self.wmi_interface.execute_method(WMI_SET_CUSTOM_FAN_STATUS, Data=0.0)
            self.state.set_applied_fan_speed_percent(INIT_APPLIED_PERCENTAGE)
            success = True
        
        if success:
            self.state.set_applied_fan_mode(mode)
            self.state.set_is_fan_control_panel_enabled((mode != FAN_MODE_BIOS))
        else:
            self.state.set_applied_fan_mode(FAN_MODE_BIOS) # 失败时回退到安全状态
        return success

    @Slot(int)
    @_handle_wmi_errors
    def set_custom_fan_speed(self, speed: int) -> bool:
        """仅在自定义模式下应用风扇速度。"""
        if not self._current_profile or self.state.get_applied_fan_mode() != FAN_MODE_CUSTOM: return True
        return self._apply_fan_speed_percent(speed)

    @Slot(str)
    @_handle_wmi_errors
    def set_battery_charge_policy(self, policy_name: str) -> bool:
        """设置电池充电策略。"""
        if not self._current_profile: return False
        policy_code = BATTERY_POLICY_CODES.get(policy_name)
        if policy_code is None: return False
        
        # 【重构】直接调用WMI方法
        self.wmi_interface.execute_method(WMI_SET_CHARGE_POLICY, Data=float(policy_code))
        
        if policy_name == CHARGE_POLICY_CUSTOM:
            # 如果切换到自定义模式，立即应用阈值
            self.set_battery_charge_threshold(
                self._current_profile.get_battery_charge_threshold(), 
                force_apply=True
            )
        
        # 等待硬件响应后，执行一次全局状态刷新以获取最新状态
        time.sleep(0.5) 
        self.perform_full_status_update()
        return True

    @Slot(int)
    @_handle_wmi_errors
    def set_battery_charge_threshold(self, threshold: int, force_apply: bool = False) -> bool:
        """设置电池充电阈值。"""
        # 仅当强制应用或当前策略为自定义时才执行
        if not force_apply and (not self._current_profile or self.state.get_applied_charge_policy() != CHARGE_POLICY_CUSTOM):
            return True
        # 【重构】直接调用WMI方法
        return self.wmi_interface.execute_method(WMI_SET_CHARGE_STOP, Data=float(threshold))

    @Slot()
    def _perform_control_cycle(self):
        """自动温控的核心循环，由controller_timer触发。"""
        if self._is_shutting_down or not self.wmi_interface.is_running: return
        if self.state.get_applied_fan_mode() != FAN_MODE_AUTO: return

        # 【重构】调用专用的、仅获取温度的WMI方法，最小化开销
        temps = self.wmi_interface.get_temperatures_sync()
        cpu_temp = temps.get('cpu_temp', TEMP_READ_ERROR_VALUE)
        gpu_temp = temps.get('gpu_temp', TEMP_READ_ERROR_VALUE)
        
        # 更新UI状态（即使有错误也要更新，以便UI显示错误状态）
        self.state.set_cpu_temp(cpu_temp)
        self.state.set_gpu_temp(gpu_temp)

        # 只有在温度读取成功时才进行计算和应用
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
        """由UI定时器触发，用于刷新UI显示的传感器数据。"""
        if self._is_shutting_down or not self.wmi_interface.is_running or not self._is_ui_visible:
            return
        
        # 【重构】从WMI接口的缓存中非阻塞地获取数据，对UI线程零影响
        sensor_data = self.wmi_interface.get_latest_core_sensor_data()
        self._update_state_from_sensor_data(sensor_data)

    @Slot()
    def perform_full_status_update(self):
        """
        执行一次全局的、阻塞式的WMI查询，用于需要立即反馈的场景。
        （如启动、窗口激活、设置更改后）
        """
        sensor_data = self.wmi_interface.get_all_sensors_sync()
        self._update_state_from_sensor_data(sensor_data)

    def _update_state_from_sensor_data(self, sensor_data: dict):
        """一个通用的辅助函数，用从WMI获取的数据更新AppState。"""
        if not sensor_data: return
        
        # 只有在数据存在时才更新，避免覆盖由其他逻辑（如温控循环）设置的值
        if 'cpu_temp' in sensor_data: self.state.set_cpu_temp(sensor_data['cpu_temp'])
        if 'gpu_temp' in sensor_data: self.state.set_gpu_temp(sensor_data['gpu_temp'])
        if 'fan1_rpm' in sensor_data: self.state.set_cpu_fan_rpm(sensor_data['fan1_rpm'])
        if 'fan2_rpm' in sensor_data: self.state.set_gpu_fan_rpm(sensor_data['fan2_rpm'])
        if 'charge_policy' in sensor_data:
            self.state.set_applied_charge_policy(BATTERY_CODE_POLICIES.get(sensor_data['charge_policy'], "err"))
        if 'charge_threshold' in sensor_data:
            self.state.set_applied_charge_threshold(sensor_data['charge_threshold'])

    def set_ui_visibility(self, is_visible: bool):
        """当UI显示或隐藏时调用，用于启动/停止轮询和执行一次性更新。"""
        self._is_ui_visible = is_visible
        if is_visible:
            # 当窗口变为可见时，立即执行一次全局刷新
            self.perform_full_status_update()