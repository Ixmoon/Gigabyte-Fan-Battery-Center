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
    MIN_CHARGE_PERCENT, MAX_CHARGE_PERCENT,
    MIN_POINTS_FOR_INTERPOLATION # Used in validation indirectly
)
# Import localization for default profile names and error messages
from .localization import tr, get_available_languages, set_language, get_current_language

# Type Hinting
ProfileSettings = Dict[str, Any]
ConfigDict = Dict[str, Any]

class ConfigManager:
    """Handles loading, saving, and validation of application configuration."""

    def __init__(self, base_dir: str):
        """
        Initializes the ConfigManager.

        Args:
            base_dir: The absolute base directory of the application.
        """
        self.base_dir = base_dir # Store base directory
        self.filename = os.path.join(self.base_dir, CONFIG_FILE_NAME)
        # Default structure is generated dynamically using potentially translated names
        self.config: ConfigDict = self._get_default_config() # Load defaults initially

    def _get_default_profile_settings(self) -> ProfileSettings:
        """Returns a dictionary containing all default settings for a single profile."""
        # Simply return the imported default settings dictionary
        # Make a deep copy to avoid modifying the original constant
        return {k: (list(v) if isinstance(v, list) else v) for k, v in DEFAULT_PROFILE_SETTINGS.items()}

    def _get_default_config(self) -> ConfigDict:
        """Returns the structure for the entire default configuration file."""
        default_profiles = {}
        profile_defaults = self._get_default_profile_settings()
        for i in range(1, NUM_PROFILES + 1):
            # Use tr() to get the potentially translated default name
            profile_name = tr("default_profile_name", num=i)
            # Ensure uniqueness if default names clash (e.g., after language change)
            unique_name = profile_name
            counter = 1
            while unique_name in default_profiles:
                unique_name = f"{profile_name} ({counter})"
                counter += 1
            default_profiles[unique_name] = profile_defaults.copy() # Use a copy

        # Determine the first profile name to set as active default
        # Need to handle the potential unique naming applied above
        first_profile_name = tr("default_profile_name", num=1)
        if first_profile_name not in default_profiles:
            # Find the name that starts with the base default name
            base_name = tr("default_profile_name", num=1)
            found = False
            for name in default_profiles.keys():
                if name.startswith(base_name):
                    first_profile_name = name
                    found = True
                    break
            if not found: # Should not happen if logic is correct, but fallback
                first_profile_name = list(default_profiles.keys())[0]

        return {
            "app_version": "0.0.0", # Will be updated on first save
            "language": DEFAULT_LANGUAGE,
            "start_on_boot": DEFAULT_START_ON_BOOT,
            "window_geometry": None, # Hex string or None
            "active_profile_name": first_profile_name,
            "profiles": default_profiles
        }

    def _is_valid_fan_table(self, table: Any) -> bool:
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
            # Allow slightly higher temp for curve end point flexibility during editing
            if not (MIN_TEMP_C <= temp <= MAX_TEMP_C + 20): return False
            if not (MIN_FAN_PERCENT <= speed <= MAX_FAN_PERCENT): return False
            # Check for monotonicity (temp must increase, speed must not decrease)
            # Allow duplicate temps ONLY if speed is non-decreasing
            if temp in temps and speed < last_speed: return False
            if temp < last_temp: return False
            if speed < last_speed: return False # Speed must be non-decreasing

            temps.add(temp)
            last_temp = temp
            last_speed = speed
        return True

    def _validate_profile_settings(self, settings: Any) -> Optional[ProfileSettings]:
        """Validates a loaded profile dictionary against defaults."""
        if not isinstance(settings, dict):
            return None

        validated = self._get_default_profile_settings() # Start with fresh defaults
        default_keys = validated.keys()

        for key in default_keys:
            if key in settings:
                loaded_value = settings[key]
                default_value = validated[key] # Get default from the fresh copy
                expected_type = type(default_value)

                # Handle specific complex types first
                if key in ["cpu_fan_table", "gpu_fan_table"]:
                    if self._is_valid_fan_table(loaded_value):
                        # Ensure points are sorted by temperature
                        validated[key] = sorted([list(p) for p in loaded_value], key=lambda x: x[0])
                    # else: keep default
                # Handle simple types and ranges
                elif isinstance(loaded_value, expected_type):
                    if key == "fan_mode":
                        # Allow legacy "manual" value from older configs
                        if loaded_value == "manual": loaded_value = "fixed"
                        if loaded_value in ["auto", "fixed"]:
                            validated[key] = loaded_value
                        # else: keep default
                    elif key == "charge_policy":
                        if loaded_value in ["standard", "custom"]:
                            validated[key] = loaded_value
                        # else: keep default
                    elif isinstance(loaded_value, (int, float)):
                        # Apply range checks based on key name patterns
                        if "PERCENT" in key or "SPEED" in key or "THRESHOLD" in key:
                            min_val, max_val = 0, 100
                            if key == "charge_threshold":
                                min_val = MIN_CHARGE_PERCENT # Use specific min if needed
                            if min_val <= loaded_value <= max_val:
                                validated[key] = loaded_value
                        elif "INTERVAL" in key or "DURATION" in key or "TIMEOUT" in key:
                            if loaded_value > 0: validated[key] = loaded_value
                        elif "STEP" in key or "SIZE" in key or "RADIUS" in key:
                            if loaded_value > 0: validated[key] = loaded_value
                        elif "ALPHA" in key:
                             if 0.0 <= loaded_value <= 1.0: validated[key] = loaded_value
                        else: # No specific range check needed for this numeric type
                            validated[key] = loaded_value
                    elif isinstance(loaded_value, str):
                        if "COLOR" in key:
                            # Basic hex color validation
                            if loaded_value.startswith('#') and len(loaded_value) in [7, 9]:
                                try: int(loaded_value[1:], 16); validated[key] = loaded_value
                                except ValueError: pass # Invalid hex, keep default
                        else: # No specific validation for this string type
                            validated[key] = loaded_value
                    else: # Other types (e.g., bool) - just check type match
                        validated[key] = loaded_value
                # else: Type mismatch, keep default value
            # else: Key missing from loaded settings, keep default value

        return validated

    def load_config(self) -> ConfigDict:
        """Loads configuration from the file, validates, and applies defaults."""
        # Ensure translations are loaded so tr() works for default profile names
        # (This should ideally be done once in main.py before ConfigManager is used)
        # from .localization import load_translations # Avoid circular import if possible
        # load_translations() # Call if not guaranteed to be loaded earlier

        default_config = self._get_default_config() # Gets defaults using tr()

        try:
            if not os.path.exists(self.filename):
                # Config file doesn't exist, use defaults and save a new one
                self.config = default_config
                self.save_config() # Save the newly created default config
                set_language(self.config["language"]) # Set language based on default
                return self.config

            # Load existing config file
            with open(self.filename, 'r', encoding='utf-8') as f:
                loaded_config = json.load(f)

            if not isinstance(loaded_config, dict):
                raise ValueError("Configuration file is not a valid JSON object.")

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
                from PyQt6.QtWidgets import QMessageBox, QApplication
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
                from PyQt6.QtWidgets import QMessageBox, QApplication
                if QApplication.instance():
                    QMessageBox.critical(None, error_title, error_msg)
            except ImportError:
                pass
        except Exception as e: # Catch unexpected errors during save
            error_title = tr("config_save_error_title")
            error_msg = tr("config_save_error_msg", filename=self.filename, error=f"Unexpected error: {e}")
            print(f"Error - {error_title}: {error_msg}", file=sys.stderr)
            try:
                from PyQt6.QtWidgets import QMessageBox, QApplication
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