# gui/lightweight_curve_canvas.py
# -*- coding: utf-8 -*-
"""
A lightweight, QPainter-based canvas for displaying and editing fan curves.
This replaces the Matplotlib-based CurveCanvas to reduce executable size.
"""

from .qt import (
    QWidget, QPainter, QColor, QPen, QBrush, QPointF, QRectF,
    Signal, Qt, QMouseEvent, QResizeEvent, QMessageBox, QFont, QPolygonF,
    QSizePolicy, QPixmap
)
from typing import List, Optional, Any, Dict, Tuple
import math

from core.interpolation import PchipInterpolator, linspace, clip, interp
from config.settings import (
    MIN_TEMP_C, MAX_TEMP_C, MIN_FAN_PERCENT, MAX_FAN_PERCENT,
    MIN_CURVE_POINTS, MIN_POINTS_FOR_INTERPOLATION, TEMP_READ_ERROR_VALUE,
    DEFAULT_PROFILE_SETTINGS
)
from tools.localization import tr

# Type Hinting
FanTable = List[List[int]]
CurveType = str  # 'cpu' or 'gpu'

class LightweightCurveCanvas(QWidget):
    """QPainter-based canvas for interactive fan curve editing."""

    point_dragged = Signal(CurveType, int, float, float)
    curve_changed = Signal(CurveType)
    point_selected = Signal(CurveType, int)

    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        self.setMinimumSize(400, 250)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Internal state
        self.cpu_curve_data: FanTable = []
        self.gpu_curve_data: FanTable = []
        self.active_curve_type: CurveType = 'cpu'
        self._appearance_settings: Dict[str, Any] = DEFAULT_PROFILE_SETTINGS.copy()

        # Interaction state
        self._dragging_point_index: Optional[int] = None
        self._selected_point_index: Optional[int] = None
        self._hovered_point_index: Optional[int] = None
        self._dragging_curve_type: Optional[CurveType] = None

        # Status indicators data
        self.cpu_temp: float = TEMP_READ_ERROR_VALUE
        self.gpu_temp: float = TEMP_READ_ERROR_VALUE

        # Plot area definition
        self._plot_area = QRectF()
        self._margins = {'left': 55, 'top': 20, 'right': 20, 'bottom': 35}

        # Performance caches
        self._background_pixmap: Optional[QPixmap] = None
        self._cpu_interpolator: Optional[PchipInterpolator] = None
        self._gpu_interpolator: Optional[PchipInterpolator] = None

    def _get_setting(self, key: str, default_override: Any = None) -> Any:
        """Safely gets an appearance setting."""
        return self._appearance_settings.get(key, DEFAULT_PROFILE_SETTINGS.get(key, default_override))

    def _update_plot_area(self):
        """Calculates the drawing area for the plot based on margins."""
        rect = self.rect()
        self._plot_area = QRectF(
            self._margins['left'],
            self._margins['top'],
            rect.width() - self._margins['left'] - self._margins['right'],
            rect.height() - self._margins['top'] - self._margins['bottom']
        )

    def _data_to_widget_coords(self, temp: float, speed: float) -> QPointF:
        """Converts data coordinates (temp, speed) to widget coordinates."""
        x_range = MAX_TEMP_C - MIN_TEMP_C
        y_range = MAX_FAN_PERCENT - MIN_FAN_PERCENT
        
        x = self._plot_area.left() + ((temp - MIN_TEMP_C) / x_range) * self._plot_area.width()
        y = self._plot_area.bottom() - ((speed - MIN_FAN_PERCENT) / y_range) * self._plot_area.height()
        
        return QPointF(x, y)

    def _widget_to_data_coords(self, point: QPointF) -> Tuple[float, float]:
        """Converts widget coordinates to data coordinates (temp, speed)."""
        x_range = MAX_TEMP_C - MIN_TEMP_C
        y_range = MAX_FAN_PERCENT - MIN_FAN_PERCENT

        temp = MIN_TEMP_C + ((point.x() - self._plot_area.left()) / self._plot_area.width()) * x_range
        speed = MIN_FAN_PERCENT + ((self._plot_area.bottom() - point.y()) / self._plot_area.height()) * y_range
        
        return temp, speed

    def resizeEvent(self, event: QResizeEvent):
        """Handle widget resize."""
        self._update_plot_area()
        self._background_pixmap = None # Invalidate background cache
        super().resizeEvent(event)

    def paintEvent(self, event):
        """Main drawing method."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Use cached background if available
        if self._background_pixmap is None:
            self._background_pixmap = QPixmap(self.size())
            self._background_pixmap.fill(Qt.GlobalColor.transparent)
            bg_painter = QPainter(self._background_pixmap)
            bg_painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            self._draw_background(bg_painter)
            self._draw_grid_and_labels(bg_painter)
            bg_painter.end()
        
        painter.drawPixmap(0, 0, self._background_pixmap)
        
        # Draw dynamic elements
        self._draw_single_curve(painter, self.gpu_curve_data, 'gpu')
        self._draw_single_curve(painter, self.cpu_curve_data, 'cpu')
        self._draw_temp_indicators(painter)
        self._draw_legend(painter)

        painter.end()

    def _draw_legend(self, painter: QPainter):
        """Draws a legend for the curves."""
        font = QFont("Segoe UI", 9, QFont.Weight.Bold)
        painter.setFont(font)
        
        cpu_color = QColor(self._get_setting("CPU_CURVE_COLOR"))
        gpu_color = QColor(self._get_setting("GPU_CURVE_COLOR"))
        
        y_pos = self._plot_area.top() + 20
        
        if self.cpu_curve_data:
            painter.setPen(cpu_color)
            painter.drawText(QPointF(self._plot_area.right() - 80, y_pos), f"CPU")
            y_pos += 20
        
        if self.gpu_curve_data:
            painter.setPen(gpu_color)
            painter.drawText(QPointF(self._plot_area.right() - 80, y_pos), f"GPU")

    def _draw_background(self, painter: QPainter):
        """Draws the plot background."""
        bg_color = QColor(self._get_setting('FIGURE_BG_COLOR', '#33373B'))
        axes_color = QColor(self._get_setting('AXES_BG_COLOR', '#2A2D30'))
        
        painter.fillRect(self.rect(), bg_color)
        painter.fillRect(self._plot_area, axes_color)

    def _draw_grid_and_labels(self, painter: QPainter):
        """Draws the grid lines and axis labels."""
        grid_color = QColor(self._get_setting('GRID_COLOR', '#555555'))
        label_color = QColor(self._get_setting('AXES_LABEL_COLOR', '#E0E0E0'))
        
        pen = QPen(grid_color)
        pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        
        font = QFont("Segoe UI", 8)
        painter.setFont(font)

        # Vertical grid lines and temp labels
        for temp in range(MIN_TEMP_C, MAX_TEMP_C + 1, 10):
            p = self._data_to_widget_coords(temp, MIN_FAN_PERCENT)
            painter.drawLine(p.x(), self._plot_area.top(), p.x(), self._plot_area.bottom())
            painter.setPen(label_color)
            painter.drawText(QRectF(p.x() - 20, self._plot_area.bottom() + 5, 40, 20), Qt.AlignmentFlag.AlignCenter, f"{temp}{tr('celsius_unit')}")
            painter.setPen(pen)

        # Horizontal grid lines and speed labels
        for speed in range(MIN_FAN_PERCENT, MAX_FAN_PERCENT + 1, 10):
            p = self._data_to_widget_coords(MIN_TEMP_C, speed)
            painter.drawLine(self._plot_area.left(), p.y(), self._plot_area.right(), p.y())
            painter.setPen(label_color)
            painter.drawText(QRectF(self._plot_area.left() - 50, p.y() - 10, 45, 20), Qt.AlignmentFlag.AlignRight, f"{speed}{tr('percent_unit')}")
            painter.setPen(pen)

    def _draw_single_curve(self, painter: QPainter, data: FanTable, curve_type: CurveType):
        """Draws a single curve (line and points)."""
        if not data:
            return

        is_active = (self.active_curve_type == curve_type)
        
        # Get appearance settings
        line_color_hex = self._get_setting("CPU_CURVE_COLOR") if curve_type == 'cpu' else self._get_setting("GPU_CURVE_COLOR")
        line_color = QColor(line_color_hex)
        point_color = QColor(self._get_setting("POINT_COLOR_ACTIVE"))
        line_width = self._get_setting("LINE_WIDTH_ACTIVE") if is_active else self._get_setting("LINE_WIDTH_INACTIVE")
        alpha = self._get_setting("ALPHA_ACTIVE") if is_active else self._get_setting("ALPHA_INACTIVE")
        point_size = self._get_setting("POINT_SIZE_ACTIVE")

        line_color.setAlphaF(alpha)
        
        # Draw the curve line
        pen = QPen(line_color, line_width)
        painter.setPen(pen)
        
        points = [self._data_to_widget_coords(p[0], p[1]) for p in data]
        
        # Interpolate for smooth curve
        if len(data) >= MIN_POINTS_FOR_INTERPOLATION:
            try:
                interpolator = self._get_cached_interpolator(curve_type)
                if interpolator:
                    spline_points = self._get_setting("SPLINE_POINTS", 100)
                    temps_smooth = linspace(interpolator.x[0], interpolator.x[-1], spline_points)
                    speeds_smooth = clip(interpolator(temps_smooth), MIN_FAN_PERCENT, MAX_FAN_PERCENT)
                    
                    smooth_points = [self._data_to_widget_coords(t, s) for t, s in zip(temps_smooth, speeds_smooth)]
                    poly = QPolygonF(smooth_points)
                    painter.drawPolyline(poly)
                else:
                    # Not enough unique points for interpolation
                    painter.drawPolyline(QPolygonF(points))

            except Exception:
                painter.drawPolyline(QPolygonF(points)) # Fallback to linear on any error
        else:
            painter.drawPolyline(QPolygonF(points))

        # Draw points for active curve
        if is_active:
            painter.setPen(point_color)
            painter.setBrush(QBrush(point_color))
            for i, p in enumerate(points):
                size = point_size
                if i == self._hovered_point_index:
                    size *= 1.5 # Make hovered point larger
                painter.drawEllipse(p, size / 2, size / 2)

    # --- Public Methods ---
    def set_active_curve(self, curve_type: CurveType):
        if curve_type in ['cpu', 'gpu'] and self.active_curve_type != curve_type:
            self.active_curve_type = curve_type
            self.update()

    def update_plot(self, cpu_data: FanTable, gpu_data: FanTable):
        new_cpu_data = self._validate_and_sort(cpu_data)
        if new_cpu_data != self.cpu_curve_data:
            self.cpu_curve_data = new_cpu_data
            self._invalidate_interpolator_cache('cpu')

        new_gpu_data = self._validate_and_sort(gpu_data)
        if new_gpu_data != self.gpu_curve_data:
            self.gpu_curve_data = new_gpu_data
            self._invalidate_interpolator_cache('gpu')
            
        self.update()

    def update_temp_indicators(self, cpu_temp: float, gpu_temp: float):
        self.cpu_temp = cpu_temp
        self.gpu_temp = gpu_temp
        self.update()

    def _draw_temp_indicators(self, painter: QPainter):
        # CPU Indicator
        if self.cpu_temp != TEMP_READ_ERROR_VALUE and self.cpu_curve_data:
            cpu_target_speed = self._get_target_speed_for_indicator(self.cpu_temp, 'cpu')
            if cpu_target_speed != -1:
                p = self._data_to_widget_coords(self.cpu_temp, cpu_target_speed)
                color = QColor(self._get_setting("CPU_TEMP_INDICATOR_COLOR"))
                pen = QPen(color, 1.5, Qt.PenStyle.DotLine)
                painter.setPen(pen)
                painter.drawLine(p.x(), self._plot_area.bottom(), p.x(), p.y())
                painter.drawLine(self._plot_area.left(), p.y(), p.x(), p.y())

        # GPU Indicator
        if self.gpu_temp != TEMP_READ_ERROR_VALUE and self.gpu_curve_data:
            gpu_target_speed = self._get_target_speed_for_indicator(self.gpu_temp, 'gpu')
            if gpu_target_speed != -1:
                p = self._data_to_widget_coords(self.gpu_temp, gpu_target_speed)
                color = QColor(self._get_setting("GPU_TEMP_INDICATOR_COLOR"))
                pen = QPen(color, 1.5, Qt.PenStyle.DotLine)
                painter.setPen(pen)
                painter.drawLine(p.x(), self._plot_area.bottom(), p.x(), p.y())
                painter.drawLine(self._plot_area.left(), p.y(), p.x(), p.y())

    def _get_target_speed_for_indicator(self, temperature: float, curve_type: CurveType) -> int:
        table = self.cpu_curve_data if curve_type == 'cpu' else self.gpu_curve_data
        if not table: return -1
        
        try:
            interpolator = self._get_cached_interpolator(curve_type)
            if interpolator:
                speed = interpolator(temperature)
                return int(round(speed))
            else: # Fallback to simple linear interpolation if not enough points for PCHIP
                temps = [p[0] for p in table]
                speeds = [p[1] for p in table]
                speed = interp(temperature, temps, speeds)
                return int(round(speed))
        except Exception:
            # Fallback for any interpolation error
            temps = [p[0] for p in table]
            speeds = [p[1] for p in table]
            speed = interp(temperature, temps, speeds)
            return int(round(speed))

    def _invalidate_interpolator_cache(self, curve_type: CurveType):
        """Invalidates the cached interpolator for a given curve type."""
        if curve_type == 'cpu':
            self._cpu_interpolator = None
        elif curve_type == 'gpu':
            self._gpu_interpolator = None

    def _get_cached_interpolator(self, curve_type: CurveType) -> Optional[PchipInterpolator]:
        """Gets or creates a cached interpolator for a given curve type."""
        interpolator_attr = f"_{curve_type}_interpolator"
        data_attr = f"{curve_type}_curve_data"
        
        cached_interpolator = getattr(self, interpolator_attr)
        if cached_interpolator:
            return cached_interpolator

        table = getattr(self, data_attr)
        if not table: return None

        temps = [p[0] for p in table]
        speeds = [p[1] for p in table]
        
        unique_temps_map = {}
        for t, s in zip(temps, speeds):
            if t not in unique_temps_map or s > unique_temps_map[t]:
                unique_temps_map[t] = s
        
        unique_temps = sorted(unique_temps_map.keys())
        
        if len(unique_temps) >= MIN_POINTS_FOR_INTERPOLATION:
            unique_speeds = [unique_temps_map[t] for t in unique_temps]
            try:
                new_interpolator = PchipInterpolator(unique_temps, unique_speeds, extrapolate=False)
                setattr(self, interpolator_attr, new_interpolator)
                return new_interpolator
            except Exception:
                return None
        return None

    def apply_appearance_settings(self, settings: Dict[str, Any]):
        self._appearance_settings = settings.copy()
        self.update()

    def get_curve_data(self, curve_type: CurveType) -> FanTable:
        data = self.cpu_curve_data if curve_type == 'cpu' else self.gpu_curve_data
        return [list(p) for p in data]

    def retranslate_ui(self):
        self.setToolTip(f"{tr('add_point_info')}\n{tr('delete_point_info')}")
        self.update()

    def _validate_and_sort(self, table: FanTable) -> FanTable:
        if not isinstance(table, list): return []
        valid_points = [p for p in table if isinstance(p, list) and len(p) == 2 and all(isinstance(x, (int, float)) for x in p)]
        bounded_points = [[max(MIN_TEMP_C, min(MAX_TEMP_C, p[0])),
                           max(MIN_FAN_PERCENT, min(MAX_FAN_PERCENT, p[1]))]
                          for p in valid_points]
        return sorted(bounded_points, key=lambda x: x[0])

    # --- Mouse Events ---

    def mousePressEvent(self, event: QMouseEvent):
        if not self._plot_area.contains(event.pos()):
            return

        point_info = self._get_point_at_event(event.pos())

        if event.button() == Qt.MouseButton.LeftButton:
            if point_info:
                self._dragging_curve_type, self._dragging_point_index = point_info
                self.point_selected.emit(*point_info)
            else:
                self._dragging_point_index = None
                self.point_selected.emit(self.active_curve_type, -1)
        
        elif event.button() == Qt.MouseButton.RightButton and point_info:
            self._delete_point(*point_info)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if self._plot_area.contains(event.pos()) and event.button() == Qt.MouseButton.LeftButton:
            if self._get_point_at_event(event.pos()) is None:
                self._add_point(event.pos())

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._dragging_point_index is not None:
            self._drag_point(event.pos())
        else:
            point_info = self._get_point_at_event(event.pos())
            new_hover_index = point_info[1] if point_info else None
            if new_hover_index != self._hovered_point_index:
                self._hovered_point_index = new_hover_index
                self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self._dragging_point_index is not None and event.button() == Qt.MouseButton.LeftButton:
            curve_type = self._dragging_curve_type
            self._dragging_point_index = None
            self._dragging_curve_type = None
            
            data = self.cpu_curve_data if curve_type == 'cpu' else self.gpu_curve_data
            self._enforce_monotonicity_and_uniqueness(data)
            self._invalidate_interpolator_cache(curve_type) # Invalidate after drag
            self.curve_changed.emit(curve_type)
            self.update()

    def _get_point_at_event(self, pos: QPointF) -> Optional[Tuple[CurveType, int]]:
        data = self.cpu_curve_data if self.active_curve_type == 'cpu' else self.gpu_curve_data
        if not data: return None

        picker_radius = self._get_setting("CURVE_POINT_PICKER_RADIUS", 10)
        for i, p_data in enumerate(data):
            p_widget = self._data_to_widget_coords(p_data[0], p_data[1])
            # Using squared distance for efficiency
            if (pos.x() - p_widget.x())**2 + (pos.y() - p_widget.y())**2 < picker_radius**2:
                return (self.active_curve_type, i)
        return None

    def _add_point(self, pos: QPointF):
        temp, speed = self._widget_to_data_coords(pos)
        data = self.cpu_curve_data if self.active_curve_type == 'cpu' else self.gpu_curve_data
        
        data.append([int(round(temp)), int(round(speed))])
        self._enforce_monotonicity_and_uniqueness(data)
        self._invalidate_interpolator_cache(self.active_curve_type) # Invalidate after add
        self.curve_changed.emit(self.active_curve_type)
        self.update()

    def _delete_point(self, curve_type: CurveType, index: int):
        data = self.cpu_curve_data if curve_type == 'cpu' else self.gpu_curve_data
        if len(data) > MIN_CURVE_POINTS:
            del data[index]
            self._invalidate_interpolator_cache(curve_type) # Invalidate after delete
            self.curve_changed.emit(curve_type)
            self.update()
        else:
            QMessageBox.warning(self, tr("delete_point_error_title"), tr("delete_point_error_msg", min_points=MIN_CURVE_POINTS))

    def _drag_point(self, pos: QPointF):
        data = self.cpu_curve_data if self._dragging_curve_type == 'cpu' else self.gpu_curve_data
        idx = self._dragging_point_index
        
        temp, speed = self._widget_to_data_coords(pos)
        
        # Clamp temperature
        left_limit = data[idx - 1][0] + 1 if idx > 0 else MIN_TEMP_C
        right_limit = data[idx + 1][0] - 1 if idx < len(data) - 1 else MAX_TEMP_C
        temp = max(left_limit, min(right_limit, temp))

        # Clamp speed
        speed = max(MIN_FAN_PERCENT, min(MAX_FAN_PERCENT, speed))

        data[idx] = [int(round(temp)), int(round(speed))]
        self.point_dragged.emit(self._dragging_curve_type, idx, temp, speed)
        self.update()

    def _enforce_monotonicity_and_uniqueness(self, data: FanTable):
        if not data: return
        
        # Sort by temperature
        data.sort(key=lambda p: p[0])
        
        # Enforce non-decreasing speed
        for i in range(1, len(data)):
            if data[i][1] < data[i-1][1]:
                data[i][1] = data[i-1][1]
