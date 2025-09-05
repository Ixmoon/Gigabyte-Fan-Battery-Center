# -*- coding: utf-8 -*-
"""
提供一个可复用的基础UI面板(BaseControlPanel)，用于统一创建和管理包含模式选择和滑块的控制区域。
该基类旨在减少FanControlPanel和BatteryControlPanel中的重复代码。
"""
from .qt import *
from .tooltip_manager import tooltip_manager
from tools.localization import tr
from core.state import AppState, ProfileState
from core.profile_manager import ProfileManager
from .EditableLabel import EditableLabel # 【新增】
from typing import Dict, Any, List, Tuple, Optional

class BaseControlPanel(QFrame):
    """
    一个可配置的基础QFrame，包含一组模式单选按钮和一个关联的滑块。
    它通过直接调用ProfileManager的方法来响应用户输入，并通过连接到
    AppState和ProfileState的信号来响应式地更新自身。
    """
    
    def __init__(self, config: Dict[str, Any], state: AppState, profile_manager: ProfileManager, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.config = config
        self.state = state
        self.profile_manager = profile_manager
        self._current_profile: Optional[ProfileState] = None
        
        self.mode_button_group: QButtonGroup
        self.mode_radios: Dict[str, QRadioButton] = {}
        self.slider: QSlider
        # 【修复】使用新的可编辑标签
        self.value_label: EditableLabel
        self.mode_label: QLabel
        self.slider_label: QLabel
        
        # 【新增】用于滑块值防抖的定时器
        self.slider_debounce_timer = QTimer(self)
        self.slider_debounce_timer.setSingleShot(True)
        self.slider_debounce_timer.setInterval(300) # 300ms延迟
        
        self._init_ui()
        self._connect_signals()
        
        self._on_active_profile_changed(self.state.get_active_profile())

    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5); layout.setSpacing(10)

        self.mode_label = QLabel(tr(self.config["mode_label_key"]), self)
        layout.addWidget(self.mode_label)

        self.mode_button_group = QButtonGroup(self)
        for mode_name, text_key in self.config["radio_configs"]:
            radio = QRadioButton(tr(text_key), self)
            self.mode_radios[mode_name] = radio
            self.mode_button_group.addButton(radio)
            layout.addWidget(radio)
        
        layout.addSpacerItem(QSpacerItem(20, 10, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))

        self.slider_label = QLabel(tr(self.config["slider_label_key"]), self)
        self.slider = QSlider(Qt.Orientation.Horizontal, self)
        self.slider.setRange(*self.config["slider_range"])

        # 【修复】实例化新的可编辑标签
        self.value_label = EditableLabel(unit=tr('percent_unit'), parent=self)
        self.value_label.setMinimumWidth(45)
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        
        layout.addWidget(self.slider_label)
        layout.addWidget(self.slider, 1)
        layout.addWidget(self.value_label)

        tooltip_manager.register(self.mode_label, self.config["mode_tooltip_key"])
        tooltip_manager.register(self.slider, self.config["slider_tooltip_key"])
        tooltip_manager.register(self.value_label, "editable_label_tooltip")

    def _connect_signals(self):
        # UI -> ProfileManager
        for mode_name, radio in self.mode_radios.items():
            radio.toggled.connect(lambda checked, name=mode_name: 
                self.profile_manager.update_active_profile_data(self.config["profile_mode_attr"], name) if checked else None)

        # 【修复】连接滑块和可编辑标签的信号
        self.slider.valueChanged.connect(self._on_slider_value_changed)
        self.slider_debounce_timer.timeout.connect(self._commit_slider_value)
        self.value_label.editingFinished.connect(self._commit_slider_value)

        # AppState -> UI
        self.state.active_profile_changed.connect(self._on_active_profile_changed)
        # 【修复】根据面板类型决定监听哪个启用信号
        if self.config.get("is_fan_control", False):
            self.state.is_fan_control_panel_enabled_changed.connect(self._on_global_panel_state_changed)

    # 【新增】处理滑块值变化的防抖逻辑
    @Slot(int)
    def _on_slider_value_changed(self, value: int):
        # 立即更新UI显示
        self.value_label.blockSignals(True)
        self.value_label.setValue(value)
        self.value_label.blockSignals(False)
        # 重启防抖定时器
        self.slider_debounce_timer.start()

    # 【新增】提交滑块或输入框的值到状态管理器
    @Slot()
    def _commit_slider_value(self):
        self.slider_debounce_timer.stop()
        current_value = self.slider.value()
        self.profile_manager.update_active_profile_data(self.config["profile_value_attr"], current_value)

    @Slot()
    def _on_global_panel_state_changed(self):
        if self._current_profile:
            current_mode = getattr(self._current_profile, f"get_{self.config['profile_mode_attr']}")()
            self._update_mode_display(current_mode)

    @Slot(ProfileState)
    def _on_active_profile_changed(self, profile: Optional[ProfileState]):
        if self._current_profile and self._current_profile != profile:
            try:
                getattr(self._current_profile, self.config["profile_mode_attr"] + "_changed").disconnect(self._update_mode_display)
                getattr(self._current_profile, self.config["profile_value_attr"] + "_changed").disconnect(self._update_value_display)
            except (AttributeError, RuntimeError): pass

        self._current_profile = profile
        if not profile: return

        getattr(profile, self.config["profile_mode_attr"] + "_changed").connect(self._update_mode_display)
        getattr(profile, self.config["profile_value_attr"] + "_changed").connect(self._update_value_display)
        
        self._update_mode_display(getattr(profile, f"get_{self.config['profile_mode_attr']}")())
        self._update_value_display(getattr(profile, f"get_{self.config['profile_value_attr']}")())

    @Slot(str)
    def _update_mode_display(self, mode: str):
        self.mode_button_group.blockSignals(True)
        try:
            if mode in self.mode_radios:
                self.mode_radios[mode].setChecked(True)
        finally:
            self.mode_button_group.blockSignals(False)
        
        is_custom_mode = (mode == self.config["custom_mode_name"])
        
        # 【修复】根据面板类型决定启用逻辑
        is_slider_enabled = False
        if self.config.get("is_fan_control", False):
            # 风扇面板依赖全局状态
            is_slider_enabled = self.state.get_is_fan_control_panel_enabled() and is_custom_mode
        else:
            # 电池面板只依赖自身模式
            is_slider_enabled = is_custom_mode

        self.slider_label.setEnabled(is_slider_enabled)
        self.slider.setEnabled(is_slider_enabled)
        self.value_label.setEnabled(is_slider_enabled)

    @Slot(int)
    def _update_value_display(self, value: int):
        # 更新滑块
        self.slider.blockSignals(True)
        self.slider.setValue(value)
        self.slider.blockSignals(False)
        # 更新标签
        self.value_label.blockSignals(True)
        self.value_label.setValue(value)
        self.value_label.blockSignals(False)

    def retranslate_ui(self):
        self.mode_label.setText(tr(self.config["mode_label_key"]))
        for mode_name, text_key in self.config["radio_configs"]:
            if mode_name in self.mode_radios:
                self.mode_radios[mode_name].setText(tr(text_key))
        
        self.slider_label.setText(tr(self.config["slider_label_key"]))
        self.value_label.unit = tr('percent_unit')
        self.value_label.setValue(self.slider.value())