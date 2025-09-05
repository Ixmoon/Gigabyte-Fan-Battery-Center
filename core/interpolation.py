# -*- coding: utf-8 -*-
"""
一个共享的、无依赖的PCHIP（分段三次Hermite插值多项式）插值模块。
确保后端风扇控制逻辑和前端UI表示使用完全相同的平滑、单调曲线算法。
"""
from typing import List, Union

# --- 无依赖的数值函数 ---

def linspace(start: float, stop: float, num: int) -> List[float]:
    """在指定间隔内生成`num`个均匀间隔的数字。"""
    if num == 0: return []
    if num == 1: return [start]
    step = (stop - start) / (num - 1)
    return [start + i * step for i in range(num)]

def clip(a: Union[float, List[float]], a_min: float, a_max: float) -> Union[float, List[float]]:
    """将一个值或一个值列表裁剪到给定范围内。"""
    if isinstance(a, (int, float)):
        return max(a_min, min(a_max, a))
    return [max(a_min, min(a_max, val)) for val in a]

def interp(x: float, xp: List[float], fp: List[float]) -> float:
    """
    一个纯Python实现的numpy.interp替代品。
    执行线性插值。
    """
    if not xp:
        return 0.0
    
    # 找到x的正确区间
    if x <= xp[0]:
        return fp[0]
    if x >= xp[-1]:
        return fp[-1]

    # 找到x所在的区间
    i = 0
    while i < len(xp) - 1 and x > xp[i+1]:
        i += 1
    
    # 线性插值公式
    x0, x1 = xp[i], xp[i+1]
    y0, y1 = fp[i], fp[i+1]
    
    # 如果点不唯一，避免除以零
    if x1 == x0:
        return y0
        
    return y0 + (x - x0) * (y1 - y0) / (x1 - x0)


class PchipInterpolator:
    """
    PCHIP插值的从零开始的实现。
    它产生一个通过所有数据点的单调三次样条。
    此实现旨在无依赖。
    """
    def __init__(self, x: List[float], y: List[float], extrapolate: bool = False):
        if len(x) != len(y) or len(x) < 2:
            raise ValueError("x和y必须是相同大小的列表，且至少有2个点。")

        # 按x值对点进行排序以确保正确的插值
        sorted_points = sorted(zip(x, y))
        self.x = [p[0] for p in sorted_points]
        self.y = [p[1] for p in sorted_points]
        self.extrapolate = extrapolate

        self.n = len(self.x)
        self.h = [self.x[i+1] - self.x[i] for i in range(self.n - 1)]
        self.delta = [(self.y[i+1] - self.y[i]) / self.h[i] for i in range(self.n - 1)]
        
        self.d = self._calculate_derivatives()

    def _calculate_derivatives(self) -> List[float]:
        """计算每个数据点的导数（斜率）。"""
        d = [0.0] * self.n

        # 端点 (非中心差分)
        d[0] = self.delta[0]
        d[self.n - 1] = self.delta[self.n - 2]

        # 内部点
        for i in range(1, self.n - 1):
            h0, h1 = self.h[i-1], self.h[i]
            d0, d1 = self.delta[i-1], self.delta[i]

            # 如果斜率有不同符号或其中一个为零，则导数为零
            # 以防止过冲并保持单调性。
            if d0 * d1 <= 0:
                d[i] = 0.0
            else:
                # 用于单调性的加权调和平均
                w1 = 2 * h1 + h0
                w2 = h1 + 2 * h0
                d[i] = (w1 + w2) / (w1 / d0 + w2 / d1)
        
        return d

    def __call__(self, xi: Union[float, List[float]]) -> Union[float, List[float]]:
        """在给定点评估插值器。"""
        is_scalar = not isinstance(xi, list)
        if is_scalar:
            # mypy complains if xi is not a list, so we make it a list
            xi_list = [xi]
        else:
            xi_list = xi

        results = []
        for val in xi_list:
            results.append(self._evaluate_single(val))
        
        return results[0] if is_scalar else results

    def _evaluate_single(self, val: float) -> float:
        """为单个值评估插值器。"""
        # 找到val所在的区间
        if val < self.x[0]:
            return self.y[0] if not self.extrapolate else self._extrapolate(val, 0)
        if val > self.x[-1]:
            return self.y[-1] if not self.extrapolate else self._extrapolate(val, self.n - 2)

        # 二分搜索找到正确的区间
        low, high = 0, self.n - 1
        while low <= high:
            mid = (low + high) // 2
            if self.x[mid] < val:
                low = mid + 1
            elif self.x[mid] > val:
                high = mid - 1
            else:
                return self.y[mid] # 完全匹配
        
        # `high`现在是区间开始的索引
        i = high if high >= 0 else 0
        if i >= self.n - 1: i = self.n - 2 # 确保我们不会越界

        # 将t归一化到区间[0, 1]
        t = (val - self.x[i]) / self.h[i]

        # Hermite基函数
        h00 = (2 * t**3) - (3 * t**2) + 1
        h10 = (t**3) - (2 * t**2) + t
        h01 = (-2 * t**3) + (3 * t**2)
        h11 = (t**3) - (t**2)

        # 三次Hermite样条公式
        return (h00 * self.y[i] +
                h01 * self.y[i+1] +
                h10 * self.h[i] * self.d[i] +
                h11 * self.h[i] * self.d[i+1])

    def _extrapolate(self, val: float, i: int) -> float:
        """使用端点的导数进行线性外插。"""
        return self.y[i] + (val - self.x[i]) * self.d[i]