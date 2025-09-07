# -*- coding: utf-8 -*-
"""
风扇和电池控制应用的全局常量和默认设置。
"""
from typing import List, Dict, Any

# ==============================================================================
# 应用信息
# ==============================================================================
APP_NAME: str = "FanBatteryControl"
APP_ORGANIZATION_NAME: str = "FanBatteryControl" # Qt用于设置路径
APP_INTERNAL_NAME: str = "FanBatteryControl" # 用于互斥锁、任务名称等

# ==============================================================================
# 文件路径 (这些现在由 core.path_manager.PathManager 集中管理)
# ==============================================================================

# ==============================================================================
# 默认配置值
# ==============================================================================
DEFAULT_LANGUAGE: str = "en" # 默认语言代码 (ISO 639-1)

# --- 核心状态常量 ---
FAN_MODE_BIOS = "bios"
FAN_MODE_AUTO = "auto" # 软件控制的曲线
FAN_MODE_CUSTOM = "custom" # 软件控制的自定义速度
FAN_MODE_UNKNOWN = "unknown"
CHARGE_POLICY_BIOS = "bios"
CHARGE_POLICY_CUSTOM = "custom"

# --- 电池控制常量 ---
BATTERY_POLICY_CODES: Dict[str, int] = {"bios": 0, "custom": 4}
BATTERY_CODE_POLICIES: Dict[int, str] = {v: k for k, v in BATTERY_POLICY_CODES.items()}

# --- 默认配置文件设置 ---
# 定义了 *每个* 配置文件的结构和默认值
DEFAULT_CPU_FAN_TABLE: List[List[int]] = [[50, 0], [60, 15], [70, 25], [80, 40], [85, 60], [90, 80], [95, 100]]
DEFAULT_GPU_FAN_TABLE: List[List[int]] = [[40, 0], [55, 15], [65, 25], [70, 40], [75, 60], [80, 80], [85, 100]]
DEFAULT_FAN_MODE: str = FAN_MODE_AUTO
DEFAULT_CUSTOM_FAN_SPEED: int = 30 # 百分比
DEFAULT_CHARGE_POLICY: str = CHARGE_POLICY_BIOS
DEFAULT_CHARGE_THRESHOLD: int = 80 # 百分比

# --- 默认控制逻辑和时序 (每个配置文件) ---
DEFAULT_GUI_UPDATE_INTERVAL_MS: int = 1000 # GUI刷新状态的频率
DEFAULT_CONTROLLER_UPDATE_INTERVAL_MS: int = 1500 # 在自动模式下调整风扇速度朝向目标的频率
DEFAULT_FAN_HYSTERESIS_PERCENT: int = 5 # 触发目标重新计算所需的温度变化
DEFAULT_MIN_ADJUSTMENT_STEP: int = 1 # 每个调整间隔的最小风扇速度变化
DEFAULT_MAX_ADJUSTMENT_STEP: int = 5 # 每个调整间隔的最大风扇速度变化

# --- 默认曲线绘制和UI外观 (每个配置文件) ---
DEFAULT_MIN_DISPLAY_TEMP_C: int = 40 # 【新增】曲线图X轴显示的最小温度
DEFAULT_CURVE_POINT_PICKER_RADIUS: float = 8.0 # 图上点的点击半径
DEFAULT_SPLINE_POINTS: int = 100 # 平滑曲线插值线的点数
DEFAULT_CPU_CURVE_COLOR: str = '#00AEEF'
DEFAULT_GPU_CURVE_COLOR: str = '#7AC143'
DEFAULT_POINT_COLOR_ACTIVE: str = '#FFFFFF'
DEFAULT_POINT_SIZE_ACTIVE: int = 7
DEFAULT_CPU_TEMP_INDICATOR_COLOR: str = '#FF6347' # 番茄色
DEFAULT_GPU_TEMP_INDICATOR_COLOR: str = '#90EE90' # 亮绿色
DEFAULT_LINE_WIDTH_ACTIVE: float = 2.0
DEFAULT_LINE_WIDTH_INACTIVE: float = 1.0
DEFAULT_ALPHA_ACTIVE: float = 1.0
DEFAULT_ALPHA_INACTIVE: float = 0.4
DEFAULT_FIGURE_BG_COLOR: str = '#33373B'
DEFAULT_AXES_BG_COLOR: str = '#2A2D30'
DEFAULT_GRID_COLOR: str = '#555555'
DEFAULT_AXES_LABEL_COLOR: str = '#E0E0E0'

# --- 将所有默认配置文件设置合并到一个字典中 ---
DEFAULT_PROFILE_SETTINGS: Dict[str, Any] = {
    "cpu_fan_table": [list(p) for p in DEFAULT_CPU_FAN_TABLE],
    "gpu_fan_table": [list(p) for p in DEFAULT_GPU_FAN_TABLE],
    "fan_mode": DEFAULT_FAN_MODE,
    "custom_fan_speed": DEFAULT_CUSTOM_FAN_SPEED,
    "battery_charge_policy": DEFAULT_CHARGE_POLICY,
    "battery_charge_threshold": DEFAULT_CHARGE_THRESHOLD,
    "gui_update_interval_ms": DEFAULT_GUI_UPDATE_INTERVAL_MS,
    "controller_update_interval_ms": DEFAULT_CONTROLLER_UPDATE_INTERVAL_MS,
    "fan_hysteresis_percent": DEFAULT_FAN_HYSTERESIS_PERCENT,
    "min_adjustment_step": DEFAULT_MIN_ADJUSTMENT_STEP,
    "max_adjustment_step": DEFAULT_MAX_ADJUSTMENT_STEP,
    "min_display_temp_c": DEFAULT_MIN_DISPLAY_TEMP_C, # 【新增】
    "curve_point_picker_radius": DEFAULT_CURVE_POINT_PICKER_RADIUS,
    "spline_points": DEFAULT_SPLINE_POINTS,
    "cpu_curve_color": DEFAULT_CPU_CURVE_COLOR,
    "gpu_curve_color": DEFAULT_GPU_CURVE_COLOR,
    "point_color_active": DEFAULT_POINT_COLOR_ACTIVE,
    "point_size_active": DEFAULT_POINT_SIZE_ACTIVE,
    "cpu_temp_indicator_color": DEFAULT_CPU_TEMP_INDICATOR_COLOR,
    "gpu_temp_indicator_color": DEFAULT_GPU_TEMP_INDICATOR_COLOR,
    "line_width_active": DEFAULT_LINE_WIDTH_ACTIVE,
    "line_width_inactive": DEFAULT_LINE_WIDTH_INACTIVE,
    "alpha_active": DEFAULT_ALPHA_ACTIVE,
    "alpha_inactive": DEFAULT_ALPHA_INACTIVE,
    "figure_bg_color": DEFAULT_FIGURE_BG_COLOR,
    "axes_bg_color": DEFAULT_AXES_BG_COLOR,
    "grid_color": DEFAULT_GRID_COLOR,
    "axes_label_color": DEFAULT_AXES_LABEL_COLOR,
}

# ==============================================================================
# WMI 配置
# ==============================================================================
WMI_NAMESPACE: str = r"root\WMI"
DEFAULT_WMI_GET_CLASS: str = "GB_WMIACPI_Get"
DEFAULT_WMI_SET_CLASS: str = "GB_WMIACPI_Set"
WMI_REQUEST_TIMEOUT_S: float = 5.0
WMI_WORKER_STOP_SIGNAL: str = "STOP_WMI_WORKER"
# 【重构】移除所有 WMI_ACTION_* 常量，只保留WMI方法名的字符串常量
WMI_GET_CPU_TEMP: str = "getCpuTemp"
WMI_GET_GPU_TEMP1: str = "getGpuTemp1"
WMI_GET_GPU_TEMP2: str = "getGpuTemp2"
WMI_GET_RPM1: str = "getRpm1"
WMI_GET_RPM2: str = "getRpm2"
WMI_GET_CHARGE_POLICY: str = "GetChargePolicy"
WMI_GET_CHARGE_STOP: str = "GetChargeStop"
WMI_SET_CUSTOM_FAN_STATUS: str = "SetFixedFanStatus"
WMI_SET_AUTO_FAN_STATUS: str = "SetAutoFanStatus"
WMI_SET_CUSTOM_FAN_SPEED: str = "SetFixedFanSpeed"
WMI_SET_GPU_FAN_DUTY: str = "SetGPUFanDuty"
WMI_SET_CHARGE_POLICY: str = "SetChargePolicy"
WMI_SET_CHARGE_STOP: str = "SetChargeStop"
WMI_SET_SUPER_QUIET: str = "SetSuperQuiet"
WMI_SET_STEP_FAN_STATUS: str = "SetStepFanStatus"
TEMP_READ_ERROR_VALUE: float = -1.0
RPM_READ_ERROR_VALUE: int = -1
CHARGE_POLICY_READ_ERROR_VALUE: int = -1
CHARGE_THRESHOLD_READ_ERROR_VALUE: int = -1
INIT_APPLIED_PERCENTAGE: int = -1

# ==============================================================================
# 控制逻辑参数
# ==============================================================================
MIN_TEMP_C: int = 0
MAX_TEMP_C: int = 100
MIN_FAN_PERCENT: int = 0
MAX_FAN_PERCENT: int = 100
MIN_CHARGE_PERCENT: int = 60
MAX_CHARGE_PERCENT: int = 100
MIN_CURVE_POINTS: int = 2
MIN_POINTS_FOR_INTERPOLATION: int = 2

# ==============================================================================
# 任务计划程序 / 单例实例
# ==============================================================================
TASK_SCHEDULER_NAME: str = f"{APP_INTERNAL_NAME} Startup Task"
STARTUP_ARG_MINIMIZED: str = "--minimized"
_APP_GUID: str = "{17e0cc04-cddb-4b9b-adcc-5faa4872e054}"
MUTEX_NAME: str = f"Global\\{APP_INTERNAL_NAME}_Mutex_{_APP_GUID}"
SHARED_MEM_NAME: str = f"Global\\{APP_INTERNAL_NAME}_SharedMem_{_APP_GUID}"
SHARED_MEM_SIZE: int = 64
# --- 共享内存命令结构 ---
SHARED_MEM_HWND_OFFSET: int = 0
SHARED_MEM_HWND_SIZE: int = 32
SHARED_MEM_COMMAND_OFFSET: int = 32
SHARED_MEM_COMMAND_SIZE: int = 1
COMMAND_NONE: int = 0
COMMAND_QUIT: int = 1                  # 请求现有实例退出
COMMAND_RELOAD_AND_SHOW: int = 2       # 请求现有实例重载配置并显示窗口 (用户手动启动)
COMMAND_RELOAD_ONLY: int = 3           # 请求现有实例仅重载配置 (任务计划程序启动)

# ==============================================================================
# 杂项
# ==============================================================================
TOOLTIP_DELAY_MS: int = 500
KNOWN_LANGUAGES: Dict[str, str] = {"en": "English", "zh": "中文"}