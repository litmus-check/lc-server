import json
from typing import Dict, Any, Tuple, Optional
from utils.utils_constants import *
from log_config.logger import logger
import traceback
from models.Suite import Suite
from models.Schedule import Schedule

def validate_playwright_config(config: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """
    Validate Playwright browser configuration against the schema.
    
    Args:
        config: The configuration dictionary to validate
        
    Returns:
        Tuple of (is_valid: bool, error_message: Optional[str])
    """
    try:
        # Check if config is a dictionary
        if not isinstance(config, dict):
            return False, "Configuration must be a JSON object"
        
        # Validate browser
        browser = config.get('browser')
        if not browser:
            return False, "Browser is required"
        if browser not in ALLOWED_BROWSERS:
            return False, f"Invalid browser '{browser}'. Allowed browsers: {', '.join(ALLOWED_BROWSERS)}"
        
        # Validate device
        device = config.get('device')
        if not device:
            return False, "Device configuration is required"
        if not isinstance(device, dict):
            return False, "Device must be a JSON object"
        
        device_type = device.get('type')
        if not device_type:
            return False, "Device type is required"
        if device_type not in ALLOWED_DEVICE_TYPES:
            return False, f"Invalid device type '{device_type}'. Allowed types: {', '.join(ALLOWED_DEVICE_TYPES)}"
        
        # Validate device_config
        device_config = device.get('device_config')
        if not device_config:
            return False, "Device configuration is required"
        if not isinstance(device_config, dict):
            return False, "Device configuration must be a JSON object"
        
        os = device_config.get('os')
        if not os:
            return False, "Operating system is required"
        
        # Validate OS based on device type
        if device_type == "desktop":
            if os not in ALLOWED_DESKTOP_OS:
                return False, f"Invalid OS '{os}' for desktop device. Allowed OS: {', '.join(ALLOWED_DESKTOP_OS)}"
        elif device_type == "mobile":
            if os not in ALLOWED_MOBILE_OS:
                return False, f"Invalid OS '{os}' for mobile device. Allowed OS: {', '.join(ALLOWED_MOBILE_OS)}"
        
        # Validate viewport
        viewport = config.get('viewport')
        if not viewport:
            return False, "Viewport configuration is required"
        if not isinstance(viewport, dict):
            return False, "Viewport must be a JSON object"
        
        width = viewport.get('width')
        height = viewport.get('height')
        
        if width is None or height is None:
            return False, "Viewport width and height are required"
        
        if not isinstance(width, int) or not isinstance(height, int):
            return False, "Viewport width and height must be integers"
        
        # Validate viewport combination against predefined configurations
        viewport_key = f"{width}x{height}"
        if viewport_key not in VIEWPORT_CONFIGS[device_type]:
            allowed_viewports = list(VIEWPORT_CONFIGS[device_type].keys())
            return False, f"Invalid viewport combination '{viewport_key}'. Allowed viewports: {', '.join(allowed_viewports)}"
        
        # Get device pixel ratio from viewport configuration
        viewport_config = VIEWPORT_CONFIGS[device_type][viewport_key]
        computed_dpr = viewport_config.get('dpr', DEFAULT_DEVICE_PIXEL_RATIO)
        
        # Set the computed device pixel ratio in the config
        config['device_pixel_ratio'] = computed_dpr
        
        return True, None
        
    except Exception as e:
        return False, f"Validation error: {str(e)}"

def get_config_from_request(request_data: Dict[str, Any] = None, suite: Suite = None, schedule: Schedule = None) -> Tuple[Dict[str, Any], int]:
    """
    Get the configuration for the given request data.
    If the request data is not provided, then use the suite config.
    If the suite config is not provided, then use the default config.
    Args:
        request_data: Request data from the user
        suite: Suite object
    Returns:
        Tuple of (configuration dictionary, status code)
    """
    try:
        logger.info(f"Getting config from request data: {request_data}")
        logger.info(f"Getting config from suite: {suite}")
        logger.info(f"Getting config from schedule: {schedule}")
        if request_data and 'config' in request_data:
            # Validate the config
            is_valid, error = validate_playwright_config(request_data['config'])
            if not is_valid:
                return {"error": f"Invalid Playwright configuration: {error}"}, 400
            return request_data['config'], 200
        elif suite:
            # Validation is not required because we are validating the config in the suite creation
            # If suite.config is None, then return the default config
            if suite.config is None:
                return DEFAULT_PLAYWRIGHT_CONFIG, 200
            else:
                return json.loads(suite.config), 200
        elif schedule:
            # Validation is not required because we are validating the config in the schedule creation
            # If schedule.config is None, then return the default config
            if schedule.config is None:
                return DEFAULT_PLAYWRIGHT_CONFIG, 200
            else:
                return json.loads(schedule.config), 200
        else:
            return DEFAULT_PLAYWRIGHT_CONFIG, 200
    except Exception as e:
        logger.error(f"Error in get_config_from_request: {str(e)}")
        logger.debug(traceback.print_exc())
        return {"error": f"Error in get_config_from_request: {str(e)}"}, 500

def format_config_string(config: Dict[str, Any]) -> str:
    """
    Format a Playwright config dictionary into a readable string.
    
    Args:
        config: The configuration dictionary
        
    Returns:
        str: Formatted config string in format "Browser | Device | Viewport"
    """
    try:
        if not config or not isinstance(config, dict):
            return None
            
        browser = config.get('browser')
        device_type = config.get('device', {}).get('type')
        viewport = config.get('viewport', {})
        width = viewport.get('width')
        height = viewport.get('height')
        
        if browser and device_type and width and height:
            return f"{browser} | {device_type} | {width}x{height}"
        else:
            return None
    except Exception:
        return None