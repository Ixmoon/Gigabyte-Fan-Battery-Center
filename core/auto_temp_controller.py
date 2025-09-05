# -*- coding: utf-8 -*-
"""
一个纯粹的、无副作用的计算引擎，负责基于温度曲线计算目标风扇速度。
此类维护自动模式的内部状态（如迟滞和当前目标），但不执行任何硬件I/O。
"""

from typing import List, Optional, Dict, cast
import sys

from gui.qt import QObject

from .interpolation import PchipInterpolator, clip, interp
from .state import ProfileState

from config.settings import (
    MIN_FAN_PERCENT, MAX_FAN_PERCENT,
    MIN_POINTS_FOR_INTERPOLATION,
    TEMP_READ_ERROR_VALUE, INIT_APPLIED_PERCENTAGE,
    DEFAULT_PROFILE_SETTINGS
)

# 类型提示
FanTable = List[List[int]] # [[温度, 速度], ...]

class AutoTemperatureController(QObject):
    """
    根据给定的温度和风扇曲线，计算并平滑地调整风扇速度。
    这是一个无I/O的状态计算器，由AppServices驱动。
    """
    def __init__(self):
        super().__init__()
        # --- 内部插值器和曲线数据 ---
        self._cpu_interpolator: Optional[PchipInterpolator] = None
        self._gpu_interpolator: Optional[PchipInterpolator] = None
        self._cpu_curve_data: FanTable = []
        self._gpu_curve_data: FanTable = []

        # --- 控制逻辑参数 ---
        self._hysteresis_percent: int = DEFAULT_PROFILE_SETTINGS['fan_hysteresis_percent']
        self._min_step: int = DEFAULT_PROFILE_SETTINGS['min_adjustment_step']
        self._max_step: int = DEFAULT_PROFILE_SETTINGS['max_adjustment_step']

        # --- 运行时状态变量 ---
        self._active_target_percentage: int = INIT_APPLIED_PERCENTAGE
        self._last_theoretical_target: int = INIT_APPLIED_PERCENTAGE
        self._current_adjustment_step_size: Optional[int] = None

    def get_last_theoretical_target(self) -> int:
        """返回上次计算的理论目标速度以供UI显示。"""
        return self._last_theoretical_target if self._last_theoretical_target != INIT_APPLIED_PERCENTAGE else 0

    def update_curves(self, cpu_curve: FanTable, gpu_curve: FanTable):
        """
        更新用于插值的风扇曲线数据。
        这会清除旧的插值器缓存，以便在下次需要时重新创建。
        """
        self._cpu_curve_data = self._validate_and_sort(cpu_curve)
        self._gpu_curve_data = self._validate_and_sort(gpu_curve)
        self._cpu_interpolator = self._create_interpolator(self._cpu_curve_data, "CPU")
        self._gpu_interpolator = self._create_interpolator(self._gpu_curve_data, "GPU")
        self.reset_state()

    def update_auto_settings(self, profile: ProfileState):
        """从配置文件更新自动模式的控制参数（如迟滞、步长）。"""
        self._hysteresis_percent = profile.get_value('fan_hysteresis_percent')
        self._min_step = profile.get_value('min_adjustment_step')
        self._max_step = profile.get_value('max_adjustment_step')
        self._min_step = max(0, self._min_step) # 确保最小步长不为负
        self._max_step = max(self._min_step, self._max_step) # 确保最大步长不小于最小步长
        self._current_adjustment_step_size = None # 重置步长缓存

    def reset_state(self):
        """重置内部自动模式的运行时状态变量，通常在模式切换或曲线更改时调用。"""
        self._active_target_percentage = INIT_APPLIED_PERCENTAGE
        self._last_theoretical_target = INIT_APPLIED_PERCENTAGE
        self._current_adjustment_step_size = None

    def _validate_and_sort(self, table: FanTable) -> FanTable:
        """按温度对表进行排序并确保数据点基本有效。"""
        if not isinstance(table, list): return []
        valid_points = [p for p in table if isinstance(p, list) and len(p) == 2 and all(isinstance(x, (int, float)) for x in p)]
        return sorted(valid_points, key=lambda x: x[0])

    def _create_interpolator(self, table: FanTable, curve_name: str) -> Optional[PchipInterpolator]:
        """使用PCHIP算法从风扇表中创建插值器对象。"""
        if len(table) < MIN_POINTS_FOR_INTERPOLATION: return None
        
        # 处理具有相同温度值的点：保留速度较高的点以确保安全
        unique_temps_map: Dict[float, float] = {}
        for t, s in table:
            if t not in unique_temps_map or s > unique_temps_map[t]:
                unique_temps_map[t] = s
        
        if len(unique_temps_map) < MIN_POINTS_FOR_INTERPOLATION: return None
        
        unique_temps = sorted(unique_temps_map.keys())
        unique_speeds = [unique_temps_map[t] for t in unique_temps]
        
        try:
            return PchipInterpolator([float(t) for t in unique_temps], [float(s) for s in unique_speeds], extrapolate=False)
        except Exception as e:
            print(f"创建 {curve_name} PCHIP插值器时出错: {e}", file=sys.stderr)
            return None

    def _linear_interpolate(self, temperature: float, table: FanTable) -> float:
        """作为后备方案执行简单的线性插值。"""
        temps = [float(p[0]) for p in table]
        speeds = [float(p[1]) for p in table]
        return interp(temperature, temps, speeds)

    def _interpolate_single_curve(self, temperature: float, table: FanTable, interpolator: Optional[PchipInterpolator]) -> int:
        """为单个曲线计算目标速度，优先使用PCHIP，并提供线性插值作为后备。"""
        if not table: return MIN_FAN_PERCENT
        if temperature == TEMP_READ_ERROR_VALUE: return MIN_FAN_PERCENT

        min_temp_curve, min_speed_curve = table[0]
        max_temp_curve, max_speed_curve = table[-1]

        # 处理超出曲线范围的温度
        if temperature <= min_temp_curve: return int(min_speed_curve)
        if temperature >= max_temp_curve: return int(max_speed_curve)

        interp_speed = 0.0
        if interpolator:
            try:
                interp_speed = interpolator(temperature)
            except Exception:
                interp_speed = self._linear_interpolate(temperature, table)
        else:
            interp_speed = self._linear_interpolate(temperature, table)

        final_speed = cast(float, interp_speed)
        clipped_speed = cast(float, clip(final_speed, MIN_FAN_PERCENT, MAX_FAN_PERCENT))
        return int(round(clipped_speed))

    def _calculate_theoretical_target(self, cpu_temp: float, gpu_temp: float) -> int:
        """根据当前温度和曲线计算出理论上的目标风扇速度。"""
        cpu_target = self._interpolate_single_curve(cpu_temp, self._cpu_curve_data, self._cpu_interpolator)
        gpu_target = self._interpolate_single_curve(gpu_temp, self._gpu_curve_data, self._gpu_interpolator)
        # 最终目标取CPU和GPU目标中较高的一个，以确保充分散热
        return max(cpu_target, gpu_target)

    def _calculate_adjustment_step_size(self, initial_delta: int) -> int:
        """根据当前速度与目标的初始差距动态计算调整步长。"""
        if initial_delta <= 0: return 0
        step_range = self._max_step - self._min_step
        if step_range > 0:
            # 差距越大，步长越大，但最大不超过max_step
            scale_factor = min(1.0, initial_delta / 100.0) # 将差距归一化
            calculated_step = self._min_step + (step_range * scale_factor)
            step_size = int(round(calculated_step))
        else:
            step_size = self._min_step
        
        step_size = max(self._min_step, min(self._max_step, step_size))
        return max(1, step_size) # 确保步长至少为1

    def _update_active_target(self, current_applied_speed: int, cpu_temp: float, gpu_temp: float):
        """
        计算理论目标，应用迟滞逻辑，并在必要时更新内部的“活动目标速度”。
        这是为了防止风扇因温度在临界点附近小幅波动而频繁启停或变速。
        """
        theoretical_target = self._calculate_theoretical_target(cpu_temp, gpu_temp)
        self._last_theoretical_target = theoretical_target

        # 只有当理论目标与当前活动目标的差距超过迟滞阈值时，才更新活动目标
        if self._active_target_percentage == INIT_APPLIED_PERCENTAGE or \
           abs(theoretical_target - self._active_target_percentage) > self._hysteresis_percent:
            if self._active_target_percentage != theoretical_target:
                self._active_target_percentage = theoretical_target
                # 当目标更新时，重新计算调整步长
                initial_delta = abs(self._active_target_percentage - current_applied_speed)
                self._current_adjustment_step_size = self._calculate_adjustment_step_size(initial_delta)

    def _calculate_next_speed(self, current_applied_speed: int) -> Optional[int]:
        """
        根据“活动目标”计算出下一个要应用的具体风扇速度值。
        这实现了风扇速度的平滑渐变，而不是瞬时跳变。
        """
        target = self._active_target_percentage
        if target == INIT_APPLIED_PERCENTAGE or current_applied_speed == target:
            # 如果已达到目标，则重置步长缓存，返回None表示无需调整
            if self._current_adjustment_step_size is not None:
                self._current_adjustment_step_size = None
            return None

        step_size = self._current_adjustment_step_size
        if step_size is None:
            # 如果步长未缓存，说明是新的调整周期，计算一次
            initial_delta = abs(target - current_applied_speed)
            step_size = self._calculate_adjustment_step_size(initial_delta)
            self._current_adjustment_step_size = step_size
        
        step_size = max(1, step_size) # 再次确保步长有效

        # 向目标值移动一步
        next_speed = current_applied_speed
        if target > current_applied_speed:
            next_speed = min(target, current_applied_speed + step_size)
        elif target < current_applied_speed:
            next_speed = max(target, current_applied_speed - step_size)

        # 如果这一步之后达到了目标，清除步长缓存
        if next_speed == target:
            self._current_adjustment_step_size = None

        return next_speed if next_speed != current_applied_speed else None

    def perform_adjustment_step(self, current_applied_speed: int, cpu_temp: float, gpu_temp: float) -> Optional[int]:
        """
        执行一次完整的风扇调整计算。
        这是由AppServices在每个控制周期调用的主方法。

        Args:
            current_applied_speed: 当前已应用到硬件的风扇速度百分比。
            cpu_temp: 当前CPU温度。
            gpu_temp: 当前GPU温度。

        Returns:
            如果需要更改，则返回新的风扇速度百分比；否则返回None。
        """
        # 1. 根据新温度更新活动目标（包含迟滞逻辑）
        self._update_active_target(current_applied_speed, cpu_temp, gpu_temp)
        # 2. 根据活动目标计算平滑调整的下一步速度
        speed_to_apply = self._calculate_next_speed(current_applied_speed)
        
        return speed_to_apply