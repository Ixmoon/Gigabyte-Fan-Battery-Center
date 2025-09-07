# -*- coding: utf-8 -*-
"""
处理应用的国际化(i18n)。
从JSON文件加载语言字符串并提供翻译函数。
"""

import json
import os
import sys
from typing import Dict, Optional
from config.settings import DEFAULT_LANGUAGE, KNOWN_LANGUAGES

# ==============================================================================
# 默认翻译字典
# ==============================================================================

# --- 默认英文翻译 ---
DEFAULT_ENGLISH_TRANSLATIONS: Dict[str, str] = {
    # 窗口和UI元素
    "window_title": "Fan & Battery Control",
    "cpu_temp_label": "CPU Temp:",
    "gpu_temp_label": "GPU Temp:",
    "cpu_fan_rpm_label": "CPU Fan RPM:",
    "gpu_fan_rpm_label": "GPU Fan RPM:",
    "applied_target_label": "Applied/Target:",
    "fan_mode_label": "Fan Mode:",
    "mode_bios": "BIOS",
    "mode_auto": "Auto",
    "mode_custom": "Custom",
    "custom_speed_label": "Custom Speed:",
    "charge_policy_label": "Charge Policy:",
    "charge_threshold_label": "Charge Limit:",
    "cpu_curve_button": "CPU Curve",
    "gpu_curve_button": "GPU Curve",
    "reset_curve_button": "Reset Curve",
    "battery_info_label": "Battery:",
    "start_on_boot_label": "Start on Boot",
    "percent_unit": "%",
    "rpm_unit": " RPM",
    "celsius_unit": "°C",
    "temp_label": "Temp",
    "speed_label": "Speed",
    "rename_button": "Rename",
    "delete_button": "Delete",

    # 工具提示
    "curve_point_tooltip": "Temp: {temp}°C, Speed: {speed}%",
    "add_point_info": "Double-click empty space to add point.",
    "delete_point_info": "Right-click point to delete.",
    "profile_button_tooltip": "Left-Click: Activate\nRight-Click: Save\nDouble-Click: Manage",
    "add_profile_tooltip": "Add a new profile",
    "start_on_boot_tooltip": "Automatically start with Windows via Task Scheduler.",
    "fan_mode_tooltip": "Select the fan control mode.\nBIOS: Control by hardware\nAuto: Control by temperature curve\nCustom: Fixed fan speed",
    "custom_fan_speed_tooltip": "Set a fixed fan speed for Custom mode.",
    "charge_policy_tooltip": "Select the battery charging policy.\nBIOS: Default hardware behavior\nCustom: Limit charging to a specific threshold",
    "charge_threshold_tooltip": "Set the maximum charge level for Custom policy.",
    "reset_curve_tooltip": "Reset the currently active curve to its default points.",
    "editable_label_tooltip": "Double-click to enter a value manually.",
    "maximize_button_tooltip": "Maximize",
    "restore_button_tooltip": "Restore",
    
    # 状态消息
    "initializing": "Initializing...",
    "paused": "Paused (Hidden)",
    "saving_config": "Config saved.",
    "shutting_down": "Shutting down...",
    "profile_saved_message": "Settings saved to '{profile_name}'.",
    "value_not_available": "---",
    "fan_display_auto_format": "{applied}% / {target}%",
    "battery_display_format": "{policy} / {limit}",

    # 错误和对话框
    "wmi_init_error_title": "WMI Error",
    "wmi_init_error_msg": "Failed to initialize WMI.\nEnsure Gigabyte drivers are installed.\n\nError: {error}",
    "wmi_error": "WMI Error",
    "temp_error": "ERR",
    "rpm_error": "ERR",
    "delete_point_error_title": "Delete Error",
    "delete_point_error_msg": "Cannot delete. Minimum of {min_points} points required.",
    "rename_profile_title": "Manage Profile",
    "rename_profile_label": "Enter a new name for '{old_name}':",
    "delete_profile_title": "Delete Profile",
    "delete_profile_confirm_msg": "Are you sure you want to permanently delete the profile '{name}'?",
    "add_profile_title": "Add New Profile",
    "add_profile_label": "Enter name for the new profile:",
    "add_profile_error_title": "Invalid Name",
    "add_profile_empty_name_error": "Profile name cannot be empty.",
    "add_profile_duplicate_name_error": "A profile named '{name}' already exists.",
    "admin_required_title": "Administrator Privileges Required",
    "admin_required_msg": "This application requires administrator privileges.",
    "elevation_error_title": "Elevation Error",
    "elevation_error_msg": "Failed to elevate privileges. Please run as administrator.",
    "task_scheduler_error_msg": "Task Scheduler failed.\nCommand: {command}\n\nError: {error}",
    "unhandled_exception_title": "Unhandled Exception",
    "single_instance_error_title": "Application Already Running",
    "single_instance_error_msg": "Another instance of {app_name} is already running.\nActivating the existing window.",

    # 托盘菜单
    "tray_menu_show_hide": "Show / Hide",
    "tray_menu_quit": "Quit",

    # 语言显示名称
    "lang_display_name_en": "English",
    "lang_display_name_zh": "中文",
}

# --- 默认中文翻译 ---
DEFAULT_CHINESE_TRANSLATIONS: Dict[str, str] = {
    # 窗口和UI元素
    "window_title": "风扇 & 电池控制",
    "cpu_temp_label": "CPU 温度:",
    "gpu_temp_label": "GPU 温度:",
    "cpu_fan_rpm_label": "CPU 风扇转速:",
    "gpu_fan_rpm_label": "GPU 风扇转速:",
    "applied_target_label": "应用/目标:",
    "fan_mode_label": "风扇模式:",
    "mode_bios": "BIOS",
    "mode_auto": "自动",
    "mode_custom": "自定义",
    "custom_speed_label": "自定义速度:",
    "charge_policy_label": "充电策略:",
    "charge_threshold_label": "充电上限:",
    "cpu_curve_button": "CPU 曲线",
    "gpu_curve_button": "GPU 曲线",
    "reset_curve_button": "重置曲线",
    "battery_info_label": "电池:",
    "start_on_boot_label": "开机启动",
    "percent_unit": "%",
    "rpm_unit": " RPM",
    "celsius_unit": "°C",
    "temp_label": "温度",
    "speed_label": "速度",
    "rename_button": "重命名",
    "delete_button": "删除",

    # 工具提示
    "curve_point_tooltip": "温度: {temp}°C, 速度: {speed}%",
    "add_point_info": "双击空白区域以添加点。",
    "delete_point_info": "右键单击点以删除。",
    "profile_button_tooltip": "左键: 激活\n右键: 保存\n双击: 管理",
    "add_profile_tooltip": "添加新配置文件",
    "start_on_boot_tooltip": "通过任务计划程序随 Windows 自动启动。",
    "fan_mode_tooltip": "选择风扇控制模式。\nBIOS: 由硬件控制\n自动: 根据温度曲线控制\n自定义: 固定风扇速度",
    "custom_fan_speed_tooltip": "为自定义模式设置一个固定的风扇速度。",
    "charge_policy_tooltip": "选择电池充电策略。\nBIOS: 默认硬件行为\n自定义: 将充电限制在特定阈值",
    "charge_threshold_tooltip": "为自定义策略设置最大充电水平。",
    "reset_curve_tooltip": "将当前活动的曲线重置为其默认点。",
    "editable_label_tooltip": "双击以手动输入数值。",
    "maximize_button_tooltip": "最大化",
    "restore_button_tooltip": "还原",
    
    # 状态消息
    "initializing": "正在初始化...",
    "paused": "已暂停 (最小化)",
    "saving_config": "配置已保存。",
    "shutting_down": "正在关闭...",
    "profile_saved_message": "设置已保存至 '{profile_name}'。",
    "value_not_available": "---",
    "fan_display_auto_format": "{applied}% / {target}%",
    "battery_display_format": "{policy} / {limit}",

    # 错误和对话框
    "wmi_init_error_title": "WMI 错误",
    "wmi_init_error_msg": "WMI 初始化失败。\n请确保已安装技嘉驱动程序。\n\n错误: {error}",
    "wmi_error": "WMI 错误",
    "temp_error": "错误",
    "rpm_error": "错误",
    "delete_point_error_title": "删除错误",
    "delete_point_error_msg": "无法删除。至少需要 {min_points} 个点。",
    "rename_profile_title": "管理配置文件",
    "rename_profile_label": "为 '{old_name}' 输入新名称:",
    "delete_profile_title": "删除配置文件",
    "delete_profile_confirm_msg": "您确定要永久删除配置文件 '{name}' 吗？",
    "add_profile_title": "添加新配置文件",
    "add_profile_label": "为新配置文件输入名称:",
    "add_profile_error_title": "无效名称",
    "add_profile_empty_name_error": "配置文件名称不能为空。",
    "add_profile_duplicate_name_error": "名为 '{name}' 的配置文件已存在。",
    "admin_required_title": "需要管理员权限",
    "admin_required_msg": "此应用程序需要管理员权限才能运行。",
    "elevation_error_title": "提权失败",
    "elevation_error_msg": "无法提升权限。请以管理员身份运行。",
    "task_scheduler_error_msg": "任务计划程序失败。\n命令: {command}\n\n错误: {error}",
    "unhandled_exception_title": "未处理的异常",
    "single_instance_error_title": "应用程序已在运行",
    "single_instance_error_msg": "{app_name} 的另一个实例已在运行。\n正在激活现有窗口。",

    # 托盘菜单
    "tray_menu_show_hide": "显示 / 隐藏",
    "tray_menu_quit": "退出",

    # 语言显示名称
    "lang_display_name_en": "English",
    "lang_display_name_zh": "中文",
}

# ==============================================================================
# 核心翻译逻辑
# ==============================================================================

_translations: Dict[str, Dict[str, str]] = {}
_current_language: str = DEFAULT_LANGUAGE
_translations_loaded: bool = False
_language_file_path: Optional[str] = None

def load_translations(file_path: str):
    global _translations, _translations_loaded, _language_file_path
    _language_file_path = file_path
    
    # 默认数据现在包含英文和中文
    default_data = {
        "en": DEFAULT_ENGLISH_TRANSLATIONS.copy(),
        "zh": DEFAULT_CHINESE_TRANSLATIONS.copy()
    }
    loaded_data = {}
    
    try:
        if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
            with open(file_path, 'r', encoding='utf-8') as f:
                loaded_data = json.load(f)
            if not isinstance(loaded_data, dict):
                raise json.JSONDecodeError("Invalid format", "", 0)
        else:
            raise FileNotFoundError
    except (FileNotFoundError, json.JSONDecodeError):
        try:
            dir_name = os.path.dirname(file_path)
            if dir_name:
                os.makedirs(dir_name, exist_ok=True)
            # 将包含两种语言的默认数据写入文件
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(default_data, f, indent=4, ensure_ascii=False)
            loaded_data = default_data
        except IOError as e:
            print(f"无法写入默认语言文件: {e}", file=sys.stderr)
            loaded_data = default_data

    # 最终的翻译字典从硬编码的默认值开始，以确保健壮性
    final_translations = default_data.copy()
    for lang, trans in loaded_data.items():
        if isinstance(trans, dict):
            # 使用英文作为基础，然后用加载的翻译覆盖
            merged = DEFAULT_ENGLISH_TRANSLATIONS.copy()
            merged.update(trans)
            final_translations[lang] = merged
    
    _translations = final_translations
    _translations_loaded = True

def set_language(lang_code: str):
    global _current_language
    if lang_code in _translations:
        _current_language = lang_code
    else:
        _current_language = DEFAULT_LANGUAGE

def tr(key: str, **kwargs) -> str:
    # 首先尝试获取当前语言的翻译
    lang_dict = _translations.get(_current_language, {})
    translation = lang_dict.get(key)
    
    # 如果当前语言没有，则回退到硬编码的英文
    if translation is None:
        translation = DEFAULT_ENGLISH_TRANSLATIONS.get(key, key)
        
    try:
        return translation.format(**kwargs)
    except (KeyError, ValueError):
        return translation

def get_available_languages() -> Dict[str, str]:
    available = {}
    for code in sorted(_translations.keys()):
        display_name_key = f"lang_display_name_{code}"
        display_name = _translations[code].get(display_name_key, KNOWN_LANGUAGES.get(code, code.upper()))
        available[code] = display_name
    return available

def get_current_language() -> str:
    return _current_language