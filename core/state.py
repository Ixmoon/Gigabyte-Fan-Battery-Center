# -*- coding: utf-8 -*-
"""
定义了应用的中心化、响应式状态。
所有状态类都继承自QObject，并使用Qt的属性系统(@Property)来在其值改变时自动发出信号。
这使得UI组件可以精确地订阅它们所关心的数据变化，实现最高效的更新。
"""
import copy
from gui.qt import QObject, Signal, Property, Slot
from typing import List, Dict, Optional, Any, cast
from config.settings import DEFAULT_PROFILE_SETTINGS
from core.path_manager import PathManager

class ProfileState(QObject):
    """
    表示单个配置文件的响应式设置集。
    每个属性的更改都会发出一个特定的信号。
    """
    fan_mode_changed = Signal(str)
    custom_fan_speed_changed = Signal(int)
    battery_charge_policy_changed = Signal(str)
    battery_charge_threshold_changed = Signal(int)
    cpu_fan_table_changed = Signal(list)
    gpu_fan_table_changed = Signal(list)
    appearance_changed = Signal()

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._data = copy.deepcopy(DEFAULT_PROFILE_SETTINGS)

    def _set_value(self, key: str, value: Any, signal: Any):
        if self._data.get(key) != value:
            self._data[key] = value
            signal.emit(value)

    def get_value(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def to_dict(self) -> Dict[str, Any]:
        return copy.deepcopy(self._data)

    def from_dict(self, data: Dict[str, Any]):
        final_data = copy.deepcopy(DEFAULT_PROFILE_SETTINGS)
        final_data.update(data)
        
        for key in ['cpu_fan_table', 'gpu_fan_table']:
            if key in final_data and final_data[key]:
                final_data[key] = [list(point) for point in final_data[key]]

        self.set_fan_mode(final_data['fan_mode'])
        self.set_custom_fan_speed(final_data['custom_fan_speed'])
        self.set_battery_charge_policy(final_data['battery_charge_policy'])
        self.set_battery_charge_threshold(final_data['battery_charge_threshold'])
        self.set_cpu_fan_table(final_data['cpu_fan_table'])
        self.set_gpu_fan_table(final_data['gpu_fan_table'])

        appearance_changed = False
        for key, value in final_data.items():
            if key in ['fan_mode', 'custom_fan_speed', 'battery_charge_policy', 'battery_charge_threshold', 'cpu_fan_table', 'gpu_fan_table']:
                continue
            if self._data.get(key) != value:
                self._data[key] = value
                appearance_changed = True
        
        if appearance_changed:
            self.appearance_changed.emit()

    def get_fan_mode(self) -> str: return cast(str, self._data['fan_mode'])
    def set_fan_mode(self, value: str): self._set_value('fan_mode', value, self.fan_mode_changed)
    fan_mode = Property(str, get_fan_mode, set_fan_mode, notify=fan_mode_changed) # type: ignore

    def get_custom_fan_speed(self) -> int: return cast(int, self._data['custom_fan_speed'])
    def set_custom_fan_speed(self, value: int): self._set_value('custom_fan_speed', value, self.custom_fan_speed_changed)
    custom_fan_speed = Property(int, get_custom_fan_speed, set_custom_fan_speed, notify=custom_fan_speed_changed) # type: ignore

    def get_battery_charge_policy(self) -> str: return cast(str, self._data['battery_charge_policy'])
    def set_battery_charge_policy(self, value: str): self._set_value('battery_charge_policy', value, self.battery_charge_policy_changed)
    battery_charge_policy = Property(str, get_battery_charge_policy, set_battery_charge_policy, notify=battery_charge_policy_changed) # type: ignore

    def get_battery_charge_threshold(self) -> int: return cast(int, self._data['battery_charge_threshold'])
    def set_battery_charge_threshold(self, value: int): self._set_value('battery_charge_threshold', value, self.battery_charge_threshold_changed)
    battery_charge_threshold = Property(int, get_battery_charge_threshold, set_battery_charge_threshold, notify=battery_charge_threshold_changed) # type: ignore

    def get_cpu_fan_table(self) -> List[List[int]]: return cast(List[List[int]], self._data['cpu_fan_table'])
    def set_cpu_fan_table(self, value: List[List[int]]): self._set_value('cpu_fan_table', value, self.cpu_fan_table_changed)
    cpu_fan_table = Property(list, get_cpu_fan_table, set_cpu_fan_table, notify=cpu_fan_table_changed) # type: ignore

    def get_gpu_fan_table(self) -> List[List[int]]: return cast(List[List[int]], self._data['gpu_fan_table'])
    def set_gpu_fan_table(self, value: List[List[int]]): self._set_value('gpu_fan_table', value, self.gpu_fan_table_changed)
    gpu_fan_table = Property(list, get_gpu_fan_table, set_gpu_fan_table, notify=gpu_fan_table_changed) # type: ignore


class AppState(QObject):
    """
    整个应用的顶层响应式状态对象。
    这是所有持久化和瞬时数据的唯一真实来源。
    """
    language_changed = Signal(str)
    start_on_boot_changed = Signal(bool)
    active_profile_changed = Signal(ProfileState)
    profiles_list_changed = Signal(list, str) # names, active_name
    
    cpu_temp_changed = Signal(float)
    gpu_temp_changed = Signal(float)
    cpu_fan_rpm_changed = Signal(int)
    gpu_fan_rpm_changed = Signal(int)
    applied_fan_mode_changed = Signal(str)
    applied_fan_speed_percent_changed = Signal(int)
    auto_fan_target_speed_percent_changed = Signal(int)
    applied_charge_policy_changed = Signal(str)
    applied_charge_threshold_changed = Signal(int)
    # 【修复】重命名，使其职责更清晰
    is_fan_control_panel_enabled_changed = Signal(bool)
    active_curve_type_changed = Signal(str)
    controller_status_message_changed = Signal(str)

    def __init__(self, path_manager: PathManager, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.paths = path_manager
        self._language: str = "en"
        self._start_on_boot: bool = False
        self._active_profile_name: Optional[str] = None
        self._profiles: Dict[str, ProfileState] = {}
        # 【新增】用于维护配置文件顺序的列表
        self.profile_order: List[str] = []
        self.window_geometry: Optional[str] = None

        self._cpu_temp: float = 0.0
        self._gpu_temp: float = 0.0
        self._cpu_fan_rpm: int = 0
        self._gpu_fan_rpm: int = 0
        self._applied_fan_mode: str = "auto"
        self._applied_fan_speed_percent: int = 0
        self._auto_fan_target_speed_percent: int = 0
        self._applied_charge_policy: str = "bios"
        self._applied_charge_threshold: int = 100
        # 【修复】重命名
        self._is_fan_control_panel_enabled: bool = True
        self._active_curve_type: str = "cpu"
        self._controller_status_message: str = ""

    def _set_value(self, field_name: str, value: Any, signal: Any):
        if getattr(self, field_name) != value:
            setattr(self, field_name, value)
            signal.emit(value)

    def get_language(self) -> str: return self._language
    def set_language(self, value: str): self._set_value('_language', value, self.language_changed)
    language = Property(str, get_language, set_language, notify=language_changed) # type: ignore

    def get_start_on_boot(self) -> bool: return self._start_on_boot
    def set_start_on_boot(self, value: bool): self._set_value('_start_on_boot', value, self.start_on_boot_changed)
    start_on_boot = Property(bool, get_start_on_boot, set_start_on_boot, notify=start_on_boot_changed) # type: ignore

    def get_active_profile(self) -> Optional[ProfileState]: return self._profiles.get(self._active_profile_name) if self._active_profile_name else None
    active_profile = Property(QObject, get_active_profile, notify=active_profile_changed) # type: ignore

    def get_active_profile_name(self) -> Optional[str]: return self._active_profile_name
    def set_active_profile_name(self, value: str):
        if self._active_profile_name != value and value in self._profiles:
            self._active_profile_name = value
            active_profile = self.get_active_profile()
            if active_profile:
                self.active_profile_changed.emit(active_profile)
            self.profiles_list_changed.emit(self.get_profile_names(), self._active_profile_name or "")
    active_profile_name = Property(str, get_active_profile_name, set_active_profile_name, notify=active_profile_changed) # type: ignore

    # 【修复】现在返回有序列表
    def get_profile_names(self) -> List[str]: return self.profile_order
    profile_names = Property(list, get_profile_names, notify=profiles_list_changed) # type: ignore
        
    def get_cpu_temp(self) -> float: return self._cpu_temp
    def set_cpu_temp(self, value: float): self._set_value('_cpu_temp', value, self.cpu_temp_changed)
    cpu_temp = Property(float, get_cpu_temp, set_cpu_temp, notify=cpu_temp_changed) # type: ignore

    def get_gpu_temp(self) -> float: return self._gpu_temp
    def set_gpu_temp(self, value: float): self._set_value('_gpu_temp', value, self.gpu_temp_changed)
    gpu_temp = Property(float, get_gpu_temp, set_gpu_temp, notify=gpu_temp_changed) # type: ignore

    def get_cpu_fan_rpm(self) -> int: return self._cpu_fan_rpm
    def set_cpu_fan_rpm(self, value: int): self._set_value('_cpu_fan_rpm', value, self.cpu_fan_rpm_changed)
    cpu_fan_rpm = Property(int, get_cpu_fan_rpm, set_cpu_fan_rpm, notify=cpu_fan_rpm_changed) # type: ignore

    def get_gpu_fan_rpm(self) -> int: return self._gpu_fan_rpm
    def set_gpu_fan_rpm(self, value: int): self._set_value('_gpu_fan_rpm', value, self.gpu_fan_rpm_changed)
    gpu_fan_rpm = Property(int, get_gpu_fan_rpm, set_gpu_fan_rpm, notify=gpu_fan_rpm_changed) # type: ignore
    
    def get_applied_fan_mode(self) -> str: return self._applied_fan_mode
    def set_applied_fan_mode(self, value: str): self._set_value('_applied_fan_mode', value, self.applied_fan_mode_changed)
    applied_fan_mode = Property(str, get_applied_fan_mode, set_applied_fan_mode, notify=applied_fan_mode_changed) # type: ignore

    def get_applied_fan_speed_percent(self) -> int: return self._applied_fan_speed_percent
    def set_applied_fan_speed_percent(self, value: int): self._set_value('_applied_fan_speed_percent', value, self.applied_fan_speed_percent_changed)
    applied_fan_speed_percent = Property(int, get_applied_fan_speed_percent, set_applied_fan_speed_percent, notify=applied_fan_speed_percent_changed) # type: ignore

    def get_auto_fan_target_speed_percent(self) -> int: return self._auto_fan_target_speed_percent
    def set_auto_fan_target_speed_percent(self, value: int): self._set_value('_auto_fan_target_speed_percent', value, self.auto_fan_target_speed_percent_changed)
    auto_fan_target_speed_percent = Property(int, get_auto_fan_target_speed_percent, set_auto_fan_target_speed_percent, notify=auto_fan_target_speed_percent_changed) # type: ignore

    def get_applied_charge_policy(self) -> str: return self._applied_charge_policy
    def set_applied_charge_policy(self, value: str): self._set_value('_applied_charge_policy', value, self.applied_charge_policy_changed)
    applied_charge_policy = Property(str, get_applied_charge_policy, set_applied_charge_policy, notify=applied_charge_policy_changed) # type: ignore
    
    def get_applied_charge_threshold(self) -> int: return self._applied_charge_threshold
    def set_applied_charge_threshold(self, value: int): self._set_value('_applied_charge_threshold', value, self.applied_charge_threshold_changed)
    applied_charge_threshold = Property(int, get_applied_charge_threshold, set_applied_charge_threshold, notify=applied_charge_threshold_changed) # type: ignore

    # 【修复】重命名
    def get_is_fan_control_panel_enabled(self) -> bool: return self._is_fan_control_panel_enabled
    def set_is_fan_control_panel_enabled(self, value: bool): self._set_value('_is_fan_control_panel_enabled', value, self.is_fan_control_panel_enabled_changed)
    is_fan_control_panel_enabled = Property(bool, get_is_fan_control_panel_enabled, set_is_fan_control_panel_enabled, notify=is_fan_control_panel_enabled_changed) # type: ignore

    def get_active_curve_type(self) -> str: return self._active_curve_type
    def set_active_curve_type(self, value: str): self._set_value('_active_curve_type', value, self.active_curve_type_changed)
    active_curve_type = Property(str, get_active_curve_type, set_active_curve_type, notify=active_curve_type_changed) # type: ignore

    def get_controller_status_message(self) -> str: return self._controller_status_message
    def set_controller_status_message(self, value: str): self._set_value('_controller_status_message', value, self.controller_status_message_changed)
    controller_status_message = Property(str, get_controller_status_message, set_controller_status_message, notify=controller_status_message_changed) # type: ignore
    
    def get_profile(self, name: str) -> Optional[ProfileState]:
        return self._profiles.get(name)
        
    def add_profile(self, name: str, profile: ProfileState):
        if name not in self._profiles:
            self._profiles[name] = profile
            self.profile_order.append(name) # 【新增】
            self.profiles_list_changed.emit(self.get_profile_names(), self.active_profile_name or "")
            
    def rename_profile(self, old_name: str, new_name: str):
        if old_name in self._profiles and new_name not in self._profiles:
            profile = self._profiles.pop(old_name)
            self._profiles[new_name] = profile
            # 【新增】更新顺序列表
            try:
                idx = self.profile_order.index(old_name)
                self.profile_order[idx] = new_name
            except ValueError:
                self.profile_order.append(new_name) # 作为后备
            
            if self.active_profile_name == old_name:
                self.set_active_profile_name(new_name)
            else:
                self.profiles_list_changed.emit(self.get_profile_names(), self.active_profile_name or "")

    # 【新增】删除配置文件的逻辑
    def delete_profile(self, name: str):
        if name in self._profiles and len(self._profiles) > 1:
            del self._profiles[name]
            if name in self.profile_order:
                self.profile_order.remove(name)
            
            if self.active_profile_name == name:
                # 如果删除的是活动配置文件，则激活列表中的第一个
                new_active_name = self.profile_order[0] if self.profile_order else None
                if new_active_name:
                    self.set_active_profile_name(new_active_name)
            else:
                self.profiles_list_changed.emit(self.get_profile_names(), self.active_profile_name or "")


    def get_profiles_for_config(self) -> Dict[str, Any]:
        return {name: profile.to_dict() for name, profile in self._profiles.items()}
        
    def load_profiles_from_config(self, profiles_data: Dict[str, Any], profile_order: List[str]):
        self._profiles.clear()
        self.profile_order = profile_order # 【新增】
        for name, profile_dict in profiles_data.items():
            profile = ProfileState(self)
            profile.from_dict(profile_dict)
            self._profiles[name] = profile