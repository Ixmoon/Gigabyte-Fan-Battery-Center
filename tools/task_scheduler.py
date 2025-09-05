# -*- coding: utf-8 -*-
"""
用于与Windows任务计划程序交互以管理应用启动的函数。
现在使用外部XML模板以增强灵活性。
"""
import os
import sys
import subprocess
import tempfile
from typing import Tuple
from config.settings import TASK_SCHEDULER_NAME, STARTUP_ARG_MINIMIZED, TASK_XML_FILE_NAME
from .system_utils import get_application_executable_path, get_application_script_path_for_task
from .localization import tr

def _run_schtasks(args: list[str]) -> Tuple[bool, str]:
    """运行schtasks.exe命令的辅助函数，并正确处理输出编码。"""
    if os.name != 'nt': return False, "Task Scheduler is only for Windows."
    command = ['schtasks'] + args
    try:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        
        result = subprocess.run(command, capture_output=True, check=True, startupinfo=startupinfo)
        
        encoding = sys.stdout.encoding or ('mbcs' if os.name == 'nt' else 'utf-8')
        output = result.stdout.decode(encoding, errors='ignore')
        return True, output

    except (FileNotFoundError, subprocess.CalledProcessError, Exception) as e:
        encoding = sys.stdout.encoding or ('mbcs' if os.name == 'nt' else 'utf-8')
        error_output_bytes = getattr(e, 'stderr', b'') or getattr(e, 'stdout', b'')
        error_output = error_output_bytes.decode(encoding, errors='ignore') if error_output_bytes else str(e)
        return False, f"schtasks command failed: {error_output.strip()}"

def _get_default_task_xml_content() -> bytes:
    """
    返回一个带有BOM前缀、utf-16-le编码的字节序列。
    这是确保内容正确的'schtasks'最可靠的方法。
    """
    xml_str = r'''<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Starts the FanBatteryControl application on user logon and system wake.</Description>
    <Author>FanBatteryControl</Author>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
    </LogonTrigger>
    <EventTrigger>
      <Enabled>true</Enabled>
      <Subscription>&lt;QueryList&gt;&lt;Query Id="0" Path="System"&gt;&lt;Select Path="System"&gt;*[System[Provider[@Name='Microsoft-Windows-Kernel-Power'] and (EventID=107)]]&lt;/Select&gt;&lt;/Query&gt;&lt;/QueryList&gt;</Subscription>
    </EventTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>HighestAvailable</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>false</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>true</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{{COMMAND}}</Command>
      <Arguments>{{ARGUMENTS}}</Arguments>
      <WorkingDirectory>{{WORKING_DIRECTORY}}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
'''
    # 添加BOM前缀并编码为UTF-16 Little Endian
    return b'\xff\xfe' + xml_str.encode('utf-16-le')

def create_startup_task(base_dir: str):
    """
    使用外部XML模板创建或更新Windows任务计划程序任务。
    如果模板不存在，则创建一个默认模板。
    """
    xml_path = os.path.join(base_dir, TASK_XML_FILE_NAME)

    if not os.path.exists(xml_path):
        try:
            default_xml_bytes = _get_default_task_xml_content()
            # 以二进制模式写入模板文件以保留BOM和编码
            with open(xml_path, 'wb') as f:
                f.write(default_xml_bytes)
            print(f"默认任务模板已创建于: {xml_path}")
        except IOError as e:
            raise Exception(f"创建默认任务模板失败: {e}")

    try:
        # 以二进制模式读取模板文件并用'utf-16'解码
        with open(xml_path, 'rb') as f:
            xml_template_bytes = f.read()
        # Python的'utf-16'解码器能正确处理BOM
        xml_template = xml_template_bytes.decode('utf-16')
    except IOError as e:
        raise Exception(f"读取任务模板文件失败: {e}")

    app_exe_path = get_application_executable_path()
    app_script_path = get_application_script_path_for_task()
    is_frozen = not bool(app_script_path)
    
    command = app_exe_path
    if not is_frozen:
        command = sys.executable
        arguments = f'"{app_script_path}" {STARTUP_ARG_MINIMIZED}'
    else:
        arguments = STARTUP_ARG_MINIMIZED
        
    working_dir = base_dir

    final_xml_content_str = xml_template.replace("{{COMMAND}}", command)
    final_xml_content_str = final_xml_content_str.replace("{{ARGUMENTS}}", arguments)
    final_xml_content_str = final_xml_content_str.replace("{{WORKING_DIRECTORY}}", working_dir)
    
    final_xml_bytes = b'\xff\xfe' + final_xml_content_str.encode('utf-16-le')

    temp_path = ""
    try:
        with tempfile.NamedTemporaryFile(mode='wb', suffix=".xml", delete=False) as temp_file:
            temp_path = temp_file.name
            temp_file.write(final_xml_bytes)
        
        success, output = _run_schtasks(['/Create', '/TN', TASK_SCHEDULER_NAME, '/XML', temp_path, '/F'])
        
        if not success:
            raise Exception(tr("task_scheduler_error_msg", command=f"Create {TASK_SCHEDULER_NAME}", error=output))
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)

def delete_startup_task():
    """从Windows任务计划程序中删除应用的启动任务。"""
    success, output = _run_schtasks(['/Delete', '/TN', TASK_SCHEDULER_NAME, '/F'])
    if not success and "ERROR: The system cannot find the file specified." not in output:
        raise Exception(tr("task_scheduler_error_msg", command=f"Delete {TASK_SCHEDULER_NAME}", error=output))

def is_startup_task_registered() -> bool:
    """检查应用的启动任务是否已在任务计划程序中注册。"""
    success, _ = _run_schtasks(['/Query', '/TN', TASK_SCHEDULER_NAME])
    return success