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
from typing import List, Tuple

# Import settings for task name, paths, arguments
from config.settings import (
    TASK_SCHEDULER_NAME,
    STARTUP_ARG_MINIMIZED,
    TASK_XML_FILE_NAME
)
# Import utilities for path finding
from .system_utils import get_application_executable_path, get_application_script_path_for_task
# Import localization for error messages
from .localization import tr

def _run_schtasks(args: List[str]) -> Tuple[bool, str]:
    """Helper function to run schtasks.exe command."""
    if os.name != 'nt':
        return False, "Task Scheduler functions are only available on Windows." # This is a developer-facing message, no need to translate
 
    command = ['schtasks'] + args
    command_str = " ".join(command)

    try:
        # Hide the console window when running schtasks
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True, # Raise CalledProcessError on non-zero exit code
            startupinfo=startupinfo,
            encoding='utf-8',
            errors='ignore' # Ignore potential decoding errors in output
        )
        return True, result.stdout
    except FileNotFoundError:
        error_msg = "Error: 'schtasks.exe' not found. Is it in your system's PATH?" # Developer-facing
        return False, error_msg
    except subprocess.CalledProcessError as e:
        # Combine stdout and stderr for error reporting as schtasks sometimes uses stdout for errors
        error_output = (e.stderr or "") + (e.stdout or "")
        error_msg = f"schtasks command failed with exit code {e.returncode}.\nCommand: {command_str}\nError: {error_output.strip()}"
        return False, error_msg
    except Exception as e:
        error_msg = f"An unexpected error occurred running schtasks.\nCommand: {command_str}\nError: {e}" # Developer-facing
        return False, error_msg

def create_startup_task(base_dir: str) -> Tuple[bool, str]:
    """
    Creates or updates a Windows Task Scheduler task to run the application.

    Triggers: On user logon, On system resume from sleep.
    Actions: Terminates existing instance, Starts new instance minimized.
    Settings: Runs with highest privileges, allowed on battery.

    Returns:
        Tuple[bool, str]: (True if successful, message) or (False, error message).
    """
    task_name = TASK_SCHEDULER_NAME
    app_exe_path = get_application_executable_path()
    app_script_path = get_application_script_path_for_task()
    is_frozen = getattr(sys, 'frozen', False)

    # Determine the command and arguments for the primary task action (starting the app)
    if is_frozen:
        start_command = app_exe_path
        start_arguments = STARTUP_ARG_MINIMIZED
        executable_base_name = os.path.basename(app_exe_path) # For taskkill
        working_directory = os.path.dirname(app_exe_path)
    else:
        # Run the script using the current Python interpreter
        start_command = sys.executable # Use the python/pythonw that launched this script
        start_arguments = f'"{app_script_path}" {STARTUP_ARG_MINIMIZED}'
        # Target the python interpreter for taskkill (risky if other scripts run)
        executable_base_name = os.path.basename(sys.executable)
        working_directory = base_dir # Run script from project root

    # Define the default Task XML template. Placeholders use .format() syntax.
    DEFAULT_TASK_XML_TEMPLATE = """<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Starts {task_name} on user logon or system resume. Ensures only one instance is running.</Description>
    <URI>\\{task_name}</URI>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
    </LogonTrigger>
    <EventTrigger>
      <Enabled>true</Enabled>
      <Subscription>
        <![CDATA[
          <QueryList>
            <Query Id="0" Path="System">
              <Select Path="System">*[System[Provider[@Name='Microsoft-Windows-Kernel-Power'] and (EventID=107)]]</Select>
            </Query>
          </QueryList>
        ]]>
      </Subscription>
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
    <StartWhenAvailable>true</StartWhenAvailable>
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
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit> <!-- No time limit -->
    <Priority>7</Priority> <!-- Below normal -->
    <UseUnifiedSchedulingEngine>true</UseUnifiedSchedulingEngine>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>"{start_command}"</Command>
      <Arguments>{start_arguments}</Arguments>
      <WorkingDirectory>{working_directory}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""
    # --- Load or Create Task XML Template ---
    xml_template_path = os.path.join(base_dir, TASK_XML_FILE_NAME)
    
    # If the template file doesn't exist, create it with the default content.
    if not os.path.exists(xml_template_path):
        try:
            with open(xml_template_path, 'w', encoding='utf-8') as f:
                # We write the unformatted default template.
                # The placeholders will be filled in later.
                f.write(DEFAULT_TASK_XML_TEMPLATE)
        except IOError:
            # If creation fails, we can't proceed with the external file.
            # We'll just use the in-memory default silently.
            pass

    # Now, try to load the template from the file path.
    # It should exist unless there was a write permission error above.
    task_xml_template = DEFAULT_TASK_XML_TEMPLATE # Default fallback
    try:
        with open(xml_template_path, 'r', encoding='utf-8') as f:
            task_xml_template = f.read()
    except (IOError, FileNotFoundError):
        # This will only be reached if the file creation failed.
        # Silently fall back to the default template.
        pass

    # Populate the template with dynamic values
    task_xml_content = task_xml_template.format(
        task_name=task_name,
        executable_base_name=executable_base_name,
        start_command=start_command,
        start_arguments=start_arguments,
        working_directory=working_directory
    )
    temp_xml_path = None
    try:
        # Create a temporary file for the XML (UTF-16 required by schtasks /XML)
        with tempfile.NamedTemporaryFile(mode='w', suffix=".xml", delete=False, encoding='utf-16') as temp_xml_file:
            temp_xml_path = temp_xml_file.name
            temp_xml_file.write(task_xml_content)

        # Arguments for creating/updating the task using XML
        create_args_xml = ['/Create', '/TN', task_name, '/XML', temp_xml_path, '/F'] # /F forces update if exists

        # Run the command
        success, output = _run_schtasks(create_args_xml)

        if not success:
            # Construct error message using translations
            error_command_display = f"schtasks {' '.join(create_args_xml).replace(temp_xml_path, '<temp_path.xml>')}"
            if "70" in output or "ERROR: Access is denied." in output: # Access denied codes
                 detailed_error = f"{output}\n\n{tr('task_scheduler_permission_error')}"
            elif "XML" in output or "Error: The task XML is missing" in output: # XML errors
                 detailed_error = f"{output}\n\n{tr('task_scheduler_xml_error')}"
            else:
                 detailed_error = output
            final_error_msg = tr("task_scheduler_error_msg", command=error_command_display, error=detailed_error)
            return False, final_error_msg
        else:
            return True, tr("task_created_success")
 
    except IOError as e:
        error_msg = tr("task_scheduler_error_msg", command="XML File Operation", error=f"Failed to write temporary XML file: {e}")
        return False, error_msg
    except Exception as e:
        error_msg = tr("task_scheduler_error_msg", command="XML Task Creation", error=f"An unexpected error occurred: {e}")
        return False, error_msg
    finally:
        # Clean up the temporary XML file
        if temp_xml_path and os.path.exists(temp_xml_path):
            try:
                os.remove(temp_xml_path)
            except OSError:
                pass # Ignore cleanup errors

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