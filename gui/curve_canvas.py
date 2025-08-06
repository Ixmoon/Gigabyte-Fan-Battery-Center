# gui/curve_canvas.py
# -*- coding: utf-8 -*-
"""
Matplotlib canvas widget for displaying and editing fan curves.
"""

# ... (previous imports remain the same) ...
from typing import List, Optional, Any, Dict, Tuple
import numpy as np
from scipy.interpolate import PchipInterpolator
import matplotlib
matplotlib.use('QtAgg') # Ensure Qt backend is used
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.lines as lines
from matplotlib.backend_bases import MouseButton

from .qt import QSizePolicy, QMessageBox, Signal

# Import settings for defaults and limits
from config.settings import (
    MIN_TEMP_C, MAX_TEMP_C, MIN_FAN_PERCENT, MAX_FAN_PERCENT,
    MIN_CURVE_POINTS, MIN_POINTS_FOR_INTERPOLATION, TEMP_READ_ERROR_VALUE,
    DEFAULT_PROFILE_SETTINGS # Used for initial/fallback appearance
)
# Import localization
from tools.localization import tr

# Type Hinting
FanTable = List[List[int]]
CurveType = str # 'cpu' or 'gpu'

class CurveCanvas(FigureCanvas):
    """Matplotlib canvas for interactive fan curve editing."""

    # ... (signals remain the same) ...
    point_dragged = Signal(CurveType, int, float, float) # curve_type, index, temp, speed
    curve_changed = Signal(CurveType) # curve_type (emitted after drag release or point add/delete)
    point_selected = Signal(CurveType, int) # curve_type, index (-1 if no point selected)


    def __init__(self, parent=None, width=5, height=4, dpi=100):
        self.fig = Figure(figsize=(width, height), dpi=dpi, facecolor='#33373B') # Set base background
        self.axes = self.fig.add_subplot(111)
        super().__init__(self.fig)
        self.setParent(parent)

        # Internal state
        self.cpu_curve_data: FanTable = []
        self.gpu_curve_data: FanTable = []
        self.active_curve_type: CurveType = 'cpu' # Which curve is currently editable
        self._appearance_settings: Dict[str, Any] = DEFAULT_PROFILE_SETTINGS.copy() # Start with defaults

        # Matplotlib plot elements (lines, points, indicators)
        self.cpu_line: Optional[lines.Line2D] = None
        self.gpu_line: Optional[lines.Line2D] = None
        self.cpu_points: Optional[lines.Line2D] = None
        self.gpu_points: Optional[lines.Line2D] = None
        self.cpu_temp_line: Optional[lines.Line2D] = None
        self.gpu_temp_line: Optional[lines.Line2D] = None
        self.cpu_speed_indicator_line: Optional[lines.Line2D] = None
        self.gpu_speed_indicator_line: Optional[lines.Line2D] = None

        # Dragging state
        self._dragging_point_index: Optional[int] = None
        self._selected_point_index: Optional[int] = None # For potential future use (e.g., showing exact values)
        self._dragging_curve_type: Optional[CurveType] = None

        # Setup UI
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.updateGeometry()
        self._setup_plot_style()
        self.connect_events()
        self.setToolTip(f"{tr('add_point_info')}\n{tr('delete_point_info')}")
        self.fig.tight_layout(pad=2.0) # Add some padding

    # --- Added Method ---
    def _validate_and_sort(self, table: FanTable) -> FanTable:
        """Sorts table by temperature and ensures basic validity for plotting."""
        if not isinstance(table, list): return []
        # Basic filtering for structure and type, then sort by temperature
        valid_points = [p for p in table if isinstance(p, list) and len(p) == 2 and all(isinstance(x, (int, float)) for x in p)]
        # Ensure points are within reasonable bounds for plotting consistency
        # (More strict validation happens in ConfigManager)
        bounded_points = [[max(MIN_TEMP_C - 20, min(MAX_TEMP_C + 20, p[0])), # Allow slight overshoot for display
                           max(MIN_FAN_PERCENT - 10, min(MAX_FAN_PERCENT + 10, p[1]))]
                          for p in valid_points]
        return sorted(bounded_points, key=lambda x: x[0])
    # --- End Added Method ---

    def _setup_plot_style(self):
        """Sets the visual style of the plot axes, labels, grid, etc."""
        # ... (rest of the method is unchanged) ...
        bg_color = self._appearance_settings.get('FIGURE_BG_COLOR', '#33373B') # Match window potentially
        axes_color = self._appearance_settings.get('AXES_BG_COLOR', '#2A2D30')
        label_color = self._appearance_settings.get('AXES_LABEL_COLOR', '#E0E0E0')
        grid_color = self._appearance_settings.get('GRID_COLOR', '#555555')
        tick_color = self._appearance_settings.get('TICK_COLOR', '#E0E0E0')

        self.fig.patch.set_facecolor(bg_color)
        self.axes.set_facecolor(axes_color)

        self.axes.set_xlabel(tr("temp_axis_label"), color=label_color)
        self.axes.set_ylabel(tr("speed_axis_label"), color=label_color)

        self.axes.tick_params(axis='x', colors=tick_color)
        self.axes.tick_params(axis='y', colors=tick_color)

        # Set spine colors (the plot border)
        for spine in self.axes.spines.values():
            spine.set_edgecolor(label_color)

        self.axes.grid(True, linestyle='--', color=grid_color, alpha=0.6)

        # Set plot limits
        self.axes.set_xlim(MIN_TEMP_C - 5, MAX_TEMP_C + 5)
        self.axes.set_ylim(MIN_FAN_PERCENT - 5, MAX_FAN_PERCENT + 5)


    def apply_appearance_settings(self, settings: Dict[str, Any]):
        """Applies new appearance settings from a profile."""
        
        self._appearance_settings = settings.copy()
        self._setup_plot_style() # Re-apply base styles
        # Update appearance of existing plot elements
        self._update_curve_appearance('cpu')
        self._update_curve_appearance('gpu')
        # Re-draw indicators with potentially new colors
        # Get last known temps if available (caller should ideally provide them)
        last_cpu_temp = TEMP_READ_ERROR_VALUE
        last_gpu_temp = TEMP_READ_ERROR_VALUE
        if self.cpu_temp_line and self.cpu_temp_line.get_visible():
            last_cpu_temp = self.cpu_temp_line.get_xdata()[0]
        if self.gpu_temp_line and self.gpu_temp_line.get_visible():
            last_gpu_temp = self.gpu_temp_line.get_xdata()[0]
        self.update_temp_indicators(last_cpu_temp, last_gpu_temp) # Redraw indicators
        self._update_legend()
        self.draw_idle()


    def _get_setting(self, key: str, default_override: Any = None) -> Any:
        """Safely gets an appearance setting, falling back to global defaults if needed."""
        
        return self._appearance_settings.get(key, DEFAULT_PROFILE_SETTINGS.get(key, default_override))


    def connect_events(self):
        """Connects matplotlib mouse events to handler methods."""
        
        self.mpl_connect('button_press_event', self.on_press)
        self.mpl_connect('motion_notify_event', self.on_motion)
        self.mpl_connect('button_release_event', self.on_release)


    def set_active_curve(self, curve_type: CurveType):
        """Sets which curve (CPU or GPU) is currently active for editing."""
        
        if curve_type in ['cpu', 'gpu'] and self.active_curve_type != curve_type:
            self.active_curve_type = curve_type
            # Update visual styles to reflect active/inactive state
            self._update_curve_appearance('cpu')
            self._update_curve_appearance('gpu')
            self.draw_idle()


    def _update_curve_appearance(self, curve_type: CurveType):
        """Updates the visual style (color, width, visibility) of a specific curve."""
        
        is_active = (self.active_curve_type == curve_type)
        line_obj = self.cpu_line if curve_type == 'cpu' else self.gpu_line
        points_obj = self.cpu_points if curve_type == 'cpu' else self.gpu_points

        # Get appearance settings from current profile config
        line_width = self._get_setting("LINE_WIDTH_ACTIVE") if is_active else self._get_setting("LINE_WIDTH_INACTIVE")
        alpha = self._get_setting("ALPHA_ACTIVE") if is_active else self._get_setting("ALPHA_INACTIVE")
        point_color = self._get_setting("POINT_COLOR_ACTIVE")
        point_size = self._get_setting("POINT_SIZE_ACTIVE")
        picker_radius = self._get_setting("CURVE_POINT_PICKER_RADIUS")
        line_color = self._get_setting("CPU_CURVE_COLOR") if curve_type == 'cpu' else self._get_setting("GPU_CURVE_COLOR")

        if line_obj:
            line_obj.set_linewidth(line_width)
            line_obj.set_alpha(alpha)
            line_obj.set_color(line_color) # Ensure color updates if profile changes
            line_obj.set_zorder(2 if is_active else 1) # Active curve on top

        if points_obj:
            points_obj.set_visible(is_active) # Only show points for active curve
            if is_active:
                points_obj.set_markersize(point_size)
                points_obj.set_color(point_color)
                points_obj.set_zorder(3) # Points on top of line
                points_obj.set_picker(picker_radius) # Enable picking for active points
            else:
                points_obj.set_picker(False) # Disable picking for inactive points


    def _plot_single_curve(self, data: FanTable, curve_type: CurveType):
        """Plots or updates a single fan curve (line and points)."""
        
        is_active = (self.active_curve_type == curve_type)
        line_obj = self.cpu_line if curve_type == 'cpu' else self.gpu_line
        points_obj = self.cpu_points if curve_type == 'cpu' else self.gpu_points

        # Get appearance settings
        line_color = self._get_setting("CPU_CURVE_COLOR") if curve_type == 'cpu' else self._get_setting("GPU_CURVE_COLOR")
        line_width = self._get_setting("LINE_WIDTH_ACTIVE") if is_active else self._get_setting("LINE_WIDTH_INACTIVE")
        alpha = self._get_setting("ALPHA_ACTIVE") if is_active else self._get_setting("ALPHA_INACTIVE")
        point_color = self._get_setting("POINT_COLOR_ACTIVE")
        point_size = self._get_setting("POINT_SIZE_ACTIVE")
        picker_radius = self._get_setting("CURVE_POINT_PICKER_RADIUS")
        spline_points = self._get_setting("SPLINE_POINTS")

        # Prepare data for plotting
        if not data: # Handle empty curve
            temps, speeds = [], []
            temps_smooth, speeds_smooth = [], []
        else:
            temps = np.array([p[0] for p in data])
            speeds = np.array([p[1] for p in data])
            temps_smooth, speeds_smooth = [], [] # For the interpolated line

            # Generate smooth curve using PCHIP if enough points
            if len(data) >= MIN_POINTS_FOR_INTERPOLATION:
                try:
                    # Handle duplicate temps for interpolation
                    unique_temps_map: Dict[float, float] = {}
                    for t, s in zip(temps, speeds):
                        if t not in unique_temps_map or s > unique_temps_map[t]:
                            unique_temps_map[t] = s
                    unique_temps = np.array(sorted(unique_temps_map.keys()))
                    unique_speeds = np.array([unique_temps_map[t] for t in unique_temps])

                    if len(unique_temps) >= MIN_POINTS_FOR_INTERPOLATION:
                        interpolator = PchipInterpolator(unique_temps, unique_speeds)
                        temps_smooth = np.linspace(unique_temps.min(), unique_temps.max(), spline_points)
                        speeds_smooth = np.clip(interpolator(temps_smooth), MIN_FAN_PERCENT, MAX_FAN_PERCENT)
                    else: # Not enough unique points, plot linearly
                        temps_smooth, speeds_smooth = temps, speeds
                except Exception: # Fallback on interpolation error
                    temps_smooth, speeds_smooth = temps, speeds
            else: # Not enough points, plot linearly
                temps_smooth, speeds_smooth = temps, speeds

        # Plot or update the smooth line
        if line_obj is None:
            line_obj, = self.axes.plot(temps_smooth, speeds_smooth, color=line_color, linestyle='-',
                                       linewidth=line_width, alpha=alpha, zorder=2 if is_active else 1)
            if curve_type == 'cpu': self.cpu_line = line_obj
            else: self.gpu_line = line_obj
        else:
            line_obj.set_data(temps_smooth, speeds_smooth)
            line_obj.set_color(line_color)
            line_obj.set_linewidth(line_width)
            line_obj.set_alpha(alpha)
            line_obj.set_zorder(2 if is_active else 1)

        # Plot or update the control points (only visible for active curve)
        if points_obj is None:
            points_obj, = self.axes.plot(temps, speeds, color=point_color, marker='o', markersize=point_size,
                                         linestyle='None', visible=is_active, picker=picker_radius if is_active else False, zorder=3)
            if curve_type == 'cpu': self.cpu_points = points_obj
            else: self.gpu_points = points_obj
        else:
            points_obj.set_data(temps, speeds)
            points_obj.set_visible(is_active)
            points_obj.set_picker(picker_radius if is_active else False)
            if is_active: # Apply active styles only if visible
                points_obj.set_color(point_color)
                points_obj.set_markersize(point_size)
                points_obj.set_zorder(3)


    def update_plot(self, cpu_data: FanTable, gpu_data: FanTable):
        """Updates both CPU and GPU curves on the plot."""
        # Store validated and sorted data internally using the new method
        self.cpu_curve_data = self._validate_and_sort(cpu_data)
        self.gpu_curve_data = self._validate_and_sort(gpu_data)

        # Plot both curves
        self._plot_single_curve(self.cpu_curve_data, 'cpu')
        self._plot_single_curve(self.gpu_curve_data, 'gpu')

        # Ensure axes limits and labels are correct
        self.axes.set_xlim(MIN_TEMP_C - 5, MAX_TEMP_C + 5)
        self.axes.set_ylim(MIN_FAN_PERCENT - 5, MAX_FAN_PERCENT + 5)
        self.axes.set_xlabel(tr("temp_axis_label"))
        self.axes.set_ylabel(tr("speed_axis_label"))

        self._update_legend()
        self.fig.tight_layout(pad=2.0)
        self.draw_idle() # Request redraw

    def update_temp_indicators(self, cpu_temp: float, gpu_temp: float):
        """Updates the vertical/horizontal lines indicating current temps and target speeds."""
        
        try:
            xmin, xmax = self.axes.get_xlim()
            ymin, ymax = self.axes.get_ylim()
        except Exception: # Handle cases where axes might not be fully initialized
            xmin, xmax = MIN_TEMP_C - 5, MAX_TEMP_C + 5
            ymin, ymax = MIN_FAN_PERCENT - 5, MAX_FAN_PERCENT + 5

        plot_ymin = max(ymin, MIN_FAN_PERCENT) # Start lines from 0% speed axis
        plot_xmin = max(xmin, MIN_TEMP_C)    # Start lines from 0°C temp axis

        # --- CPU Indicator ---
        cpu_temp_color = self._get_setting("CPU_TEMP_INDICATOR_COLOR")
        cpu_speed_color = self._get_setting("CPU_SPEED_INDICATOR_COLOR")
        cpu_target_speed = -1
        if cpu_temp != TEMP_READ_ERROR_VALUE and self.cpu_curve_data:
            # Calculate target speed based on *current* curve data (use linear for simplicity here)
            cpu_target_speed = self._get_target_speed_for_indicator(cpu_temp, self.cpu_curve_data)

        # Update CPU Temperature Line (Vertical)
        if cpu_temp != TEMP_READ_ERROR_VALUE and cpu_target_speed != -1:
            if self.cpu_temp_line is None:
                self.cpu_temp_line, = self.axes.plot([cpu_temp, cpu_temp], [plot_ymin, cpu_target_speed],
                                                     color=cpu_temp_color, linestyle=':', linewidth=1.5, zorder=0.5, label='_nolegend_')
            else:
                self.cpu_temp_line.set_data([cpu_temp, cpu_temp], [plot_ymin, cpu_target_speed])
                self.cpu_temp_line.set_color(cpu_temp_color) # Update color in case profile changed
                self.cpu_temp_line.set_visible(True)
        elif self.cpu_temp_line is not None:
            self.cpu_temp_line.set_visible(False)

        # Update CPU Speed Line (Horizontal)
        if cpu_temp != TEMP_READ_ERROR_VALUE and cpu_target_speed != -1:
            if self.cpu_speed_indicator_line is None:
                self.cpu_speed_indicator_line, = self.axes.plot([plot_xmin, cpu_temp], [cpu_target_speed, cpu_target_speed],
                                                                color=cpu_speed_color, linestyle='--', linewidth=1.0, zorder=0.6, label='_nolegend_')
            else:
                self.cpu_speed_indicator_line.set_data([plot_xmin, cpu_temp], [cpu_target_speed, cpu_target_speed])
                self.cpu_speed_indicator_line.set_color(cpu_speed_color)
                self.cpu_speed_indicator_line.set_visible(True)
        elif self.cpu_speed_indicator_line is not None:
            self.cpu_speed_indicator_line.set_visible(False)

        # --- GPU Indicator ---
        gpu_temp_color = self._get_setting("GPU_TEMP_INDICATOR_COLOR")
        gpu_speed_color = self._get_setting("GPU_SPEED_INDICATOR_COLOR")
        gpu_target_speed = -1
        if gpu_temp != TEMP_READ_ERROR_VALUE and self.gpu_curve_data:
            gpu_target_speed = self._get_target_speed_for_indicator(gpu_temp, self.gpu_curve_data)

        # Update GPU Temperature Line (Vertical)
        if gpu_temp != TEMP_READ_ERROR_VALUE and gpu_target_speed != -1:
            if self.gpu_temp_line is None:
                self.gpu_temp_line, = self.axes.plot([gpu_temp, gpu_temp], [plot_ymin, gpu_target_speed],
                                                     color=gpu_temp_color, linestyle=':', linewidth=1.5, zorder=0.5, label='_nolegend_')
            else:
                self.gpu_temp_line.set_data([gpu_temp, gpu_temp], [plot_ymin, gpu_target_speed])
                self.gpu_temp_line.set_color(gpu_temp_color)
                self.gpu_temp_line.set_visible(True)
        elif self.gpu_temp_line is not None:
            self.gpu_temp_line.set_visible(False)

        # Update GPU Speed Line (Horizontal)
        if gpu_temp != TEMP_READ_ERROR_VALUE and gpu_target_speed != -1:
            if self.gpu_speed_indicator_line is None:
                self.gpu_speed_indicator_line, = self.axes.plot([plot_xmin, gpu_temp], [gpu_target_speed, gpu_target_speed],
                                                                color=gpu_speed_color, linestyle='--', linewidth=1.0, zorder=0.6, label='_nolegend_')
            else:
                self.gpu_speed_indicator_line.set_data([plot_xmin, gpu_temp], [gpu_target_speed, gpu_target_speed])
                self.gpu_speed_indicator_line.set_color(gpu_speed_color)
                self.gpu_speed_indicator_line.set_visible(True)
        elif self.gpu_speed_indicator_line is not None:
            self.gpu_speed_indicator_line.set_visible(False)

        # Redraw the canvas to show changes
        self.draw_idle()


    def _get_target_speed_for_indicator(self, temperature: float, table: FanTable) -> int:
        """Helper to calculate target speed using linear interpolation for indicators."""
        
        if not table: return -1
        # Clamp temperature to the range defined by the curve for realistic indicator lines
        temp_clamped = max(table[0][0], min(table[-1][0], temperature))

        # Use simple linear interpolation (same as fallback in AutoTempController)
        if temp_clamped <= table[0][0]: return int(table[0][1])
        if temp_clamped >= table[-1][0]: return int(table[-1][1])

        for i in range(len(table) - 1):
            temp1, speed1 = table[i]
            temp2, speed2 = table[i+1]
            if temp1 <= temp_clamped < temp2:
                if temp2 == temp1: return int(speed1)
                interp_speed = speed1 + (temp_clamped - temp1) * (speed2 - speed1) / (temp2 - temp1)
                return int(max(MIN_FAN_PERCENT, min(MAX_FAN_PERCENT, round(interp_speed))))
        return int(table[-1][1]) # Fallback


    def _update_legend(self):
        """Updates the plot legend based on visible curves."""
        
        handles = []
        labels = []
        # Get colors from settings for legend handles
        cpu_curve_color = self._get_setting("CPU_CURVE_COLOR")
        gpu_curve_color = self._get_setting("GPU_CURVE_COLOR")

        # Add legend entry only if the curve has data
        if self.cpu_curve_data:
             # Use existing line if available, otherwise create a dummy handle
             handle_cpu = self.cpu_line if self.cpu_line else lines.Line2D([], [], color=cpu_curve_color)
             handles.append(handle_cpu)
             labels.append(tr("cpu_curve_legend_label"))
        if self.gpu_curve_data:
             handle_gpu = self.gpu_line if self.gpu_line else lines.Line2D([], [], color=gpu_curve_color)
             handles.append(handle_gpu)
             labels.append(tr("gpu_curve_legend_label"))

        # Remove existing legend before adding new one
        if self.axes.get_legend() is not None:
            self.axes.get_legend().remove()

        # Add new legend if there are handles
        if handles:
            self.axes.legend(handles, labels, loc='lower right', fontsize='small', framealpha=0.7)


    def get_point_at_event(self, event) -> Optional[Tuple[CurveType, int]]:
        """Finds the index of the active curve point near the mouse event."""
        
        if not event.inaxes == self.axes: return None # Event outside plot area

        active_data = self.cpu_curve_data if self.active_curve_type == 'cpu' else self.gpu_curve_data
        if not active_data: return None # No points in active curve

        active_points_obj = self.cpu_points if self.active_curve_type == 'cpu' else self.gpu_points
        # Check if points are visible and pickable
        if not active_points_obj or not active_points_obj.get_visible() or not active_points_obj.get_picker():
            return None

        # Check distance in display coordinates
        picker_radius = active_points_obj.get_picker() # Use the set picker radius
        min_dist_sq = picker_radius**2 # Compare squared distances
        closest_index = None
        x_display, y_display = event.x, event.y # Event coordinates in pixels

        for i, (temp, speed) in enumerate(active_data):
            # Convert data point to display coordinates
            point_x_display, point_y_display = self.axes.transData.transform((temp, speed))
            dist_sq = (x_display - point_x_display)**2 + (y_display - point_y_display)**2
            if dist_sq < min_dist_sq:
                min_dist_sq = dist_sq
                closest_index = i

        if closest_index is not None:
            return (self.active_curve_type, closest_index)
        return None


    def _enforce_monotonicity_and_uniqueness(self, data: FanTable) -> FanTable:
        """Ensures the curve is monotonically increasing in both temp and speed, removing duplicates."""
        
        if not data: return []

        # 1. Sort by temperature primarily, speed secondarily (for stability)
        data = sorted(data, key=lambda p: (p[0], p[1]))

        # 2. Handle duplicate temperatures: keep only the point with the highest speed
        unique_data_map: Dict[float, float] = {}
        for temp, speed in data:
            if temp not in unique_data_map or speed > unique_data_map[temp]:
                unique_data_map[temp] = speed
        # Rebuild sorted list from unique points
        unique_data = sorted([[t, s] for t, s in unique_data_map.items()], key=lambda p: p[0])

        # 3. Enforce non-decreasing speed
        if not unique_data: return []
        corrected_data = [unique_data[0]] # Start with the first point
        for i in range(1, len(unique_data)):
            current_temp, current_speed = unique_data[i]
            prev_temp, prev_speed = corrected_data[-1] # Get the last added point
            # Ensure speed is not lower than the previous point's speed
            corrected_speed = max(current_speed, prev_speed)
            corrected_data.append([current_temp, corrected_speed])

        return corrected_data


    # --- Event Handlers ---

    def on_press(self, event):
        """Handles mouse button presses on the canvas."""
        
        if not event.inaxes == self.axes: return

        click_result = self.get_point_at_event(event)

        if event.button == MouseButton.RIGHT and click_result is not None:
            # Right Click on a point: Delete point
            curve_type, index = click_result
            data = self.cpu_curve_data if curve_type == 'cpu' else self.gpu_curve_data
            if len(data) <= MIN_CURVE_POINTS:
                QMessageBox.warning(self, tr("delete_point_error_title"), tr("delete_point_error_msg", min_points=MIN_CURVE_POINTS))
                return

            del data[index]
            # No need to enforce monotonicity here, happens on release/update_plot
            self.update_plot(self.cpu_curve_data, self.gpu_curve_data) # Redraw immediately
            self.curve_changed.emit(curve_type) # Signal change
            return

        elif event.dblclick and event.button == MouseButton.LEFT and click_result is None:
            # Double Left Click on empty space: Add point to active curve
            x_data, y_data = event.xdata, event.ydata
            if x_data is None or y_data is None: return

            curve_type = self.active_curve_type
            data = self.cpu_curve_data if curve_type == 'cpu' else self.gpu_curve_data

            # Clamp new point coordinates to valid ranges
            new_temp = int(max(MIN_TEMP_C, min(MAX_TEMP_C, round(x_data))))
            new_speed = int(max(MIN_FAN_PERCENT, min(MAX_FAN_PERCENT, round(y_data))))

            # Add the new point
            data.append([new_temp, new_speed])

            # Enforce monotonicity and uniqueness immediately after adding
            validated_data = self._enforce_monotonicity_and_uniqueness(data)
            if curve_type == 'cpu': self.cpu_curve_data = validated_data
            else: self.gpu_curve_data = validated_data

            self.update_plot(self.cpu_curve_data, self.gpu_curve_data) # Redraw
            self.curve_changed.emit(curve_type) # Signal change
            return

        elif event.button == MouseButton.LEFT:
            # Left Click: Select point or start drag
            if click_result is not None:
                curve_type, index = click_result
                self._dragging_curve_type = curve_type
                self._dragging_point_index = index
                self._selected_point_index = index
                self.point_selected.emit(curve_type, index)
                # Visually indicate selection (optional, e.g., change point color slightly)
            else:
                # Clicked on empty space, deselect
                self._selected_point_index = None
                self._dragging_curve_type = None
                self._dragging_point_index = None
                self.point_selected.emit(self.active_curve_type, -1)
                # Reset visual indication if any


    def on_motion(self, event):
        """Handles mouse movement while a button is pressed (dragging)."""
        
        if self._dragging_point_index is None or event.button != MouseButton.LEFT or not event.inaxes == self.axes:
            return

        x_data, y_data = event.xdata, event.ydata
        if x_data is None or y_data is None: return # Outside plot area

        idx = self._dragging_point_index
        curve_type = self._dragging_curve_type
        data = self.cpu_curve_data if curve_type == 'cpu' else self.gpu_curve_data
        points_obj = self.cpu_points if curve_type == 'cpu' else self.gpu_points
        line_obj = self.cpu_line if curve_type == 'cpu' else self.gpu_line

        if not data or idx >= len(data) or not points_obj or not line_obj:
            # Should not happen if dragging state is correct, but safety check
            self._dragging_point_index = None
            self._dragging_curve_type = None
            return

        # --- Calculate movement boundaries ---
        # Temperature boundaries (cannot move past adjacent points)
        left_temp_limit = data[idx - 1][0] + 1 if idx > 0 else MIN_TEMP_C
        right_temp_limit = data[idx + 1][0] - 1 if idx < len(data) - 1 else MAX_TEMP_C
        # Speed boundaries (cannot move below previous point or above next point's speed)
        # Note: This enforces monotonicity *during* the drag visually
        lower_speed_bound = data[idx - 1][1] if idx > 0 else MIN_FAN_PERCENT
        upper_speed_bound = data[idx + 1][1] if idx < len(data) - 1 else MAX_FAN_PERCENT

        # --- Apply boundaries and update point position ---
        new_temp = int(max(left_temp_limit, min(right_temp_limit, round(x_data))))
        new_speed = int(max(MIN_FAN_PERCENT, min(MAX_FAN_PERCENT, round(y_data))))
        # Apply monotonic speed constraint relative to neighbors
        new_speed = int(max(lower_speed_bound, min(upper_speed_bound, new_speed)))

        # Update data list directly
        data[idx][0] = new_temp
        data[idx][1] = new_speed

        # --- Update plot visually during drag ---
        # Update points object data
        temps = [p[0] for p in data]
        speeds = [p[1] for p in data]
        points_obj.set_data(temps, speeds)

        # Update smooth line based on potentially non-monotonic *during drag* data
        # (Final monotonicity is enforced on release)
        temps_smooth, speeds_smooth = [], []
        spline_points = self._get_setting("SPLINE_POINTS")
        if len(data) >= MIN_POINTS_FOR_INTERPOLATION:
            try:
                # Use current (potentially non-monotonic) data for visual feedback
                unique_temps_map = {}
                for t, s in zip(temps, speeds):
                     if t not in unique_temps_map or s > unique_temps_map[t]: unique_temps_map[t] = s
                unique_temps = np.array(sorted(unique_temps_map.keys()))
                unique_speeds = np.array([unique_temps_map[t] for t in unique_temps])

                if len(unique_temps) >= MIN_POINTS_FOR_INTERPOLATION:
                    interpolator = PchipInterpolator(unique_temps, unique_speeds)
                    temps_smooth = np.linspace(unique_temps.min(), unique_temps.max(), spline_points)
                    speeds_smooth = np.clip(interpolator(temps_smooth), MIN_FAN_PERCENT, MAX_FAN_PERCENT)
                else: temps_smooth, speeds_smooth = temps, speeds
            except Exception: temps_smooth, speeds_smooth = temps, speeds
        else: temps_smooth, speeds_smooth = temps, speeds
        line_obj.set_data(temps_smooth, speeds_smooth)

        # Emit signal for potential live feedback (e.g., status bar)
        self.point_dragged.emit(curve_type, idx, new_temp, new_speed)

        # Redraw canvas
        self.draw_idle()


    def on_release(self, event):
        """Handles mouse button releases, finalizing drag operations."""
        
        if event.button != MouseButton.LEFT or self._dragging_point_index is None:
            return # Not releasing a drag we initiated

        curve_type = self._dragging_curve_type
        idx = self._dragging_point_index # Keep index for signal if needed

        # Clear dragging state
        self._dragging_point_index = None
        self._dragging_curve_type = None

        # Get the final data after drag
        data = self.cpu_curve_data if curve_type == 'cpu' else self.gpu_curve_data

        # Enforce final monotonicity and uniqueness
        validated_data = self._enforce_monotonicity_and_uniqueness(data)
        if curve_type == 'cpu': self.cpu_curve_data = validated_data
        else: self.gpu_curve_data = validated_data

        # Update the plot with the final, validated data
        self.update_plot(self.cpu_curve_data, self.gpu_curve_data)

        # Emit signal indicating the curve has changed
        self.curve_changed.emit(curve_type)


    # --- Public Methods ---

    def retranslate_ui(self):
        """Retranslates text elements on the plot."""
        
        self.axes.set_xlabel(tr("temp_axis_label"))
        self.axes.set_ylabel(tr("speed_axis_label"))
        self.setToolTip(f"{tr('add_point_info')}\n{tr('delete_point_info')}")
        self._update_legend()
        self.draw_idle()


    def get_curve_data(self, curve_type: CurveType) -> FanTable:
        """Returns the current data points for the specified curve."""
        
        data = self.cpu_curve_data if curve_type == 'cpu' else self.gpu_curve_data
        # Return a copy to prevent external modification
        return [list(p) for p in data]