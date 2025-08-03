# tools/localization.py
# -*- coding: utf-8 -*-
"""
Handles internationalization (i18n) for the application.
Loads language strings from a JSON file and provides a translation function.
"""

import json
import os
import sys
from typing import Dict

# Import settings needed for defaults and paths
from config.settings import (
    DEFAULT_LANGUAGE,
    KNOWN_LANGUAGES
)

# --- Default English Translations (Used for fallback and creating default languages.json) ---
# ... (DEFAULT_ENGLISH_TRANSLATIONS dictionary remains the same) ...
DEFAULT_ENGLISH_TRANSLATIONS: Dict[str, str] = {
    # Window & UI Elements
    "window_title": "Fan & Battery Control",
    "cpu_temp_label": "CPU Temp:",
    "gpu_temp_label": "GPU Temp:",
    "fan1_rpm_label": "Fan 1 RPM:",
    "fan2_rpm_label": "Fan 2 RPM:",
    "applied_target_label": "Applied / Target:",
    "status_label": "Status:",
    "fan_mode_label": "Fan Mode:",
    "mode_auto": "Auto",
    "mode_manual": "Manual", # UI label, maps to "fixed" internally
    "manual_speed_label": "Manual Speed:",
    "charge_policy_label": "Charge Policy:",
    "mode_standard": "Standard",
    "mode_custom": "Custom",
    "charge_threshold_label": "Charge Limit:",
    "cpu_curve_button": "CPU Curve",
    "gpu_curve_button": "GPU Curve",
    "language_label": "Language:",
    "reset_curve_button": "Reset Curve",
    "battery_info_label": "Battery:",
    "start_on_boot_label": "Start on Boot",
    "percent_unit": "%",
    "rpm_unit": " RPM",
    "celsius_unit": "°C",

    # Tooltips & Hints
    "curve_point_tooltip": "Drag to adjust | Temp: {temp}°C | Speed: {speed}%",
    "add_point_info": "Double-click empty space to add point.",
    "delete_point_info": "Right-click point to delete.",
    "policy_standard_tooltip": "Standard charging policy (usually full charge).",
    "policy_custom_tooltip": "Custom charging policy (uses charge limit slider).",
    "threshold_slider_tooltip": "Set the maximum charge percentage (only active in Custom mode).",
    "profile_button_tooltip": "Left-Click: Activate Profile\nRight-Click: Save Current Settings to Profile\nDouble-Click: Rename Profile",
    "start_on_boot_tooltip": "Automatically start the application with Windows (requires Admin, uses Task Scheduler).",

    # Status Messages
    "initializing": "Initializing...",
    "ready": "Ready",
    "paused": "Paused (Hidden)",
    "saving_config": "Configuration saved.",
    "applying_settings": "Applying settings...",
    "shutting_down": "Shutting down...",
    "profile_activated": "Profile '{name}' activated.",
    "profile_saved": "Current settings saved to profile '{name}'.",
    "profile_renamed": "Profile renamed to '{new_name}'.",

    # Error Messages & Titles
    "config_load_error_title": "Configuration Error",
    "config_load_error_msg": "Could not load or parse '{filename}'.\nUsing default settings.\n\nError: {error}",
    "config_save_error_title": "Configuration Save Error",
    "config_save_error_msg": "Could not save configuration to '{filename}'.\n\nError: {error}",
    "wmi_init_error_title": "WMI Initialization Error",
    "wmi_init_error_msg": "Failed to initialize WMI communication.\nEnsure Gigabyte software/drivers are installed and running.\nThe application may not function correctly.\n\nError: {error}",
    "wmi_error": "WMI Error",
    "temp_error": "ERR",
    "rpm_error": "ERR",
    "policy_error": "ERR",
    "threshold_error": "ERR",
    "unknown_mode": "Unknown",
    "delete_point_error_title": "Delete Point Error",
    "delete_point_error_msg": "Cannot delete point. Minimum of {min_points} points required.",
    "dependency_error_title": "Dependency Error",
    "dependency_error_msg": "Error: Missing required library '{name}'.\nPlease install the necessary packages:\npip install {packages}",
    "rename_profile_title": "Rename Profile",
    "rename_profile_label": "Enter new name for '{old_name}':",
    "rename_profile_error_title": "Rename Error",
    "rename_profile_error_empty": "Profile name cannot be empty.",
    "rename_profile_error_duplicate": "Profile name '{new_name}' already exists.",
    "registry_error_title": "Startup Registry Error", # Kept for potential future use, though Task Scheduler is preferred
    "registry_write_error_msg": "Could not modify Windows startup settings.\nPlease check permissions or run as administrator if needed.\n\nError: {error}",
    "icon_load_error_title": "Icon Error",
    "icon_load_error_msg": "Could not load application icon '{path}'. Tray icon will be default.",
    "admin_required_title": "Administrator Privileges Required",
    "admin_required_msg": "This application requires administrator privileges to function correctly (especially for fan/battery control and auto-start).\nPlease restart the application as an administrator.",
    "elevation_error_title": "Elevation Error",
    "elevation_error_msg": "Failed to automatically elevate privileges.\nPlease run the application manually as an administrator.",
    "task_scheduler_error_title": "Task Scheduler Error",
    "task_scheduler_error_msg": "Failed to create or delete the startup task.\nPlease check Task Scheduler permissions or logs.\n\nCommand: {command}\n\nError: {error}",
    "task_check_error_msg": "Failed to check startup task status.\n\nError: {error}",
    "task_scheduler_permission_error": "Task Scheduler operation requires administrator privileges.", # Specific error hint
    "task_scheduler_xml_error": "There was an error processing the Task Scheduler XML definition.", # Specific error hint
    "language_load_error_title": "Language File Error",
    "language_load_error_msg": "Could not load or parse '{filename}'.\nUsing default English translations.\n\nError: {error}",
    "language_save_error_title": "Language File Save Error",
    "language_save_error_msg": "Could not save default language file to '{filename}'.\n\nError: {error}",
    "unhandled_exception_title": "Unhandled Exception",
    "single_instance_error_title": "Application Already Running",
    "single_instance_error_msg": "Another instance of {app_name} is already running.\nActivating the existing window.",
    "single_instance_fallback_msg": "Could not activate the existing window. Please close the other instance manually.",

    # Curve Plot Labels
    "temp_axis_label": "Temperature (°C)",
    "speed_axis_label": "Fan Speed (%)",
    "cpu_temp_indicator_label": "CPU Temp", # Legend label (if needed, currently not shown)
    "gpu_temp_indicator_label": "GPU Temp", # Legend label (if needed)
    "cpu_speed_indicator_label": "CPU Target Speed", # Legend label (if needed)
    "gpu_speed_indicator_label": "GPU Target Speed", # Legend label (if needed)
    "cpu_curve_legend_label": "CPU Curve",
    "gpu_curve_legend_label": "GPU Curve",

    # Profile Names
    "default_profile_name": "Configuration {num}", # Used by ConfigManager

    # Confirmation Dialogs
    "reset_curve_confirm_title": "Confirm Reset",
    "reset_curve_confirm_msg": "Reset the current {curve_type} curve to default values?",

    # Tray Menu
    "tray_menu_show_hide": "Show / Hide",
    "tray_menu_quit": "Quit",

    # Language Display Names (Self-reference within each language file is preferred)
    # These are fallbacks used if a language file doesn't define its own display name.
    "lang_display_name_en": KNOWN_LANGUAGES.get("en", "English"),
    "lang_display_name_zh": KNOWN_LANGUAGES.get("zh", "中文"),
    # Add fallbacks for other languages defined in KNOWN_LANGUAGES
}

# --- Global Translation Variables ---
_translations: Dict[str, Dict[str, str]] = {}
_current_language: str = DEFAULT_LANGUAGE
_translations_loaded: bool = False

# --- Language Loading Function ---
def load_translations(file_path: str, force_reload: bool = False) -> Dict[str, Dict[str, str]]:
    """
    Loads translations from the specified JSON file.
    Creates a default English file if the specified file doesn't exist or is invalid.
    Merges loaded translations with defaults to ensure all keys are present.
    """
    global _translations, _current_language, _translations_loaded
    if _translations_loaded and not force_reload:
        return _translations

    default_data = {DEFAULT_LANGUAGE: DEFAULT_ENGLISH_TRANSLATIONS.copy()}
    loaded_data = {}
    write_default_file = False

    try:
        if os.path.exists(file_path):
            # Check if file is empty before trying to load
            if os.path.getsize(file_path) > 0:
                with open(file_path, 'r', encoding='utf-8') as f:
                    loaded_data = json.load(f)
                if not isinstance(loaded_data, dict):
                    print(f"Warning: Invalid format in language file '{file_path}'. Using default English.", file=sys.stderr)
                    loaded_data = {}
                    write_default_file = True # Overwrite invalid file
            else:
                # File exists but is empty
                print(f"Warning: Language file '{file_path}' is empty. Using default English.", file=sys.stderr)
                loaded_data = {}
                write_default_file = True # Overwrite empty file
        else:
            # File not found, create default English file
            print(f"Language file '{file_path}' not found. Creating default English file.")
            loaded_data = {} # Start with empty data
            write_default_file = True

    except (json.JSONDecodeError, IOError) as e:
        # Log error and force using defaults, overwrite corrupted file
        print(f"Error: Could not load or parse language file '{file_path}'. Using default English.\nError: {e}", file=sys.stderr)
        loaded_data = {}
        write_default_file = True
    except Exception as e:
        # Catch other potential errors during file access/loading
        print(f"Error: Unexpected error loading language file '{file_path}'. Using default English.\nError: {e}", file=sys.stderr)
        loaded_data = {}
        # Decide if you want to overwrite on unexpected errors, maybe not?
        # write_default_file = True

    # Write the default file if needed (missing, empty, or invalid format)
    if write_default_file:
        try:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(default_data, f, indent=4, ensure_ascii=False)
            print(f"Default language file saved/overwritten at '{file_path}'.")
        except IOError as e:
            print(f"Error: Could not save default language file to '{file_path}'.\nError: {e}", file=sys.stderr)
            # Continue with default data in memory even if saving failed

    # Merge loaded data with defaults
    final_translations = default_data.copy()
    for lang_code, translations in loaded_data.items():
        if isinstance(translations, dict):
            merged_lang = DEFAULT_ENGLISH_TRANSLATIONS.copy()
            merged_lang.update(translations)
            final_translations[lang_code] = merged_lang
        else:
            print(f"Warning: Invalid translation data for language '{lang_code}' in '{file_path}'. Using default English.", file=sys.stderr)
            final_translations[lang_code] = DEFAULT_ENGLISH_TRANSLATIONS.copy()

    _translations = final_translations
    if DEFAULT_LANGUAGE not in _translations:
         _translations[DEFAULT_LANGUAGE] = DEFAULT_ENGLISH_TRANSLATIONS.copy()

    _translations_loaded = True
    return _translations

# --- Set Current Language ---
def set_language(lang_code: str):
    """Sets the active language for the tr function."""
    # ... (function content unchanged) ...
    global _current_language, _translations
    if lang_code in _translations:
        _current_language = lang_code
    else:
        print(f"Warning: Language code '{lang_code}' not found in loaded translations. Falling back to '{DEFAULT_LANGUAGE}'.", file=sys.stderr)
        _current_language = DEFAULT_LANGUAGE


# --- Translation Function ---
def tr(key: str, **kwargs) -> str:
    """
    Translates a given key using the current language setting.
    """
    # ... (function content unchanged) ...
    global _current_language, _translations

    # Ensure translations are loaded (should be called explicitly early on)
    if not _translations_loaded:
        print("Warning: Attempting to translate before translations are loaded. Loading defaults now.", file=sys.stderr)
        load_translations() # Attempt to load

    # Get the dictionary for the current language, fallback to English dict
    lang_dict = _translations.get(_current_language)
    if lang_dict is None:
        lang_dict = _translations.get(DEFAULT_LANGUAGE)

    # If even English isn't loaded (severe error), use the hardcoded defaults
    if lang_dict is None:
        lang_dict = DEFAULT_ENGLISH_TRANSLATIONS

    # Get the translation, falling back to English if needed, then to the key itself
    translation = lang_dict.get(key)
    if translation is None and _current_language != DEFAULT_LANGUAGE:
        # Try fallback to default English
        default_lang_dict = _translations.get(DEFAULT_LANGUAGE, DEFAULT_ENGLISH_TRANSLATIONS)
        translation = default_lang_dict.get(key)

    # If still not found, use the key itself as the translation
    if translation is None:
        translation = key

    # Apply formatting if arguments are provided
    try:
        return translation.format(**kwargs)
    except (KeyError, ValueError, TypeError) as e:
        # Error during formatting, return the raw translation or key with an error marker
        print(f"Warning: Formatting error for key '{key}' in language '{_current_language}'. Error: {e}", file=sys.stderr)
        return f"{translation} [FORMAT ERR]"


# --- Get Available Languages ---
def get_available_languages() -> Dict[str, str]:
    """
    Returns a dictionary of available language codes and their display names.
    """
    # ... (function content unchanged) ...
    global _translations
    if not _translations_loaded:
        load_translations()

    available = {}
    for code in sorted(_translations.keys()):
        lang_dict = _translations[code]
        display_name_key = f"lang_display_name_{code}"
        # Prefer name from translation file, fallback to settings.KNOWN_LANGUAGES, fallback to code
        display_name = lang_dict.get(display_name_key, KNOWN_LANGUAGES.get(code, code.upper()))
        available[code] = display_name
    return available


# --- Get Current Language ---
def get_current_language() -> str:
    """Returns the currently set language code."""
    # ... (function content unchanged) ...
    return _current_language