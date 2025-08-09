# tools/task_scheduler.py
# -*- coding: utf-8 -*-
"""
Functions for interacting with the Windows Task Scheduler to manage
application startup on boot/resume. Requires administrator privileges.
"""

import os
import sys
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from typing import List, Tuple

# Import settings for task name, paths, arguments
from config.settings import (
    TASK_SCHEDULER_NAME,
    STARTUP_ARG_MINIMIZED
)
# Import utilities for path finding
from .system_utils import get_application_executable_path, get_application_script_path_for_task
# Import localization for error messages
from .localization import tr

def _run_schtasks(args: List[str]) -> Tuple[bool, str]:
    """Helper function to run schtasks.exe command."""
    if os.name != 'nt':
        return False, "Task Scheduler functions are only available on Windows."
 
    command = ['schtasks'] + args
    command_str = " ".join(command)

    try:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,
            startupinfo=startupinfo,
            encoding='utf-8',
            errors='ignore'
        )
        return True, result.stdout
    except FileNotFoundError:
        return False, "Error: 'schtasks.exe' not found. Is it in your system's PATH?"
    except subprocess.CalledProcessError as e:
        error_output = (e.stderr or "") + (e.stdout or "")
        error_msg = f"schtasks command failed with exit code {e.returncode}.\nCommand: {command_str}\nError: {error_output.strip()}"
        return False, error_msg
    except Exception as e:
        return False, f"An unexpected error occurred running schtasks.\nCommand: {command_str}\nError: {e}"

def _build_task_xml(task_name: str, start_command: str, start_arguments: str, working_directory: str) -> bytes:
    """Builds the Task Scheduler XML content using ElementTree for robustness."""
    
    # Root element with namespace
    ns = "http://schemas.microsoft.com/windows/2004/02/mit/task"
    ET.register_namespace('', ns)
    root = ET.Element("Task", version="1.4")

    # Registration Info
    reg_info = ET.SubElement(root, "RegistrationInfo")
    ET.SubElement(reg_info, "Description").text = f"Starts {task_name} on user logon or system resume."
    ET.SubElement(reg_info, "URI").text = f"\\{task_name}"

    # Triggers
    triggers = ET.SubElement(root, "Triggers")
    logon_trigger = ET.SubElement(triggers, "LogonTrigger")
    ET.SubElement(logon_trigger, "Enabled").text = "true"
    
    event_trigger = ET.SubElement(triggers, "EventTrigger")
    ET.SubElement(event_trigger, "Enabled").text = "true"
    subscription = ET.SubElement(event_trigger, "Subscription")
    subscription.text = (
        "<QueryList><Query Id='0' Path='System'>"
        "<Select Path='System'>*[System[Provider[@Name='Microsoft-Windows-Kernel-Power'] and (EventID=107)]]</Select>"
        "</Query></QueryList>"
    )

    # Principals
    principals = ET.SubElement(root, "Principals")
    principal = ET.SubElement(principals, "Principal", id="Author")
    ET.SubElement(principal, "LogonType").text = "InteractiveToken"
    ET.SubElement(principal, "RunLevel").text = "HighestAvailable"

    # Settings
    settings = ET.SubElement(root, "Settings")
    ET.SubElement(settings, "MultipleInstancesPolicy").text = "IgnoreNew"
    ET.SubElement(settings, "DisallowStartIfOnBatteries").text = "false"
    ET.SubElement(settings, "StopIfGoingOnBatteries").text = "false"
    ET.SubElement(settings, "AllowHardTerminate").text = "true"
    ET.SubElement(settings, "StartWhenAvailable").text = "true"
    ET.SubElement(settings, "RunOnlyIfNetworkAvailable").text = "false"
    idle_settings = ET.SubElement(settings, "IdleSettings")
    ET.SubElement(idle_settings, "StopOnIdleEnd").text = "true"
    ET.SubElement(idle_settings, "RestartOnIdle").text = "false"
    ET.SubElement(settings, "AllowStartOnDemand").text = "true"
    ET.SubElement(settings, "Enabled").text = "true"
    ET.SubElement(settings, "Hidden").text = "false"
    ET.SubElement(settings, "RunOnlyIfIdle").text = "false"
    ET.SubElement(settings, "WakeToRun").text = "false"
    ET.SubElement(settings, "ExecutionTimeLimit").text = "PT0S"
    ET.SubElement(settings, "Priority").text = "7"
    ET.SubElement(settings, "UseUnifiedSchedulingEngine").text = "true"

    # Actions
    actions = ET.SubElement(root, "Actions", Context="Author")
    exec_action = ET.SubElement(actions, "Exec")
    ET.SubElement(exec_action, "Command").text = start_command
    ET.SubElement(exec_action, "Arguments").text = start_arguments
    ET.SubElement(exec_action, "WorkingDirectory").text = working_directory

    # Serialize to XML string with UTF-16 encoding as required by schtasks
    return ET.tostring(root, encoding='utf-16', xml_declaration=True)

def create_startup_task(base_dir: str) -> Tuple[bool, str]:
    """
    Creates or updates a Windows Task Scheduler task to run the application using a robust XML builder.
    """
    task_name = TASK_SCHEDULER_NAME
    app_exe_path = get_application_executable_path()
    app_script_path = get_application_script_path_for_task()
    is_frozen = not bool(app_script_path)

    if is_frozen:
        start_command = app_exe_path
        start_arguments = STARTUP_ARG_MINIMIZED
        working_directory = os.path.dirname(app_exe_path)
    else:
        start_command = sys.executable
        start_arguments = f'"{app_script_path}" {STARTUP_ARG_MINIMIZED}'
        working_directory = base_dir

    try:
        task_xml_content = _build_task_xml(task_name, start_command, start_arguments, working_directory)
    except Exception as e:
        error_msg = tr("task_scheduler_error_msg", command="XML Build", error=f"Failed to build task XML: {e}")
        return False, error_msg

    temp_xml_path = None
    try:
        with tempfile.NamedTemporaryFile(mode='wb', suffix=".xml", delete=False) as temp_xml_file:
            temp_xml_path = temp_xml_file.name
            temp_xml_file.write(task_xml_content)

        create_args_xml = ['/Create', '/TN', task_name, '/XML', temp_xml_path, '/F']
        success, output = _run_schtasks(create_args_xml)

        if not success:
            error_command_display = f"schtasks {' '.join(create_args_xml).replace(temp_xml_path, '<temp_path.xml>')}"
            if "70" in output or "ERROR: Access is denied." in output:
                 detailed_error = f"{output}\n\n{tr('task_scheduler_permission_error')}"
            elif "XML" in output or "Error: The task XML is missing" in output:
                 detailed_error = f"{output}\n\n{tr('task_scheduler_xml_error')}"
            else:
                 detailed_error = output
            final_error_msg = tr("task_scheduler_error_msg", command=error_command_display, error=detailed_error)
            return False, final_error_msg
        else:
            return True, tr("task_created_success")
 
    except (IOError, Exception) as e:
        error_msg = tr("task_scheduler_error_msg", command="XML File Operation", error=f"Failed to write temporary XML file or run task: {e}")
        return False, error_msg
    finally:
        if temp_xml_path and os.path.exists(temp_xml_path):
            try:
                os.remove(temp_xml_path)
            except OSError:
                pass

def delete_startup_task() -> Tuple[bool, str]:
    """
    Deletes the application's startup task from Windows Task Scheduler.

    Returns:
        Tuple[bool, str]: (True if successful/already gone, message) or (False, error message).
    """
    task_name = TASK_SCHEDULER_NAME
    args = ['/Delete', '/TN', task_name, '/F'] # /F suppresses confirmation

    success, output = _run_schtasks(args)

    if not success:
        # Check if the error is simply that the task doesn't exist (which is success for deletion)
        if "ERROR: The system cannot find the file specified." in output:
            return True, tr("task_delete_failed_not_found")
        else:
            # Report other errors during deletion
            error_command_display = f"schtasks {' '.join(args)}"
            final_error_msg = tr("task_scheduler_error_msg", command=error_command_display, error=output)
            return False, final_error_msg
    else:
        return True, tr("task_deleted_success")

def is_startup_task_registered() -> bool:
    """
    Checks if the application's startup task is registered in Task Scheduler.

    Returns:
        bool: True if the task exists, False otherwise or if an error occurs.
    """
    task_name = TASK_SCHEDULER_NAME
    args = ['/Query', '/TN', task_name]

    success, output = _run_schtasks(args)

    # schtasks /Query returns exit code 0 if found, non-zero otherwise (usually 1 if not found)
    # We only return True if the command succeeded (exit code 0)
    if not success:
        # Don't show error message here, just return False
        # Let the calling code decide whether to show an error based on context
        # Example: if "ERROR: The system cannot find the file specified." not in output:
        #     print(f"Error checking task status: {output}") # Optional logging
        pass
    return success