# -*- coding: utf-8 -*-
"""
一个轻量级、基于QPainter的画布，用于显示和编辑风扇曲线。
【最终优化】此版本实现了智能局部绘制和绘图对象缓存，以彻底解决CPU占用激增问题。
【体验优化】实现了水平和垂直方向的智能联动调整，当拖拽点时，会自动调整相邻点以提供完全自由、流畅的编辑体验。
"""

from .qt import *
from typing import List, Optional, Any, Dict, Tuple, cast

from core.interpolation import PchipInterpolator, linspace, clip, interp
from core.profile_manager import ProfileManager
from config.settings import (
    MAX_TEMP_C, MIN_FAN_PERCENT, MAX_FAN_PERCENT,
    MIN_CURVE_POINTS, MIN_POINTS_FOR_INTERPOLATION, TEMP_READ_ERROR_VALUE,
    DEFAULT_MIN_DISPLAY_TEMP_C
)
from tools.localization import tr
from core.state import AppState, ProfileState
from .tooltip_manager import tooltip_manager

# 类型提示
FanTable = List[List[int]]
CurveType = str  # 'cpu' 或 'gpu'

class LightweightCurveCanvas(QWidget):
    """基于QPainter的交互式风扇曲线编辑画布。"""
    point_dragged = Signal(CurveType, int, float, float)
    transient_status_signal = Signal(str, int)

    def __init__(self, state: AppState, profile_manager: ProfileManager, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.state = state
        self.profile_manager = profile_manager
        self._current_profile: Optional[ProfileState] = None
        self.setMinimumSize(400, 250)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.cpu_curve_data: FanTable = []
        self.gpu_curve_data: FanTable = []
        self.active_curve_type: CurveType = 'cpu'
        self._appearance_settings: Dict[str, Any] = {}
        self._dragging_point_index: Optional[int] = None
        self._hovered_point_index: Optional[int] = None
        self._plot_area = QRectF()
        self._margins = {'left': 55, 'top': 20, 'right': 20, 'bottom': 35}
        
        # 【优化】缓存绘图对象
        self._background_pixmap: Optional[QPixmap] = None
        self._cached_cpu_curve_poly: Optional[QPolygonF] = None
        self._cached_gpu_curve_poly: Optional[QPolygonF] = None
        self._last_cpu_indicator_region = QRegion()
        self._last_gpu_indicator_region = QRegion()
        
        self._cpu_interpolator: Optional[PchipInterpolator] = None
        self._gpu_interpolator: Optional[PchipInterpolator] = None

        tooltip_manager.register(self, "canvas_tooltip")
        self._connect_signals()
        
        self._on_active_profile_changed(self.state.get_active_profile())
        self.set_active_curve(self.state.get_active_curve_type())
        self.update_temp_indicators(self.state.get_cpu_temp(), self.state.get_gpu_temp())
        self.setEnabled(self.state.get_is_fan_control_panel_enabled())

    def _connect_signals(self):
        """订阅AppState和ProfileState的信号。"""
        self.state.active_profile_changed.connect(self._on_active_profile_changed)
        self.state.active_curve_type_changed.connect(self.set_active_curve)
        self.state.cpu_temp_changed.connect(lambda t: self.update_temp_indicators(cpu_temp=t))
        self.state.gpu_temp_changed.connect(lambda t: self.update_temp_indicators(gpu_temp=t))
        self.state.is_fan_control_panel_enabled_changed.connect(self.setEnabled)

    @Slot(ProfileState)
    def _on_active_profile_changed(self, profile: Optional[ProfileState]):
        """当活动配置文件改变时，安全地重新连接信号。"""
        if self._current_profile and self._current_profile != profile:
            try:
                self._current_profile.cpu_fan_table_changed.disconnect(self._on_cpu_curve_data_changed)
                self._current_profile.gpu_fan_table_changed.disconnect(self._on_gpu_curve_data_changed)
                self._current_profile.appearance_changed.disconnect(self._on_appearance_changed)
            except (AttributeError, RuntimeError): pass

        self._current_profile = profile
        if not profile: return
        
        profile.cpu_fan_table_changed.connect(self._on_cpu_curve_data_changed)
        profile.gpu_fan_table_changed.connect(self._on_gpu_curve_data_changed)
        profile.appearance_changed.connect(self._on_appearance_changed)
        
        self._on_cpu_curve_data_changed(profile.cpu_fan_table)
        self._on_gpu_curve_data_changed(profile.gpu_fan_table)
        self._on_appearance_changed()

    @Slot(list)
    def _on_cpu_curve_data_changed(self, data: FanTable):
        self.cpu_curve_data = self._validate_and_sort(data)
        self._cpu_interpolator = None
        self._recache_curves() # 【优化】数据变化时，重新缓存曲线
        self.update()

    @Slot(list)
    def _on_gpu_curve_data_changed(self, data: FanTable):
        self.gpu_curve_data = self._validate_and_sort(data)
        self._gpu_interpolator = None
        self._recache_curves() # 【优化】数据变化时，重新缓存曲线
        self.update()

    @Slot()
    def _on_appearance_changed(self):
        profile = self.state.get_active_profile()
        if profile:
            self._appearance_settings = profile.to_dict()
            self._background_pixmap = None # 外观变化时，背景需要重绘
            self._recache_curves() # 曲线颜色可能变化，重新缓存
            self.update()

    def _get_setting(self, key: str, default_override: Any = None) -> Any:
        return self._appearance_settings.get(key, default_override)

    def _update_plot_area(self):
        rect = self.rect()
        self._plot_area = QRectF(
            self._margins['left'], self._margins['top'],
            rect.width() - self._margins['left'] - self._margins['right'],
            rect.height() - self._margins['top'] - self._margins['bottom']
        )

    def _data_to_widget_coords(self, temp: float, speed: float) -> QPointF:
        min_temp = self._get_setting('min_display_temp_c', DEFAULT_MIN_DISPLAY_TEMP_C)
        temp_range = MAX_TEMP_C - min_temp
        
        if temp_range <= 0: x_ratio = 0.0
        else: x_ratio = (clip(temp, min_temp, MAX_TEMP_C) - min_temp) / temp_range

        x = self._plot_area.left() + x_ratio * self._plot_area.width()
        y = self._plot_area.bottom() - ((speed - MIN_FAN_PERCENT) / (MAX_FAN_PERCENT - MIN_FAN_PERCENT)) * self._plot_area.height()
        return QPointF(x, y)

    def _widget_to_data_coords(self, point: QPointF) -> Tuple[float, float]:
        min_temp = self._get_setting('min_display_temp_c', DEFAULT_MIN_DISPLAY_TEMP_C)
        temp_range = MAX_TEMP_C - min_temp
        
        if self._plot_area.width() == 0: temp = min_temp
        else: temp = min_temp + ((point.x() - self._plot_area.left()) / self._plot_area.width()) * temp_range

        speed = MIN_FAN_PERCENT + ((self._plot_area.bottom() - point.y()) / self._plot_area.height()) * (MAX_FAN_PERCENT - MIN_FAN_PERCENT)
        return temp, speed

    def resizeEvent(self, event: QResizeEvent):
        self._update_plot_area()
        self._background_pixmap = None # 尺寸变化时，所有缓存失效
        self._recache_curves()
        super().resizeEvent(event)

    def paintEvent(self, event: QPaintEvent):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        if self._background_pixmap is None or self._background_pixmap.size() != self.size():
            self._background_pixmap = QPixmap(self.size())
            self._background_pixmap.fill(Qt.GlobalColor.transparent)
            bg_painter = QPainter(self._background_pixmap)
            bg_painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            self._draw_background(bg_painter)
            self._draw_grid_and_labels(bg_painter)
            bg_painter.end()
        
        painter.drawPixmap(0, 0, self._background_pixmap)
        
        self._draw_single_curve(painter, self.gpu_curve_data, 'gpu', self._cached_gpu_curve_poly)
        self._draw_single_curve(painter, self.cpu_curve_data, 'cpu', self._cached_cpu_curve_poly)
        
        self._draw_temp_indicators(painter)
        painter.end()

    def _draw_background(self, painter: QPainter):
        bg_color = QColor(self._get_setting('figure_bg_color', '#33373B'))
        axes_color = QColor(self._get_setting('axes_bg_color', '#2A2D30'))
        painter.fillRect(self.rect(), bg_color)
        painter.fillRect(self._plot_area, axes_color)

    def _draw_grid_and_labels(self, painter: QPainter):
        grid_color = QColor(self._get_setting('grid_color', '#555555'))
        label_color = QColor(self._get_setting('axes_label_color', '#E0E0E0'))
        pen = QPen(grid_color); pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        font = QFont("Segoe UI", 8); painter.setFont(font)
        
        min_temp = self._get_setting('min_display_temp_c', DEFAULT_MIN_DISPLAY_TEMP_C)
        
        for temp in range(min_temp, MAX_TEMP_C + 1, 10):
            if temp == min_temp and min_temp % 10 != 0:
                self._draw_temp_grid_line(painter, min_temp, pen, label_color)
            if temp % 10 == 0:
                 self._draw_temp_grid_line(painter, temp, pen, label_color)

        for speed in range(MIN_FAN_PERCENT, MAX_FAN_PERCENT + 1, 10):
            p = self._data_to_widget_coords(min_temp, speed)
            painter.setPen(pen)
            painter.drawLine(int(self._plot_area.left()), int(p.y()), int(self._plot_area.right()), int(p.y()))
            painter.setPen(label_color)
            painter.drawText(QRectF(self._plot_area.left() - 50, p.y() - 10, 45, 20), Qt.AlignmentFlag.AlignRight, f"{speed}{tr('percent_unit')}")

    def _draw_temp_grid_line(self, painter: QPainter, temp: int, grid_pen: QPen, label_color: QColor):
        p = self._data_to_widget_coords(temp, MIN_FAN_PERCENT)
        painter.setPen(grid_pen)
        painter.drawLine(int(p.x()), int(self._plot_area.top()), int(p.x()), int(self._plot_area.bottom()))
        painter.setPen(label_color)
        painter.drawText(QRectF(p.x() - 20, self._plot_area.bottom() + 5, 40, 20), Qt.AlignmentFlag.AlignCenter, f"{temp}{tr('celsius_unit')}")

    def _draw_single_curve(self, painter: QPainter, data: FanTable, curve_type: CurveType, cached_poly: Optional[QPolygonF]):
        if not data: return
        is_active = (self.active_curve_type == curve_type)
        line_color = QColor(self._get_setting(f"{curve_type}_curve_color"))
        point_color = QColor(self._get_setting("point_color_active"))
        line_width = self._get_setting("line_width_active") if is_active else self._get_setting("line_width_inactive")
        alpha = self._get_setting("alpha_active") if is_active else self._get_setting("alpha_inactive")
        point_size = self._get_setting("point_size_active")
        line_color.setAlphaF(alpha)
        pen = QPen(line_color, line_width); painter.setPen(pen)
        
        if cached_poly:
            painter.drawPolyline(cached_poly)
        
        if is_active:
            painter.setPen(point_color); painter.setBrush(QBrush(point_color))
            for i, p_data in enumerate(data):
                p_widget = self._data_to_widget_coords(p_data[0], p_data[1])
                size = point_size * 1.5 if i == self._hovered_point_index else point_size
                painter.drawEllipse(p_widget, size / 2, size / 2)

    @Slot(str)
    def set_active_curve(self, curve_type: CurveType):
        if self.active_curve_type != curve_type:
            self.active_curve_type = curve_type
            self.update()

    @Slot()
    def update_temp_indicators(self, cpu_temp: Optional[float] = None, gpu_temp: Optional[float] = None):
        update_region = QRegion()
        
        if cpu_temp is not None:
            update_region += self._last_cpu_indicator_region
            new_region = self._calculate_indicator_region(cpu_temp, 'cpu')
            update_region += new_region
            self._last_cpu_indicator_region = new_region
            
        if gpu_temp is not None:
            update_region += self._last_gpu_indicator_region
            new_region = self._calculate_indicator_region(gpu_temp, 'gpu')
            update_region += new_region
            self._last_gpu_indicator_region = new_region

        if not update_region.isEmpty():
            self.update(update_region)

    def _calculate_indicator_region(self, temp: float, curve_type: CurveType) -> QRegion:
        if temp == TEMP_READ_ERROR_VALUE or not self.get_curve_data(curve_type):
            return QRegion()
        
        speed = self._get_target_speed_for_indicator(temp, curve_type)
        min_temp = self._get_setting('min_display_temp_c', DEFAULT_MIN_DISPLAY_TEMP_C)
        
        if speed != -1 and temp >= min_temp:
            p = self._data_to_widget_coords(temp, speed)
            horiz_rect = QRect(int(self._plot_area.left()), int(p.y() - 1), int(p.x() - self._plot_area.left()), 3)
            vert_rect = QRect(int(p.x() - 1), int(p.y()), 3, int(self._plot_area.bottom() - p.y()))
            return QRegion(horiz_rect).united(QRegion(vert_rect))
            
        return QRegion()

    def _draw_temp_indicators(self, painter: QPainter):
        cpu_temp = self.state.get_cpu_temp()
        gpu_temp = self.state.get_gpu_temp()
        if cpu_temp != TEMP_READ_ERROR_VALUE and self.cpu_curve_data:
            speed = self._get_target_speed_for_indicator(cpu_temp, 'cpu')
            color = QColor(self._get_setting("cpu_temp_indicator_color"))
            self._draw_indicator_lines(painter, cpu_temp, speed, color)
        if gpu_temp != TEMP_READ_ERROR_VALUE and self.gpu_curve_data:
            speed = self._get_target_speed_for_indicator(gpu_temp, 'gpu')
            color = QColor(self._get_setting("gpu_temp_indicator_color"))
            self._draw_indicator_lines(painter, gpu_temp, speed, color)

    def _draw_indicator_lines(self, painter: QPainter, temp: float, speed: int, color: QColor):
        min_temp = self._get_setting('min_display_temp_c', DEFAULT_MIN_DISPLAY_TEMP_C)
        if speed != -1 and temp >= min_temp:
            p = self._data_to_widget_coords(temp, speed)
            pen = QPen(color, 1.5, Qt.PenStyle.DotLine); painter.setPen(pen)
            painter.drawLine(int(p.x()), int(self._plot_area.bottom()), int(p.x()), int(p.y()))
            painter.drawLine(int(self._plot_area.left()), int(p.y()), int(p.x()), int(p.y()))

    def _get_target_speed_for_indicator(self, temperature: float, curve_type: CurveType) -> int:
        table = self.get_curve_data(curve_type)
        if not table: return -1
        interpolator = self._get_cached_interpolator(curve_type)
        if interpolator:
            return int(round(cast(float, clip(cast(float, interpolator(temperature)), MIN_FAN_PERCENT, MAX_FAN_PERCENT))))
        return int(round(interp(temperature, [p[0] for p in table], [p[1] for p in table])))

    def _get_cached_interpolator(self, curve_type: CurveType) -> Optional[PchipInterpolator]:
        attr_name = f"_{curve_type}_interpolator"
        if getattr(self, attr_name): return getattr(self, attr_name)
        
        table = self.get_curve_data(curve_type)
        unique_points = sorted(list({tuple(p) for p in table}), key=lambda x: x[0])
        if len(unique_points) < MIN_POINTS_FOR_INTERPOLATION: return None
        
        try:
            interpolator = PchipInterpolator([float(p[0]) for p in unique_points], [float(p[1]) for p in unique_points], extrapolate=False)
            setattr(self, attr_name, interpolator)
            return interpolator
        except Exception: return None

    def _recache_curves(self):
        self._cached_cpu_curve_poly = self._create_curve_polygon(self.cpu_curve_data, 'cpu')
        self._cached_gpu_curve_poly = self._create_curve_polygon(self.gpu_curve_data, 'gpu')

    def _create_curve_polygon(self, data: FanTable, curve_type: CurveType) -> Optional[QPolygonF]:
        if not data: return None
        interpolator = self._get_cached_interpolator(curve_type)
        if not interpolator: return None
        
        spline_points = self._get_setting("spline_points", 100)
        temps_smooth = linspace(interpolator.x[0], interpolator.x[-1], spline_points)
        speeds_smooth = clip(cast(List[float], interpolator(temps_smooth)), MIN_FAN_PERCENT, MAX_FAN_PERCENT)
        points = [self._data_to_widget_coords(t, s) for t, s in zip(temps_smooth, cast(List[float], speeds_smooth))]
        return QPolygonF(points)

    def get_curve_data(self, curve_type: CurveType) -> FanTable:
        return self.cpu_curve_data if curve_type == 'cpu' else self.gpu_curve_data

    def retranslate_ui(self):
        self._background_pixmap = None
        self.update()

    def _validate_and_sort(self, table: FanTable) -> FanTable:
        min_temp = self._get_setting('min_display_temp_c', DEFAULT_MIN_DISPLAY_TEMP_C) if self._appearance_settings else 0
        valid = [[max(min_temp, min(MAX_TEMP_C, p[0])), max(MIN_FAN_PERCENT, min(MAX_FAN_PERCENT, p[1]))] for p in table if isinstance(p, list) and len(p) == 2]
        return sorted(valid, key=lambda x: x[0])

    def _update_curve_in_state(self, curve_type: CurveType, data: FanTable):
        self.profile_manager.set_curve_data(curve_type, data)
        self.transient_status_signal.emit(tr("saving_config"), 2000)
    
    def mousePressEvent(self, event: QMouseEvent):
        pos = event.position()
        if not self._plot_area.contains(pos): return
        point_info = self._get_point_at_event(pos)
        if event.button() == Qt.MouseButton.LeftButton and point_info:
            self._dragging_point_index = point_info[1]
        elif event.button() == Qt.MouseButton.RightButton and point_info:
            self._delete_point(*point_info)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        pos = event.position()
        if self._plot_area.contains(pos) and event.button() == Qt.MouseButton.LeftButton and self._get_point_at_event(pos) is None:
            self._add_point(pos)

    def mouseMoveEvent(self, event: QMouseEvent):
        pos = event.position()
        if self._dragging_point_index is not None:
            self._drag_point(pos)
        else:
            point_info = self._get_point_at_event(pos)
            new_hover = point_info[1] if point_info else None
            if new_hover != self._hovered_point_index:
                self._hovered_point_index = new_hover
                self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self._dragging_point_index is not None and event.button() == Qt.MouseButton.LeftButton:
            self._dragging_point_index = None
            data = self.get_curve_data(self.active_curve_type)
            data.sort(key=lambda p: p[0])
            self._update_curve_in_state(self.active_curve_type, data)
            self.update()

    def _get_point_at_event(self, pos: QPointF) -> Optional[Tuple[CurveType, int]]:
        data = self.get_curve_data(self.active_curve_type)
        radius = self._get_setting("curve_point_picker_radius", 8.0)
        for i, p_data in enumerate(data):
            p_widget = self._data_to_widget_coords(p_data[0], p_data[1])
            if (pos.x() - p_widget.x())**2 + (pos.y() - p_widget.y())**2 < radius**2:
                return (self.active_curve_type, i)
        return None

    def _add_point(self, pos: QPointF):
        temp, speed = self._widget_to_data_coords(pos)
        data = self.get_curve_data(self.active_curve_type)
        data.append([int(round(temp)), int(round(speed))])
        data.sort(key=lambda p: p[0])
        for i in range(1, len(data)):
            if data[i][1] < data[i-1][1]:
                data[i][1] = data[i-1][1]
        
        setattr(self, f"_{self.active_curve_type}_interpolator", None)
        self._update_curve_in_state(self.active_curve_type, data)
        self.update()

    def _delete_point(self, curve_type: CurveType, index: int):
        data = self.get_curve_data(curve_type)
        if len(data) > MIN_CURVE_POINTS:
            del data[index]
            setattr(self, f"_{curve_type}_interpolator", None)
            self._update_curve_in_state(curve_type, data)
            self.update()

    def _drag_point(self, pos: QPointF):
        """【最终优化】实现水平和垂直方向的完全自由、智能联动的拖拽。"""
        data = self.get_curve_data(self.active_curve_type)
        idx = self._dragging_point_index
        if idx is None: return
        
        temp, speed = self._widget_to_data_coords(pos)
        
        # 1. 应用画布边界限制
        min_temp = self._get_setting('min_display_temp_c', DEFAULT_MIN_DISPLAY_TEMP_C)
        temp = max(min_temp, min(MAX_TEMP_C, temp))
        speed = max(MIN_FAN_PERCENT, min(MAX_FAN_PERCENT, speed))
        
        # 2. 更新当前点的位置
        data[idx] = [int(round(temp)), int(round(speed))]
        
        # 3. 【核心】实时强制水平和垂直的连锁反应
        self._enforce_temperature_separation_during_drag(data, idx)
        self._enforce_speed_monotonicity_during_drag(data, idx)
        
        # 4. 更新状态并重绘
        setattr(self, f"_{self.active_curve_type}_interpolator", None)
        self._recache_curves()
        self.point_dragged.emit(self.active_curve_type, idx, temp, speed)
        self.update()

    def _enforce_speed_monotonicity_during_drag(self, data: FanTable, dragged_index: int):
        """实时强制风扇速度的单调性（只能增加或持平）。"""
        # 向前连锁（处理向下拖动）
        for i in range(dragged_index, 0, -1):
            if data[i][1] < data[i-1][1]:
                data[i-1][1] = data[i][1]
        
        # 向后连锁（处理向上拖动）
        for i in range(dragged_index, len(data) - 1):
            if data[i][1] > data[i+1][1]:
                data[i+1][1] = data[i][1]

    def _enforce_temperature_separation_during_drag(self, data: FanTable, dragged_index: int):
        """实时强制温度点的最小间距和顺序。"""
        min_temp = self._get_setting('min_display_temp_c', DEFAULT_MIN_DISPLAY_TEMP_C)
        
        # 向后连锁（处理向右拖动，推开右边的点）
        for i in range(dragged_index, len(data) - 1):
            if data[i+1][0] <= data[i][0]:
                new_temp = min(MAX_TEMP_C, data[i][0] + 1)
                data[i+1][0] = new_temp
        
        # 向前连锁（处理向左拖动，推开左边的点）
        for i in range(dragged_index, 0, -1):
            if data[i-1][0] >= data[i][0]:
                new_temp = max(min_temp, data[i][0] - 1)
                data[i-1][0] = new_temp