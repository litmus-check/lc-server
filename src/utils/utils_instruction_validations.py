from log_config.logger import logger
import traceback
import json
import re
from utils.action_constants import *
from service.service_test_segment import *
from utils.utils_test import validate_playwright_instructions_helper
from utils.utils_constants import VARIABLE_REGEX_PATTERN, ENV_VARIABLE_REGEX_PATTERN, STATE_TEMPLATE_REGEX

def has_variables(value: any) -> bool:
    """
    Check if a value contains variables in the format ${variable_name}.
    Args:
        value: The value to check.
    Returns:
        bool: True if the value contains variables, False otherwise.
    """
    if not isinstance(value, str):
        return False
    
    # Use constant regex pattern to match ${variable_name}
    return bool(re.search(VARIABLE_REGEX_PATTERN, value) or re.search(ENV_VARIABLE_REGEX_PATTERN, value) or re.search(STATE_TEMPLATE_REGEX, value))

def validate_instructions(current_user: dict, instructions: list[dict]) -> tuple[bool, str]:
    """
    Validate the instructions to ensure they are not empty and contain valid commands.
    Args:
        instructions (list): The instructions to validate.
    Returns:
        bool: True if the instructions are valid, False otherwise.
        str: Error message if validation fails.
    """
    logger.info(f"Vaildating instructions {instructions}")
    try:
        for ind, instruction in enumerate(instructions):
            if not isinstance(instruction, dict):
                # try to convert the instruction to a dictionary
                try:
                    instruction = json.loads(instruction)
                except:
                    logger.error(f"Instruction {instruction} is not a dictionary")
                    return False, f"Instruction {ind+1} is not JSON object"
            if instruction.get("type") not in SUPPORTED_ACTION_TYPES:
                logger.error(f"Instruction {instruction} has unsupported action type")
                return False, f"Instruction {ind+1} has unsupported action type : '{instruction.get('type')}'"
            if instruction.get("type") == AI_ACTION:
                is_valid, error_message = validate_ai_action(instruction, ind)
                if not is_valid:
                    return False, error_message
            elif instruction.get("type") == NON_AI_ACTION:
                is_valid, error_message = validate_non_ai_action(instruction, ind)
                if not is_valid:
                    return False, error_message
            elif instruction.get("type") == TEST_SEGMENT:
                is_valid, error_message = validate_test_segment(current_user, instruction)
                if not is_valid:
                    return False, error_message
        return True, None
    except Exception as e:
        logger.error("Unable to validate instructions, " + str(e))
        logger.debug(traceback.format_exc())
        return False, f"Unable to validate instructions, {str(e)}"
    
def validate_ai_action(instruction: dict, ind: int) -> tuple[bool, str]:
    """
    Validate the AI action in the instruction.
    Args:
        instruction (dict): The instruction to validate.
        ind (int): The index of the instruction in the list.
    Returns:
        bool: True if the AI action is valid, False otherwise.
        str: Error message if validation fails.
    """
    try:
        # Check if action is present and supported
        action = instruction.get("action")
        if not action:
            logger.error(f"Instruction {instruction} is missing action")
            return False, f"Instruction {ind+1} is missing action"
            
        if action not in SUPPORTED_AI_ACTIONS:
            logger.error(f"Instruction {instruction} has unsupported AI action")
            return False, f"Instruction {ind+1} has unsupported AI action : '{action}'"
        
        # Get required args for this action
        required_args = AI_ACTION_REQUIRED_ARGS.get(action, {})
        received_args = instruction.get("args", [])
        received_args_dict = {arg.get("key"): arg.get("value") for arg in received_args}
        
        # Validate required arguments
        for arg_name, arg_spec in required_args.items():
            if arg_spec.get("required", False):
                if arg_name not in received_args_dict:
                    logger.error(f"Instruction {instruction} is missing required argument {arg_name}")
                    return False, f"Instruction {ind+1} is missing required argument '{arg_name}' for action '{action}'"
                
                # Validate argument type
                arg_value = received_args_dict[arg_name]
                expected_type = arg_spec.get("type")
                
                # Skip type validation if the argument contains variables
                # if has_variables(arg_value):
                #     logger.info(f"Instruction {ind+1} argument '{arg_name}' contains variables, skipping type validation")
                #     continue
                
                if expected_type == "string":
                    is_valid, error_msg = validate_string(arg_value)
                    if not is_valid:
                        logger.error(f"Instruction {instruction} has invalid argument '{arg_name}'")
                        return False, f"Instruction {ind+1} has invalid argument '{arg_name}' for action '{action}' - {error_msg}"
                    if arg_name == "url":
                        is_valid, error_msg = validate_url(arg_value)
                        if not is_valid:
                            logger.error(f"Instruction {instruction} has invalid URL for argument '{arg_name}'")
                            return False, f"Instruction {ind+1} has invalid URL for argument '{arg_name}' for action '{action}' - {error_msg}"
                
        return True, None
    except Exception as e:
        logger.error("Unable to validate instructions, " + str(e))
        logger.debug(traceback.format_exc())
        raise e
    
def validate_url(url: str) -> tuple[bool, str]:
    """
    Validate if the given string is a valid URL.
    Args:
        url (str): The URL to validate.
    Returns:
        bool: True if the URL is valid, False otherwise.
        str: Error message if validation fails.
    """
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        return False, "URL must start with http:// or https://"
    return True, None

def add_protocol_if_not_present(url: str) -> str:
    """
    Add https:// if it is not present in the URL.
    """
    url = url.strip()
    if not url.startswith(("http://", "https://")):   #TODO: Bypass regex strings
        return f"https://{url}"
    return url

def validate_number(value: any) -> tuple[bool, str]:
    """
    Validate if the given value is a valid number.
    Args:
        value: The value to validate.
    Returns:
        bool: True if the value is a valid number, False otherwise.
        str: Error message if validation fails.
    """
    if not isinstance(value, (int, str)):
        return False, "Value must be a number or string"
    if isinstance(value, str) and has_variables(value):
        return True, None
    if isinstance(value, str) and not value.isdigit():
        return False, "String value must contain only digits"
    return True, None

def validate_string(value: any) -> tuple[bool, str]:
    """
    Validate if the given value is a valid string.
    Args:
        value: The value to validate.
    Returns:
        bool: True if the value is a valid string, False otherwise.
        str: Error message if validation fails.
    """
    if not isinstance(value, str):
        return False, "Value must be a string"
    return True, None

def validate_state_variable_name(value: any) -> tuple[bool, str]:
    """
    Validate state variable name. It must start with a letter and can only
    contain letters, numbers, and underscores.
    """
    if not isinstance(value, str):
        return False, "Variable name must be a string"
    variable_name_pattern = r"^[a-zA-Z][a-zA-Z0-9_]*$"
    if not re.match(variable_name_pattern, value):
        return False, "Variable name must start with a letter and can only contain letters, numbers, and underscores"
    return True, None

def validate_scroll_direction(value: any) -> tuple[bool, str]:
    """
    Validate if the given value is a valid scroll direction.
    Args:
        value: The value to validate.
    Returns:
        bool: True if the value is a valid scroll direction, False otherwise.
        str: Error message if validation fails.
    """
    valid_directions = ['up', 'down', 'left', 'right']
    if not isinstance(value, str):
        return False, "Direction must be a string"
    if value not in valid_directions:
        return False, f"Direction must be one of: {', '.join(valid_directions)}"
    return True, None

def validate_http_method(value: any) -> tuple[bool, str]:
    """
    Validate if the given value is a valid HTTP method.
    Args:
        value: The value to validate.
    Returns:
        bool: True if the value is a valid HTTP method, False otherwise.
        str: Error message if validation fails.
    """
    valid_methods = ['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS']
    if not isinstance(value, str):
        return False, "Method must be a string"
    if value.upper() not in valid_methods:
        return False, f"Method must be one of: {', '.join(valid_methods)}"
    return True, None

def validate_api_intercept_action(value: any) -> tuple[bool, str]:
    """
    Validate if the given value is a valid API intercept action.
    Args:
        value: The value to validate.
    Returns:
        bool: True if the value is a valid API intercept action, False otherwise.
        str: Error message if validation fails.
    """
    from utils.action_constants import API_INTERCEPT_ACTIONS
    if not isinstance(value, str):
        return False, "Action must be a string"
    if value not in API_INTERCEPT_ACTIONS:
        return False, f"Action must be one of: {', '.join(API_INTERCEPT_ACTIONS)}"
    return True, None

def validate_non_ai_action(instruction: dict, ind: int) -> tuple[bool, str]:
    """
    Validate the Non-AI action in the instruction.
    Args:
        instruction (dict): The instruction to validate.
        ind (int): The index of the instruction in the list.
    Returns:
        bool: True if the Non-AI action is valid, False otherwise.
        str: Error message if validation fails.
    """
    try:
        # Check if action is present and supported
        action = instruction.get("action")
        if not action:
            logger.error(f"Instruction {instruction} is missing action")
            return False, f"Instruction {ind+1} is missing action"
            
        if action not in SUPPORTED_NON_AI_ACTIONS:
            logger.error(f"Instruction {instruction} has unsupported Non-AI action")
            return False, f"Instruction {ind+1} has unsupported Non-AI action : '{action}'"
        
        # Get required args for this action
        required_args = NON_AI_ACTION_REQUIRED_ARGS.get(action, {})
        received_args = instruction.get("args", [])
        received_args_dict = {arg.get("key"): arg.get("value") for arg in received_args}
        
        # Validate required arguments
        for arg_name, arg_spec in required_args.items():
            if arg_spec.get("required", False):
                if arg_name not in received_args_dict:
                    logger.error(f"Instruction {instruction} is missing required argument '{arg_name}'")
                    return False, f"Instruction {ind+1} is missing required argument '{arg_name}' for action '{action}'"
                
                # Validate argument type
                arg_value = received_args_dict[arg_name]
                expected_type = arg_spec.get("type")
                
                # Skip type validation if the argument contains variables
                # if has_variables(arg_value):
                #     logger.info(f"Instruction {ind+1} argument '{arg_name}' contains variables, skipping type validation")
                #     continue
                
                if expected_type == "string":
                    is_valid, error_msg = validate_string(arg_value)
                    if not is_valid:
                        logger.error(f"Instruction {instruction} has invalid argument '{arg_name}'")
                        return False, f"Instruction {ind+1} has invalid argument '{arg_name}' for action '{action}' - {error_msg}"
                    # Additional URL validation for url arguments
                    # Skip URL validation for api_intercept, remove_api_handlers, and api_mock as they support glob patterns
                    if arg_name == "url" and action not in [API_INTERCEPT, REMOVE_API_HANDLERS, API_MOCK]:
                        is_valid = True
                        url_index = next((i for i, arg in enumerate(received_args) if arg.get("key") == "url"), None)
                        # Add prefix if it is not present. Check if any of the other args has key tabSelectionMethod and value is regex
                        if any(arg.get("key") == "tabSelectionMethod" and arg.get("value") != "regex" for arg in received_args):
                            arg_value = add_protocol_if_not_present(arg_value)  # Only if it is not a regex string
                            instruction["args"][url_index]["value"] = arg_value  # Instead of 0th index, we need to find the index of the url argument
                            is_valid, error_msg = validate_url(arg_value)
                        if not is_valid:
                            logger.error(f"Instruction {instruction} has invalid URL")
                            return False, f"Instruction {ind+1} has invalid URL for action '{action}' - {error_msg}"
                            
                elif expected_type == "number":
                    is_valid, error_msg = validate_number(arg_value)
                    if not is_valid:
                        logger.error(f"Instruction {instruction} has invalid argument '{arg_name}'")
                        return False, f"Instruction {ind+1} has invalid argument '{arg_name}' for action '{action}' - {error_msg}"
                
                # Additional validation for scroll direction
                if action == SCROLL and arg_name == "direction":
                    is_valid, error_msg = validate_scroll_direction(arg_value)
                    if not is_valid:
                        logger.error(f"Instruction {instruction} has invalid scroll direction")
                        return False, f"Instruction {ind+1} has invalid scroll direction for action '{action}' - {error_msg}"
                
                # Validate playwright script if action is run_script
                if action == RUN_SCRIPT and arg_name == "script":
                    # Replace ${variable_name} patterns with empty strings for validation
                    processed_script = re.sub(VARIABLE_REGEX_PATTERN, '""', arg_value)
                    # Replace {{env.variable_name}} patterns with empty strings for validation
                    processed_script = re.sub(ENV_VARIABLE_REGEX_PATTERN, '""', processed_script)
                    logger.info(f"Processed script: {processed_script}")
                    is_valid, _ = validate_playwright_instructions_helper(processed_script)
                    if not is_valid:
                        logger.error(f"Instruction {instruction} has invalid playwright script")
                        return False, f"Instruction {ind+1} has invalid playwright script for action '{action}'"
                
                # Validate HTTP method for api_intercept and api_mock
                if action in [API_INTERCEPT, API_MOCK] and arg_name == "method":
                    is_valid, error_msg = validate_http_method(arg_value)
                    if not is_valid:
                        logger.error(f"Instruction {instruction} has invalid HTTP method")
                        return False, f"Instruction {ind+1} has invalid HTTP method for action '{action}' - {error_msg}"
                
                # Validate status code for api_mock
                if action == API_MOCK and arg_name == "status_code":
                    try:
                        status_code = int(arg_value)
                        if status_code < 100 or status_code > 599:
                            logger.error(f"Instruction {instruction} has invalid status code")
                            return False, f"Instruction {ind+1} has invalid status_code for action '{action}' - must be between 100 and 599"
                    except (ValueError, TypeError):
                        logger.error(f"Instruction {instruction} has invalid status code")
                        return False, f"Instruction {ind+1} has invalid status_code for action '{action}' - must be a number"
                
                # Validate response_header for api_mock (should be valid JSON)
                if action == API_MOCK and arg_name == "response_header":
                    try:
                        import json
                        json.loads(arg_value)
                    except (json.JSONDecodeError, TypeError):
                        logger.error(f"Instruction {instruction} has invalid response_header")
                        return False, f"Instruction {ind+1} has invalid response_header for action '{action}' - must be valid JSON string"
                
                # Validate response_body for api_mock (should be valid JSON or string)
                if action == API_MOCK and arg_name == "response_body":
                    # response_body can be any string, but if it's JSON, validate it
                    try:
                        import json
                        json.loads(arg_value)
                    except (json.JSONDecodeError, TypeError):
                        # If it's not JSON, that's fine - it can be a plain string
                        pass
                
                # Validate API intercept action type
                if action == API_INTERCEPT and arg_name == "action":
                    is_valid, error_msg = validate_api_intercept_action(arg_value)
                    if not is_valid:
                        logger.error(f"Instruction {instruction} has invalid API intercept action")
                        return False, f"Instruction {ind+1} has invalid API intercept action for action '{action}' - {error_msg}"
                
                # Validate js_code for api_intercept (same as run_script validation)
                if action == API_INTERCEPT and arg_name == "js_code":
                    # Replace ${variable_name} patterns with empty strings for validation
                    processed_script = re.sub(VARIABLE_REGEX_PATTERN, '""', arg_value)
                    # Replace {{env.variable_name}} patterns with empty strings for validation
                    processed_script = re.sub(ENV_VARIABLE_REGEX_PATTERN, '""', processed_script)
                    logger.info(f"Processed js_code: {processed_script}")
                    is_valid, _ = validate_playwright_instructions_helper(processed_script)
                    if not is_valid:
                        logger.error(f"Instruction {instruction} has invalid js_code")
                        return False, f"Instruction {ind+1} has invalid js_code for action '{action}'"
                
                # Validate variable_name for api_intercept (same as set_state_variable validation)
                if action == API_INTERCEPT and arg_name == "variable_name":
                    is_valid, error_msg = validate_state_variable_name(arg_value)
                    if not is_valid:
                        logger.error(f"Instruction {instruction} has invalid variable_name")
                        return False, f"Instruction {ind+1} has invalid variable_name for action '{action}' - {error_msg}"
                
        # Additional validation for api_intercept: variable_name is required for all actions except abort_request
        if action == API_INTERCEPT:
            from utils.action_constants import API_INTERCEPT_ACTION_ABORT_REQUEST
            intercept_action = received_args_dict.get("action")
            variable_name = received_args_dict.get("variable_name")
            if intercept_action != API_INTERCEPT_ACTION_ABORT_REQUEST and not variable_name:
                logger.error(f"Instruction {instruction} is missing required variable_name for api_intercept action when action is not abort_request")
                return False, f"Instruction {ind+1} is missing required variable_name for api_intercept action when action is not abort_request"
        
        # Additional validation for verify action
        if action == VERIFY:
            is_valid, error_message = validate_manual_verification(instruction, ind)
            if not is_valid:
                return False, error_message
        
        # Additional validation for set_state_variable action
        if action == SET_STATE_VARIABLE:
            if not received_args:
                return False, f"Instruction {ind+1} must include at least one state variable to set"
            
            # Find the variable_name argument
            variable_name_arg = None
            for arg in received_args:
                if isinstance(arg, dict) and arg.get("key") == "variable_name":
                    variable_name_arg = arg
                    break
            
            if not variable_name_arg:
                return False, f"Instruction {ind+1} is missing required 'variable_name' argument for set_state_variable action"
            
            variable_name = variable_name_arg.get("value")
            if not isinstance(variable_name, str):
                return False, f"Instruction {ind+1} has invalid variable_name value '{variable_name}'. Must be a string"
            
            # Validate the variable name
            is_valid, error_msg = validate_state_variable_name(variable_name)
            if not is_valid:
                return False, f"Instruction {ind+1} has invalid state variable name '{variable_name}' - {error_msg}"
            logger.info(f"State variable name '{variable_name}' is valid")
                
        return True, None
    except Exception as e:
        logger.error("Unable to validate instructions, " + str(e))
        logger.debug(traceback.format_exc())
        raise e

def validate_test_segment(current_user: dict, instruction: dict) -> tuple[bool, str]:
    """
    Validate the test segment instruction.
    Args:
        current_user: dict
        instruction: dict
    Returns:
        bool: True if the test segment instruction is valid, False otherwise.
        str: Error message if validation fails.
    """
    try:
        test_obj, status_code = validate_test_segment_existence_only(current_user, instruction)
        if status_code != 200:
            return False, test_obj.get("message")
        return True, None
    except Exception as e:
        logger.error("Unable to validate test segment, " + str(e))
        logger.debug(traceback.format_exc())
        raise e

def validate_manual_verification(instruction: dict, ind: int) -> tuple[bool, str]:
    """
    Validate manual verification instruction.
    Args:
        instruction (dict): The instruction to validate.
        ind (int): The index of the instruction in the list.
    Returns:
        bool: True if the manual verification is valid, False otherwise.
        str: Error message if validation fails.
    """
    try:
        received_args = instruction.get("args", [])
        received_args_dict = {arg.get("key"): arg.get("value") for arg in received_args}
        
        # Validate target
        target = received_args_dict.get("target")
        if target not in [VERIFICATION_TARGET_ELEMENT, VERIFICATION_TARGET_PAGE]:
            return False, f"Instruction {ind+1} has invalid target '{target}'. Must be '{VERIFICATION_TARGET_ELEMENT}' or '{VERIFICATION_TARGET_PAGE}'"
        
        # Validate locator_type
        locator_type = received_args_dict.get("locator_type")
        if locator_type not in [VERIFICATION_LOCATOR_TYPE_MANUAL, VERIFICATION_LOCATOR_TYPE_AI] and target != VERIFICATION_TARGET_PAGE:
            return False, f"Instruction {ind+1} has invalid locator_type '{locator_type}'. Must be '{VERIFICATION_LOCATOR_TYPE_MANUAL}' or '{VERIFICATION_LOCATOR_TYPE_AI}'"
        
        # Validate locator_prompt and locator based on locator_type
        locator_prompt = received_args_dict.get("prompt")
        locator = received_args_dict.get("locator")
        element_id = instruction.get("element_id")
        logger.info(f"Element ID: {element_id} and prompt: {locator_prompt}")
        
        if locator_type == VERIFICATION_LOCATOR_TYPE_MANUAL and target != VERIFICATION_TARGET_PAGE:
            if not locator:
                return False, f"Instruction {ind+1} is missing required locator for manual verification"
        elif locator_type == VERIFICATION_LOCATOR_TYPE_AI and target != VERIFICATION_TARGET_PAGE:
            if not locator_prompt and not element_id:
                return False, f"Instruction {ind+1} is missing required prompt or element_id for AI verification"
        
        # Validate property based on target
        property_value = received_args_dict.get("property")
        allowed_properties = VERIFICATION_PROPERTY_ALLOWED_VALUES.get(target, [])
        if property_value not in allowed_properties:
            property_names = [prop.replace('verify_', '') for prop in allowed_properties]
            return False, f"Instruction {ind+1} has invalid property '{property_value}' for {target} target. Must be one of: {', '.join(property_names)}"
        
        # Validate check based on property
        check = received_args_dict.get("check")
        valid_checks = VERIFICATION_PROPERTY_CHECKS.get(property_value, [])
        if property_value not in VERIFICATION_BOOLEAN_PROPERTIES and check not in valid_checks:
            return False, f"Instruction {ind+1} has invalid check '{check}' for property '{property_value}'. Must be one of: {', '.join(valid_checks)}"
        
        # Validate sub_property for specific properties
        sub_property = received_args_dict.get("sub_property")
        if property_value in VERIFICATION_PROPERTIES_REQUIRING_SUB_PROPERTY:
            if not sub_property:
                return False, f"Instruction {ind+1} is missing required sub_property for property '{property_value}'"
        else:
            if sub_property is not None:
                return False, f"Instruction {ind+1} has sub_property '{sub_property}' but property '{property_value}' does not support sub_property"
        
        # Validate value
        value = received_args_dict.get("value")
        if property_value not in VERIFICATION_BOOLEAN_PROPERTIES and not value:
            return False, f"Instruction {ind+1} is missing required value"
        
        # Validate fail_test
        fail_test = received_args_dict.get("fail_test")
        if not isinstance(fail_test, bool):
            return False, f"Instruction {ind+1} has invalid fail_test '{fail_test}'. Must be a boolean"
        
        # Validate expected_result
        expected_result = received_args_dict.get("expected_result")
        if not isinstance(expected_result, bool):
            return False, f"Instruction {ind+1} has invalid expected_result '{expected_result}'. Must be a boolean"
        
        return True, None
    except Exception as e:
        logger.error("Unable to validate manual verification, " + str(e))
        logger.debug(traceback.format_exc())
        return False, f"Unable to validate manual verification: {str(e)}"

