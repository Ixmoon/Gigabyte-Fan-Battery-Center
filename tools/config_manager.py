# tools/config_manager.py
# -*- coding: utf-8 -*-
"""
Manages application configuration loading, saving, validation, and profiles.
"""

import json
import os
import sys
from typing import Dict, List, Optional, Any

# Import settings for defaults and paths
from config.settings import (
    CONFIG_FILE_NAME,
    DEFAULT_LANGUAGE,
    DEFAULT_START_ON_BOOT,
    NUM_PROFILES,
    DEFAULT_PROFILE_SETTINGS,
    MIN_CURVE_POINTS,
    MIN_TEMP_C, MAX_TEMP_C,
    MIN_FAN_PERCENT, MAX_FAN_PERCENT,
    MIN_CHARGE_PERCENT,
    FAN_MODE_AUTO, FAN_MODE_FIXED,
    CHARGE_POLICY_STANDARD_STR, CHARGE_POLICY_CUSTOM_STR
)
# Import localization for default profile names and error messages
from .localization import tr, get_available_languages, set_language, get_current_language

# Type Hinting
ProfileSettings = Dict[str, Any]
ConfigDict = Dict[str, Any]

# --- Validation Helper Functions (Module-level) ---

def _is_valid_fan_table(table: Any) -> bool:
    """Validates the structure and values of a fan curve table."""
    if not isinstance(table, list) or len(table) < MIN_CURVE_POINTS:
        return False
    temps = set()
    last_temp = -1.0
    last_speed = -1.0
    for i, item in enumerate(table):
        if not isinstance(item, list) or len(item) != 2: return False
        if not all(isinstance(val, (int, float)) for val in item): return False
        temp, speed = item
        if not (MIN_TEMP_C <= temp <= MAX_TEMP_C + 20): return False
        if not (MIN_FAN_PERCENT <= speed <= MAX_FAN_PERCENT): return False
        if temp in temps and speed < last_speed: return False
        if temp < last_temp: return False
        if speed < last_speed: return False
        temps.add(temp)
        last_temp = temp
        last_speed = speed
    return True

def _validate_numeric(value: Any, default: Any, min_val: Optional[float] = None, max_val: Optional[float] = None) -> Any:
    """Validates a numeric value against a type and optional range."""
    if not isinstance(value, (int, float)):
        return default
    if min_val is not None and value < min_val:
        return default
    if max_val is not None and value > max_val:
        return default
    return value

def _validate_choice(value: Any, default: str, choices: List[str], legacy_map: Optional[Dict[str, str]] = None) -> str:
    """Validates a string value against a list of allowed choices."""
    if legacy_map and value in legacy_map:
        value = legacy_map[value]
    return value if isinstance(value, str) and value in choices else default

def _validate_color(value: Any, default: str) -> str:
    """Validates a hex color string."""
    if isinstance(value, str) and value.startswith('#') and len(value) in [7, 9]:
        try:
            int(value[1:], 16)
            return value
        except ValueError:
            pass
    return default

# --- ConfigManager Class ---

class ConfigManager:
    """Handles loading, saving, and validation of application configuration."""

    def __init__(self, base_dir: str):
        """
        Initializes the ConfigManager.

        Args:
            base_dir: The absolute base directory of the application.
        """
        self.base_dir = base_dir
        self.filename = os.path.join(self.base_dir, CONFIG_FILE_NAME)
        self.config: ConfigDict = self._get_default_config()

    def _get_default_profile_settings(self) -> ProfileSettings:
        """Returns a deep copy of the default settings for a single profile."""
        return {k: (list(v) if isinstance(v, list) else v) for k, v in DEFAULT_PROFILE_SETTINGS.items()}

    def _get_default_config(self) -> ConfigDict:
        """Returns the structure for the entire default configuration file."""
        default_profiles = {}
        profile_defaults = self._get_default_profile_settings()
        for i in range(1, NUM_PROFILES + 1):
            profile_name = tr("default_profile_name", num=i)
            unique_name = profile_name
            counter = 1
            while unique_name in default_profiles:
                unique_name = f"{profile_name} ({counter})"
                counter += 1
            default_profiles[unique_name] = profile_defaults.copy()

        first_profile_name = tr("default_profile_name", num=1)
        if first_profile_name not in default_profiles:
            base_name = tr("default_profile_name", num=1)
            for name in default_profiles.keys():
                if name.startswith(base_name):
                    first_profile_name = name
                    break
            else:
                first_profile_name = list(default_profiles.keys())[0]

        return {
            "app_version": "0.0.0",
            "language": DEFAULT_LANGUAGE,
            "start_on_boot": DEFAULT_START_ON_BOOT,
            "window_geometry": None,
            "active_profile_name": first_profile_name,
            "profiles": default_profiles
        }

    def _validate_profile_settings(self, settings: Any) -> Optional[ProfileSettings]:
        """Validates a loaded profile dictionary against defaults using helper functions."""
        if not isinstance(settings, dict):
            return None

        validated = self._get_default_profile_settings()
        
        for key, default_value in validated.items():
            loaded_value = settings.get(key)
            if loaded_value is None:
                continue

            if key in ["cpu_fan_table", "gpu_fan_table"]:
                if _is_valid_fan_table(loaded_value):
                    validated[key] = sorted([list(p) for p in loaded_value], key=lambda x: x[0])
            elif key == "fan_mode":
                validated[key] = _validate_choice(loaded_value, default_value, [FAN_MODE_AUTO, FAN_MODE_FIXED], {"manual": FAN_MODE_FIXED})
            elif key == "charge_policy":
                validated[key] = _validate_choice(loaded_value, default_value, [CHARGE_POLICY_STANDARD_STR, CHARGE_POLICY_CUSTOM_STR])
            elif "PERCENT" in key or "SPEED" in key or "THRESHOLD" in key:
                min_val = MIN_CHARGE_PERCENT if key == "charge_threshold" else 0
                validated[key] = _validate_numeric(loaded_value, default_value, min_val, 100)
            elif "INTERVAL" in key or "DURATION" in key or "TIMEOUT" in key or "STEP" in key or "SIZE" in key or "RADIUS" in key:
                validated[key] = _validate_numeric(loaded_value, default_value, min_val=0)
            elif "ALPHA" in key:
                validated[key] = _validate_numeric(loaded_value, default_value, 0.0, 1.0)
            elif "COLOR" in key:
                validated[key] = _validate_color(loaded_value, default_value)
            elif isinstance(loaded_value, type(default_value)):
                validated[key] = loaded_value
        
        return validated

    def load_config(self, force_reload: bool = False) -> ConfigDict:
        """
        Loads configuration from the file, validates, and applies defaults.

        Args:
            force_reload: If True, bypasses any cached config and re-reads from disk.
        """
        # If not forcing a reload and config is already populated, return the cached version.
        # The initial load will always proceed as self.config starts as a default structure.
        if not force_reload and self.config.get("app_version") != "0.0.0":
            return self.config

        # Ensure translations are loaded so tr() works for default profile names
        default_config = self._get_default_config() # Gets defaults using tr()

        try:
            if not os.path.exists(self.filename):
                # Config file doesn't exist, use defaults and save a new one
                self.config = default_config
                self.save_config() # Save the newly created default config
                set_language(self.config["language"]) # Set language based on default
                return self.config

            # Load existing config file
            print(f"Loading configuration from: {self.filename}")
            with open(self.filename, 'r', encoding='utf-8') as f:
                loaded_config = json.load(f)

            if not isinstance(loaded_config, dict):
                raise ValueError("Config file is not a valid JSON object.")

            # Start validation with a fresh default structure
            validated_config = self._get_default_config()
            validated_config["profiles"] = {} # Clear default profiles to fill from loaded

            # --- Validate Top-Level Settings ---
            available_langs = get_available_languages()
            loaded_lang = loaded_config.get("language", DEFAULT_LANGUAGE)
            if loaded_lang in available_langs:
                validated_config["language"] = loaded_lang
            else:
                validated_config["language"] = DEFAULT_LANGUAGE # Fallback
            # Set the global language based on the loaded/validated setting
            set_language(validated_config["language"])

            if isinstance(loaded_config.get("start_on_boot"), bool):
                validated_config["start_on_boot"] = loaded_config["start_on_boot"]
            if isinstance(loaded_config.get("window_geometry"), str):
                 validated_config["window_geometry"] = loaded_config["window_geometry"]
            # Ignore app_version from loaded file, will be updated on save

            # --- Validate Profiles ---
            loaded_profiles = loaded_config.get("profiles", {})
            if isinstance(loaded_profiles, dict):
                for name, settings in loaded_profiles.items():
                    if not isinstance(name, str) or not name: continue # Skip invalid names
                    validated_settings = self._validate_profile_settings(settings)
                    if validated_settings:
                        validated_config["profiles"][name] = validated_settings
            # else: Keep profiles empty, defaults will be added below

            # --- Ensure Correct Number of Profiles ---
            # Use tr() for default naming function
            default_profile_name_func = lambda i: tr("default_profile_name", num=i)
            existing_names = list(validated_config["profiles"].keys())
            num_existing = len(existing_names)

            if num_existing < NUM_PROFILES:
                # Add missing default profiles
                num_to_add = NUM_PROFILES - num_existing
                added_count = 0
                profile_defaults = self._get_default_profile_settings()
                for i in range(1, NUM_PROFILES + num_existing + 1): # Check beyond NUM_PROFILES if needed
                    if added_count >= num_to_add: break
                    potential_name = default_profile_name_func(i)
                    name_to_add = potential_name
                    counter = 1
                    # Ensure added name is unique among existing *and* newly added ones
                    while name_to_add in validated_config["profiles"]:
                        name_to_add = f"{potential_name} ({counter})"
                        counter += 1
                    validated_config["profiles"][name_to_add] = profile_defaults.copy()
                    added_count += 1
            elif num_existing > NUM_PROFILES:
                 # Trim excess profiles (keep the first NUM_PROFILES loaded)
                 profiles_to_keep = {name: validated_config["profiles"][name] for name in list(validated_config["profiles"])[:NUM_PROFILES]}
                 validated_config["profiles"] = profiles_to_keep

            # --- Validate Active Profile Name ---
            profile_names = list(validated_config["profiles"].keys())
            if not profile_names:
                 # Severe issue: No valid profiles found/created. Revert to full default.
                 print("Error: No valid profiles found after loading/validation. Reverting to full default config.", file=sys.stderr)
                 validated_config = self._get_default_config() # Gets defaults using tr()
                 set_language(validated_config["language"]) # Reset language too
            else:
                loaded_active_name = loaded_config.get("active_profile_name")
                if loaded_active_name in profile_names:
                    validated_config["active_profile_name"] = loaded_active_name
                else:
                    # Active profile not found, set to the first available one
                    validated_config["active_profile_name"] = profile_names[0]

            self.config = validated_config
            return self.config

        except (json.JSONDecodeError, IOError, TypeError, KeyError, AttributeError, ValueError) as e:
            # Use tr() for the error message box titles/text (requires GUI context or print fallback)
            error_title = tr("config_load_error_title")
            error_msg = tr("config_load_error_msg", filename=self.filename, error=str(e))
            print(f"Error - {error_title}: {error_msg}", file=sys.stderr) # Print error as GUI might not be up
            # Show message box if possible (requires QApplication instance)
            try:
                from gui.qt import QMessageBox, QApplication
                if QApplication.instance():
                    QMessageBox.warning(None, error_title, error_msg)
            except ImportError:
                pass # PyQt not available yet or failed import

            # Fallback to default config
            self.config = self._get_default_config() # Use fresh defaults (using tr())
            set_language(self.config["language"]) # Reset language
            try:
                self.save_config() # Attempt to save the defaults
            except Exception as save_e:
                print(f"Error saving default config after load error: {save_e}", file=sys.stderr)
            return self.config

    def save_config(self):
        """Saves the current configuration to the file."""
        try:
            # Ensure profiles are valid before saving
            if "profiles" in self.config and isinstance(self.config["profiles"], dict):
                profiles_to_save = {}
                for name, settings in self.config["profiles"].items():
                    # Re-validate on save to catch potential runtime modifications
                    validated_settings = self._validate_profile_settings(settings)
                    if validated_settings:
                        profiles_to_save[name] = validated_settings
                self.config["profiles"] = profiles_to_save
            else:
                # Invalid profiles structure, reset to default
                default_conf = self._get_default_config()
                self.config["profiles"] = default_conf["profiles"]
                self.config["active_profile_name"] = default_conf["active_profile_name"]

            # Ensure active profile exists
            if self.config.get("active_profile_name") not in self.config.get("profiles", {}):
                 profile_names = list(self.config.get("profiles", {}).keys())
                 if profile_names:
                     self.config["active_profile_name"] = profile_names[0]
                 else: # No profiles exist, reset active name from default
                     self.config["active_profile_name"] = self._get_default_config()["active_profile_name"]

            # Update app version in config before saving
            from config.settings import APP_VERSION
            self.config["app_version"] = APP_VERSION

            # Ensure directory exists
            os.makedirs(os.path.dirname(self.filename), exist_ok=True)

            # Save the validated config
            with open(self.filename, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)

        except (IOError, TypeError) as e:
            error_title = tr("config_save_error_title")
            error_msg = tr("config_save_error_msg", filename=self.filename, error=str(e))
            print(f"Error - {error_title}: {error_msg}", file=sys.stderr)
            try:
                from gui.qt import QMessageBox, QApplication
                if QApplication.instance():
                    QMessageBox.critical(None, error_title, error_msg)
            except ImportError:
                pass
        except Exception as e: # Catch unexpected errors during save
            error_title = tr("config_save_error_title")
            error_msg = tr("config_save_error_msg", filename=self.filename, error=f"Unexpected error: {e}")
            print(f"Error - {error_title}: {error_msg}", file=sys.stderr)
            try:
                from gui.qt import QMessageBox, QApplication
                if QApplication.instance():
                    QMessageBox.critical(None, error_title, error_msg)
            except ImportError:
                pass

    def get(self, key: str, default: Any = None) -> Any:
        """Gets a top-level configuration value."""
        return self.config.get(key, default)

    def set(self, key: str, value: Any):
        """Sets a top-level configuration value."""
        self.config[key] = value

    def get_profile_names(self) -> List[str]:
        """Returns a list of current profile names."""
        return list(self.config.get("profiles", {}).keys())

    def get_profile(self, name: str) -> Optional[ProfileSettings]:
        """Gets the settings dictionary for a specific profile."""
        return self.config.get("profiles", {}).get(name)

    def save_profile(self, name: str, settings: ProfileSettings):
        """Saves settings for a specific profile after validation."""
        validated_settings = self._validate_profile_settings(settings)
        if validated_settings:
            if "profiles" not in self.config or not isinstance(self.config["profiles"], dict):
                 self.config["profiles"] = {} # Initialize if missing
            self.config["profiles"][name] = validated_settings
        else:
            # Log attempt to save invalid settings
            print(f"Warning: Attempted to save invalid profile settings for '{name}'. Discarded.", file=sys.stderr)


    def rename_profile(self, old_name: str, new_name: str) -> bool:
        """Renames a profile."""
        profiles = self.config.get("profiles", {})
        if old_name not in profiles: return False # Old name doesn't exist
        if not new_name or not isinstance(new_name, str): return False # New name invalid
        new_name = new_name.strip()
        if not new_name: return False # New name empty after stripping
        # Check if new name exists (case-insensitive check recommended)
        if new_name.lower() != old_name.lower() and new_name.lower() in [n.lower() for n in profiles.keys()]:
            return False # New name already exists (and it's not just a case change)

        # Perform rename using a new dictionary
        new_profiles = {}
        for name, settings in profiles.items():
            if name == old_name:
                new_profiles[new_name] = settings
            else:
                new_profiles[name] = settings

        self.config["profiles"] = new_profiles

        # Update active profile name if it was the one renamed
        if self.get_active_profile_name() == old_name:
            self.set_active_profile_name(new_name)

        return True

    def get_active_profile_name(self) -> str:
        """Gets the name of the currently active profile."""
        active_name = self.config.get("active_profile_name")
        profile_names = self.get_profile_names()

        if not profile_names:
             # No profiles exist, return the default first profile name
             active_name = self._get_default_config()["active_profile_name"]
             self.config["active_profile_name"] = active_name # Fix config state
        elif active_name not in profile_names:
            # Active name is invalid, fallback to the first available profile
            active_name = profile_names[0]
            self.config["active_profile_name"] = active_name # Fix config state

        return active_name

    def set_active_profile_name(self, name: str):
        """Sets the active profile name."""
        if name in self.get_profile_names():
            self.config["active_profile_name"] = name
        else:
            print(f"Warning: Attempted to set invalid active profile name '{name}'. Ignored.", file=sys.stderr)

    def get_active_profile(self) -> Optional[ProfileSettings]:
        """Gets the settings dictionary for the currently active profile."""
        active_name = self.get_active_profile_name()
        return self.get_profile(active_name)

    def get_active_profile_setting(self, key: str, default_override: Any = None) -> Any:
        """Gets a specific setting from the active profile, with fallback to defaults."""
        active_profile = self.get_active_profile()
        if active_profile:
            # Use the profile's value if present, otherwise use the global default
            # Use default_override if provided, otherwise use the key's default from DEFAULT_PROFILE_SETTINGS
            default_value = default_override if default_override is not None else DEFAULT_PROFILE_SETTINGS.get(key)
            return active_profile.get(key, default_value)
        else:
            # No active profile found, return the global default or override
            return default_override if default_override is not None else DEFAULT_PROFILE_SETTINGS.get(key)