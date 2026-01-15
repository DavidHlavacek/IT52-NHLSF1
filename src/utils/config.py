"""
Configuration Utilities

Loads and manages configuration from config/settings.yaml

Configuration Hierarchy:
    1. Command-line arguments (highest priority)
    2. Config file (config/settings.yaml)
    3. Default values (lowest priority)
"""

import os
import logging
from typing import Any, Dict, Optional

# Try to import yaml, fall back to json if not available
try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False
    import json

logger = logging.getLogger(__name__)

# Default configuration for F1 Motion Simulator
# These are conservative defaults - tune based on hardware testing
DEFAULT_CONFIG = {
    "telemetry": {
        "port": 20777,           # F1 game default UDP port
        "buffer_size": 2048      # UDP receive buffer
    },

    "motion": {
        # Dimension selection (surge/sway/heave/pitch/roll)
        "dimension": "surge",

        # Washout filter settings
        "highpass_cutoff_hz": 1.0,  # Filter cutoff (0.5-2.0 Hz typical)

        # Gain settings
        "gain": 100.0,              # mm per G (or mm per radian for angles)

        # Anti-oscillation settings
        "deadband": 0.05,           # Input change threshold (G or radians)
        "slew_rate_limit": 500.0,   # Max position change rate (mm/s)

        # Actuator settings
        "stroke_mm": 900.0,         # Total actuator stroke
        "center_mm": 450.0,         # Center/home position
        "soft_limit_mm": 50.0,      # Safety margin from ends

        # Processing rate
        "update_rate_hz": 30.0      # Motion algorithm update rate
    },

    "hardware": {
        "smc": {
            # Serial connection
            "port": "/dev/ttyUSB0",     # Linux default (use COM3 on Windows)
            "baudrate": 38400,          # Fixed by SMC protocol
            "parity": "N",              # No parity (some use 'E')
            "controller_id": 1,         # Modbus slave ID

            # Actuator specs
            "stroke_mm": 900.0,         # LEL25LT-900 stroke
            "center_mm": 450.0,         # Center position
            "soft_limit_mm": 5.0,       # Safety margin

            # Motion profile
            "default_speed": 500,       # mm/s
            "default_accel": 3000,      # mm/s²
            "default_decel": 3000,      # mm/s²

            # Command rate (anti-oscillation)
            "command_rate_hz": 30.0     # Max 30Hz to prevent oscillation
        },

        "moog": {
            # Future sprint - 6-DOF platform
            "ip": "192.168.1.100",
            "port": 6000,
            "send_rate_hz": 60.0
        }
    }
}


def load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Load configuration from file or return defaults.

    Args:
        config_path: Path to config file. If None, looks in config/settings.yaml

    Returns:
        Configuration dictionary with defaults merged in
    """
    if config_path is None:
        # Look for config file relative to project root
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

        if YAML_AVAILABLE:
            config_path = os.path.join(project_root, "config", "settings.yaml")
        else:
            config_path = os.path.join(project_root, "config", "settings.json")

    config = DEFAULT_CONFIG.copy()

    if os.path.exists(config_path):
        logger.info(f"Loading config from {config_path}")
        try:
            with open(config_path, 'r') as f:
                if YAML_AVAILABLE and config_path.endswith('.yaml'):
                    file_config = yaml.safe_load(f)
                else:
                    file_config = json.load(f)

            # Deep merge file config into defaults
            if file_config:
                config = _deep_merge(config, file_config)

        except Exception as e:
            logger.warning(f"Failed to load config: {e}. Using defaults.")
    else:
        logger.info("No config file found. Using defaults.")

    return config


def _deep_merge(base: Dict, override: Dict) -> Dict:
    """
    Deep merge override dict into base dict.

    Args:
        base: Base dictionary (defaults)
        override: Override dictionary (from file)

    Returns:
        Merged dictionary
    """
    result = base.copy()

    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value

    return result


def save_config(config: Dict[str, Any], config_path: Optional[str] = None):
    """
    Save configuration to file.

    Args:
        config: Configuration dictionary
        config_path: Path to save to
    """
    if config_path is None:
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        if YAML_AVAILABLE:
            config_path = os.path.join(project_root, "config", "settings.yaml")
        else:
            config_path = os.path.join(project_root, "config", "settings.json")

    os.makedirs(os.path.dirname(config_path), exist_ok=True)

    with open(config_path, 'w') as f:
        if YAML_AVAILABLE and config_path.endswith('.yaml'):
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)
        else:
            json.dump(config, f, indent=2)

    logger.info(f"Config saved to {config_path}")


def get_smc_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Extract SMC-specific configuration."""
    return config.get('hardware', {}).get('smc', DEFAULT_CONFIG['hardware']['smc'])


def get_motion_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Extract motion algorithm configuration."""
    return config.get('motion', DEFAULT_CONFIG['motion'])
