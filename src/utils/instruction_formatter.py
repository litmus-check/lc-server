"""
Instruction formatter for displaying instructions in Slack messages.
Uses displayStructure format to create human-readable instruction descriptions.
"""

from utils.action_constants import *


def format_instruction_for_display(instruction: dict) -> str:
    """
    Format instruction object for Slack display using displayStructure.
    Matches the frontend formatting logic.
    
    Args:
        instruction: Instruction object containing action, args, prompt, etc.
        
    Returns:
        Formatted instruction string for Slack display
    """
    try:
        if not instruction:
            return "No instruction data available"
        
        action = instruction.get('action', 'unknown')
        args = instruction.get('args', [])
        prompt = instruction.get('prompt', '')
        
        # Create args dictionary for easy lookup
        args_dict = {}
        if args and isinstance(args, list):
            for arg in args:
                if isinstance(arg, dict) and 'key' in arg and 'value' in arg:
                    args_dict[arg['key']] = arg['value']
        
        # Special handling for reuse_test. Message format: Reuse test {test_name}
        if action == 'reuse_test':
            source_test_id = args_dict.get('source_test_id', '')
            test_name = args_dict.get('test_name', source_test_id)
            return f"Reuse test {test_name}"
        
        # Special handling for ai_file_upload
        if action == AI_FILE_UPLOAD:
            file_name = args_dict.get('file_name', 'file')
            return f"Upload file {file_name} in {prompt}"
        
        # Special handling for verify action
        if action == VERIFY:
            return format_verify_instruction_frontend_style(instruction, args_dict)
        
        # Special handling for switch_tab
        if action == SWITCH_TAB:
            url_value = args_dict.get('url', '')
            tab_selection_method = args_dict.get('tabSelectionMethod', 'dropdown')
            display_text = 'Switch to tab matching regex' if tab_selection_method == 'regex' else 'Switch to tab'
            return f"{display_text} {url_value}"
        
        # Special handling for run_script
        if action == RUN_SCRIPT:
            description = args_dict.get('description', '')
            return f"run_script: {description}"
        
        # Get display structure from constants
        display_structure = ACTION_DISPLAY_STRUCTURES.get(action, f"Execute {action}")
        
        # Replace [prompt] with prompt
        if prompt and '[prompt]' in display_structure:
            display_structure = display_structure.replace('[prompt]', prompt)

        # check if element_id is present. If present, then replace prompt with element name
        element_id = instruction.get('element_id', '')
        if element_id and '[prompt]' in display_structure:
            display_structure = display_structure.replace('[prompt]', element_id)
        
        # Replace other placeholders with values
        for key, value in args_dict.items():
            placeholder = f'[{key}]'
            if placeholder in display_structure:
                display_structure = display_structure.replace(placeholder, str(value) if value is not None else 'N/A')
        
        return display_structure
        
    except Exception as e:
        import traceback
        from log_config.logger import logger
        logger.error(f"Error formatting instruction for Slack: {str(e)}")
        logger.debug(traceback.format_exc())
        return f"Error formatting instruction: {action}"


def format_verify_instruction_frontend_style(instruction: dict, args_dict: dict) -> str:
    """
    Special formatting for verify action matching frontend style.
    """
    try:
        # Extract verify-specific values
        target = args_dict.get('target', '')
        property_name = args_dict.get('property', '')
        check_type = args_dict.get('check', '')
        value = args_dict.get('value', '')
        locator = args_dict.get('locator', '')
        prompt_value = args_dict.get('prompt', '')
        sub_property = args_dict.get('sub_property', '')
        sub_property_value = args_dict.get('value', '')
        expected_result = args_dict.get('expected_result')
        fail_test = args_dict.get('fail_test')
        
        # Get the main prompt from instruction or args
        prompt = instruction.get('prompt', '') or prompt_value or locator
        
        # Build the verify description
        verify_parts = []
        
        # Add target
        if target:
            target_display = get_target_display_text(target)
            verify_parts.append(f"Verify {target_display}")
        
        # Add prompt/locator
        if prompt:
            verify_parts.append(f": {prompt}")
        
        # Add property
        if property_name:
            property_display = get_property_display_text(property_name)
            verify_parts.append(f": {property_display}")
        
        # Add check
        if check_type:
            verify_parts.append(f" {check_type}")
        
        # Add sub property
        if sub_property:
            verify_parts.append(f" {sub_property}")
            if sub_property_value:
                verify_parts.append(f": {sub_property_value}")
        
        # Add value (for non-attribute/non-css properties)
        if value and property_name not in ['verify_attribute', 'verify_css']:
            verify_parts.append(f" {value}")
        
        # Add expected result indicators
        if expected_result is False:
            verify_parts.append(" (Expected to fail)")
        
        if fail_test is False:
            verify_parts.append(" (Continue on failure)")
        
        return "".join(verify_parts) if verify_parts else "Verify"
            
    except Exception as e:
        from log_config.logger import logger
        logger.error(f"Error formatting verify instruction: {str(e)}")
        return "Verify"


def get_target_display_text(target: str) -> str:
    """Get display text for target using constants."""
    return VERIFY_TARGET_DISPLAY_MAPPING.get(target, target)


def get_property_display_text(property_name: str) -> str:
    """Get display text for property using constants."""
    return VERIFY_PROPERTY_DISPLAY_MAPPING.get(property_name, property_name)
