"""
Configuration Utilities

Loads and manages configuration from config/settings.yaml
"""

import os
import logging
from typing import Any, Dict

# Try to import yaml, fall back to json if not available
try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False
    import json

logger = logging.getLogger(__name__)

# Default configuration
DEFAULT_CONFIG = {
    "telemetry": {
        "port": 20777,
        "buffer_size": 2048
    },
    "motion": {
        "surge_scale": 0.05,
        "sway_scale": 0.05,
        "heave_scale": 0.03,
        "roll_scale": 0.3,
        "pitch_scale": 0.3,
        "yaw_scale": 0.1,
        "max_translation": 0.1,
        "max_rotation": 0.26,
        "smoothing_factor": 0.3,
        "home_z": -0.18
    },
    "hardware": {
        "smc": {
            "port": "/dev/ttyUSB0",
            "baudrate": 38400,
            "controller_id": 1,
            "stroke_mm": 100.0
        },
        "moog": {
            "ip": "192.168.1.100",
            "port": 6000,
            "send_rate_hz": 60.0
        }
    }
}


def load_config(config_path: str = None) -> Dict[str, Any]:
    """
    Load configuration from file or return defaults.
    
    Args:
        config_path: Path to config file. If None, looks in config/settings.yaml
        
    Returns:
        Configuration dictionary
    """
    if config_path is None:
        # Look for config file relative to project root
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        
        if YAML_AVAILABLE:
            config_path = os.path.join(project_root, "config", "settings.yaml")
        else:
            config_path = os.path.join(project_root, "config", "settings.json")
    
    if os.path.exists(config_path):
        logger.info(f"Loading config from {config_path}")
        try:
            with open(config_path, 'r') as f:
                if YAML_AVAILABLE and config_path.endswith('.yaml'):
                    return yaml.safe_load(f)
                else:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load config: {e}. Using defaults.")
            return DEFAULT_CONFIG
    else:
        logger.info("No config file found. Using defaults.")
        return DEFAULT_CONFIG


def save_config(config: Dict[str, Any], config_path: str = None):
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
            yaml.dump(config, f, default_flow_style=False)
        else:
            json.dump(config, f, indent=2)
    
    logger.info(f"Config saved to {config_path}")
