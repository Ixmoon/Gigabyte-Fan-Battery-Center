# -*- coding to: utf-8 -*-
"""
【新增】紧急风扇速度设置器。

这是一个完全独立的脚本，其唯一目的是在主应用程序崩溃时被调用，
将风扇速度设置为一个安全值（80%）。

它通过进程隔离来避免主应用崩溃时可能出现的COM重入死锁问题。
【最终修复】简化并统一了WMI调用方式，使其与主程序保持一致，更加健壮和简洁。
"""

import os
import sys
import math
import traceback
from datetime import datetime

# 确保可以从项目根目录导入config模块
try:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from config.settings import (
        WMI_NAMESPACE, DEFAULT_WMI_SET_CLASS, SET_CUSTOM_FAN_STATUS, SET_SUPER_QUIET,
        SET_AUTO_FAN_STATUS, SET_STEP_FAN_STATUS, SET_CUSTOM_FAN_SPEED, SET_GPU_FAN_DUTY
    )
except ImportError:
    try:
        from config.settings import (
            WMI_NAMESPACE, DEFAULT_WMI_SET_CLASS, SET_CUSTOM_FAN_STATUS, SET_SUPER_QUIET,
            SET_AUTO_FAN_STATUS, SET_STEP_FAN_STATUS, SET_CUSTOM_FAN_SPEED, SET_GPU_FAN_DUTY
        )
    except ImportError:
        WMI_NAMESPACE = r"root\WMI"
        DEFAULT_WMI_SET_CLASS = "GB_WMIACPI_Set"
        SET_CUSTOM_FAN_STATUS = "SetFixedFanStatus"
        SET_AUTO_FAN_STATUS = "SetAutoFanStatus"
        SET_CUSTOM_FAN_SPEED = "SetFixedFanSpeed"
        SET_GPU_FAN_DUTY = "SetGPUFanDuty"
        SET_SUPER_QUIET = "SetSuperQuiet"
        SET_STEP_FAN_STATUS = "SetStepFanStatus"

def log_message(message: str):
    """将消息记录到 emergency.log 文件中。"""
    log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'emergency.log')
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    try:
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(f"[{timestamp}] {message}\n")
    except Exception:
        pass

def set_emergency_fan_speed():
    """
    一个独立的函数，用于设置紧急风扇速度。
    """
    log_message("紧急风扇设置脚本启动...")
    
    try:
        import wmi
        import pythoncom
    except ImportError:
        log_message("错误: wmi或pythoncom库未找到。无法设置紧急速度。")
        return

    com_initialized = False
    try:
        pythoncom.CoInitializeEx(pythoncom.COINIT_MULTITHREADED)
        com_initialized = True
        
        wmi_conn = wmi.WMI(namespace=WMI_NAMESPACE)
        instances = wmi_conn.query(f"SELECT * FROM {DEFAULT_WMI_SET_CLASS}")
        if not instances:
            log_message("错误: 无法获取WMI Set实例。")
            return
        wmi_set_obj = instances[0]

        # 1. 取得软件控制权
        log_message("正在取得软件风扇控制权...")
        # 【最终修复】使用与主程序一致的高级wmi调用方式，简单且可靠
        getattr(wmi_set_obj, SET_CUSTOM_FAN_STATUS)(Data=1.0)
        getattr(wmi_set_obj, SET_SUPER_QUIET)(Data=0.0)
        getattr(wmi_set_obj, SET_AUTO_FAN_STATUS)(Data=0.0)
        getattr(wmi_set_obj, SET_STEP_FAN_STATUS)(Data=0.0)
        
        # 2. 设置80%的风扇速度
        raw_speed = float(math.ceil(0.80 * 229.0))
        log_message(f"正在设置风扇速度为 {raw_speed} (80%)...")
        getattr(wmi_set_obj, SET_CUSTOM_FAN_SPEED)(Data=raw_speed)
        getattr(wmi_set_obj, SET_GPU_FAN_DUTY)(Data=raw_speed)
        
        log_message("成功设置紧急风扇速度。")
        
    except Exception:
        log_message("错误: 设置紧急风扇速度失败。")
        log_message(traceback.format_exc())
    finally:
        if com_initialized:
            try:
                pythoncom.CoUninitialize()
                log_message("COM库已反初始化。")
            except Exception:
                log_message("警告: COM库反初始化失败。")
        log_message("紧急风扇设置脚本结束。")

if __name__ == "__main__":
    set_emergency_fan_speed()