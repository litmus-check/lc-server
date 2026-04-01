"""
Playwright script generator utility for Element selectors.
This module generates Playwright scripts from selector arrays and updates selectors with script keys.
"""

from log_config.logger import logger
from utils.action_constants import ACTION_TO_PW_METHOD
from utils.utils_constants import STATE_TEMPLATE_REGEX
import re

def StateTemplateDetector(value: str) -> bool:
    return re.search(STATE_TEMPLATE_REGEX, value) is not None

def escape_js_string(value: str) -> str:
    """
    Escape a string value for use in JavaScript string literals (single-quoted strings).
    Escapes quotes, backslashes, control characters, and Unicode line/paragraph separators.
    """
    if value is None:
        return ''

    value_str = str(value)
    return (value_str
            .replace('\\', '\\\\')         # backslashes
            .replace("'", "\\'")           # single quotes
            .replace('\n', '\\n')          # newlines
            .replace('\r', '\\r')          # carriage returns
            .replace('\t', '\\t')          # tabs
            .replace('\b', '\\b')          # backspace
            .replace('\f', '\\f')          # form feed
            .replace('\u2028', '\\u2028')  # line separator
            .replace('\u2029', '\\u2029')  # paragraph separator
    )

def generate_playwright_scripts_for_selectors(selectors: list, action: str, value: str = None, verify_params: dict = None) -> list:
    """
    Generate Playwright scripts for an array of selectors and add script key to each selector.
    
    Args:
        selectors: List of selector objects with structure:
            {
                "display": "Get By XPath",
                "method": "page.locator", 
                "selector": "xpath=/html/body/div[1]/div[3]/div[1]/div[1]/form[1]/div[3]/input[1]"
            }
        action: The Playwright action to perform (click, fill, hover, verify, etc.)
        value: Optional value for actions like fill, selectOption, etc.
        verify_params: Optional verification parameters for verify actions
    
    Returns:
        List of updated selector objects with added 'script' key
    """
    try:
        updated_selectors = []
        
        for selector in selectors:
            # Create a copy of the selector object
            updated_selector = selector.copy()
            
            # Generate the script based on the selector method and action
            script = generate_script_for_selector(selector, action, value, verify_params)
            
            # Add the script to the selector object
            updated_selector['script'] = script
            
            updated_selectors.append(updated_selector)
            
        logger.info(f"Updated selectors: {updated_selectors}")
        logger.info(f"Generated {len(updated_selectors)} scripts for action '{action}'")
        return updated_selectors
        
    except Exception as e:
        logger.error(f"Error generating Playwright scripts: {str(e)}")
        raise e


def generate_script_for_selector(selector_obj: dict, action: str, value: str = None, verify_params: dict = None) -> str:
    """
    Generate a Playwright script for a single selector object.
    
    Args:
        selector_obj: Selector object with method, selector, and display
        action: The Playwright action to perform
        value: Optional value for the action
        verify_params: Optional verification parameters for verify actions
    
    Returns:
        Generated Playwright script string
    """
    try:
        method = selector_obj.get('method')
        selector_value = selector_obj.get('selector')

        if not method or not selector_value:
            logger.error(f"Method or selector value not found for selector {selector_obj}")
            return None
        
        # Handle verify actions specially
        if action == 'verify' and verify_params:
            return generate_verify_script(selector_obj, verify_params)
        
        # Map action to correct Playwright method based on LitmusAgent implementation
        playwright_action = map_action_to_playwright(action)
        
        # Handle special cases for different methods
        if method == 'page.getByRole':
            # Parse getByRole selector to extract role and name
            # Expected format: "'button', {name: 'Submit'}"
            import re
            role_match = re.match(r"^'([^']+)',\s*\{\s*name:\s*'([^']+)'\s*\}$", selector_value)
            if role_match:
                role = role_match.group(1)
                name = role_match.group(2)
                script = f"await {method}('{role}', {{name: '{name}'}}).{playwright_action}"
            else:
                # Fallback to treating as regular selector
                script = f"await {method}('{selector_value}').{playwright_action}"
        else:
            # For other methods, quote the selector value
            script = f"await {method}('{selector_value}').{playwright_action}"
        
        # Add value parameter if provided
        # Support state variables in value
        if value is not None:
            if StateTemplateDetector(value):
                script += f"(`{value}`)"
            else:
                escaped_value = escape_js_string(value)
                script += f"('{escaped_value}')"
        else:
            script += "()"
        
        # Add semicolon
        script += ";"
        
        return script
        
    except Exception as e:
        logger.error(f"Error generating script for selector {selector_obj}: {str(e)}")
        raise e


def generate_verify_script(selector_obj: dict, verify_params: dict) -> str:
    """
    Generate Playwright script for element verify actions only.
    
    Args:
        selector_obj: Selector object with method, selector, and display
        verify_params: Verification parameters including property, check, value, etc.
    
    Returns:
        Generated Playwright element verification script string
    """
    try:
        method = selector_obj.get('method')
        selector_value = selector_obj.get('selector')
        
        if not method or not selector_value:
            logger.error(f"Method or selector value not found for selector {selector_obj}")
            return None
        
        # Build the element selector
        element_selector = build_element_selector(method, selector_value)
        
        # Get verification parameters (element-only)
        property_type = verify_params.get('property')
        check = verify_params.get('check')
        value = verify_params.get('value')
        sub_property = verify_params.get('sub_property')
        expected_result = verify_params.get('expected_result', True)
        
        # Generate verification code for element verifications only
        verification_code = generate_element_verification_code(
            element_selector, property_type, check, value, sub_property
        )
        
        # Negate if expected_result is False
        if expected_result is False:
            verification_code = negate_verification(verification_code)
        
        return verification_code
        
    except Exception as e:
        logger.error(f"Error generating verify script: {str(e)}")
        raise e


def build_element_selector(method: str, selector_value: str) -> str:
    """
    Build element selector string from method and selector value.
    
    Args:
        method: The selector method (e.g., 'page.locator', 'page.getByRole')
        selector_value: The selector value
    
    Returns:
        Element selector string
    """
    if method == 'page.getByRole':
        # Parse getByRole selector to extract role and name
        import re
        role_match = re.match(r"^'([^']+)',\s*\{\s*name:\s*'([^']+)'\s*\}$", selector_value)
        if role_match:
            role = role_match.group(1)
            name = role_match.group(2)
            return f"{method}('{role}', {{name: '{name}'}})"
        else:
            return f"{method}('{selector_value}')"
    else:
        return f"{method}('{selector_value}')"




def generate_element_verification_code(element_selector: str, property_type: str, check: str, value: str, sub_property: str = None) -> str:
    """
    Generate Playwright code for element verifications only.
    
    Args:
        element_selector: The element selector string
        property_type: The element property to verify
        check: The check type
        value: The expected value
        sub_property: Sub-property for attribute/CSS verifications
    
    Returns:
        Generated Playwright verification code
    """
    if property_type == 'verify_text':
        return generate_text_verification_code(element_selector, check, value)
    elif property_type == 'verify_class':
        return generate_class_verification_code(element_selector, check, value)
    elif property_type == 'verify_attribute':
        return generate_attribute_verification_code(element_selector, check, value, sub_property)
    elif property_type == 'verify_count':
        return generate_count_verification_code(element_selector, check, value)
    elif property_type == 'verify_value':
        return generate_value_verification_code(element_selector, check, value)
    elif property_type == 'verify_css':
        return generate_css_verification_code(element_selector, check, value, sub_property)
    elif property_type == 'verify_if_visible':
        return f"await expect({element_selector}).toBeVisible();"
    elif property_type == 'verify_if_checked':
        return f"await expect({element_selector}).toBeChecked();"
    elif property_type == 'verify_if_empty':
        return f"await expect({element_selector}).toBeEmpty();"
    elif property_type == 'verify_if_in_viewport':
        return f"await expect({element_selector}).toBeInViewport();"
    
    raise ValueError(f"Unsupported element property: {property_type}")


def generate_text_verification_code(element_selector: str, check: str, value: str) -> str:
    """Generate text verification code."""
    if check == 'contains':
        return f"await expect({element_selector}).toHaveText(/{escape_regex(value)}/);"
    elif check == 'is':
        escaped_value = escape_js_string(value)
        return f"await expect({element_selector}).toHaveText('{escaped_value}');"
    raise ValueError(f"Unsupported text check: {check}")


def generate_class_verification_code(element_selector: str, check: str, value: str) -> str:
    """Generate class verification code."""
    if check == 'contains':
        return f"await expect({element_selector}).toHaveClass(/{escape_regex(value)}/);"
    elif check == 'is':
        escaped_value = escape_js_string(value)
        return f"await expect({element_selector}).toHaveClass('{escaped_value}');"
    raise ValueError(f"Unsupported class check: {check}")


def generate_attribute_verification_code(element_selector: str, check: str, value: str, sub_property: str) -> str:
    """Generate attribute verification code."""
    if not sub_property:
        raise ValueError("Sub-property is required for attribute verifications")
    
    escaped_sub_property = escape_js_string(sub_property)
    if check == 'contains':
        return f"await expect({element_selector}).toHaveAttribute('{escaped_sub_property}', /{escape_regex(value)}/);"
    elif check == 'is':
        escaped_value = escape_js_string(value)
        return f"await expect({element_selector}).toHaveAttribute('{escaped_sub_property}', '{escaped_value}');"
    raise ValueError(f"Unsupported attribute check: {check}")


def generate_count_verification_code(element_selector: str, check: str, value: str) -> str:
    """Generate count verification code."""
    if check == 'is':
        return f"await expect({element_selector}).toHaveCount({value});"
    elif check == 'greater_than':
        return f"const count = await {element_selector}.count(); await expect(count).toBeGreaterThan({value});"
    elif check == 'less_than':
        return f"const count = await {element_selector}.count(); await expect(count).toBeLessThan({value});"
    elif check == 'greater_than_or_equal':
        return f"const count = await {element_selector}.count(); await expect(count).toBeGreaterThanOrEqual({value});"
    elif check == 'less_than_or_equal':
        return f"const count = await {element_selector}.count(); await expect(count).toBeLessThanOrEqual({value});"
    raise ValueError(f"Unsupported count check: {check}")


def generate_value_verification_code(element_selector: str, check: str, value: str) -> str:
    """Generate value verification code."""
    if check == 'contains':
        return f"await expect({element_selector}).toHaveValue(/{escape_regex(value)}/);"
    elif check == 'is':
        escaped_value = escape_js_string(value)
        return f"await expect({element_selector}).toHaveValue('{escaped_value}');"
    raise ValueError(f"Unsupported value check: {check}")


def generate_css_verification_code(element_selector: str, check: str, value: str, sub_property: str) -> str:
    """Generate CSS verification code."""
    if not sub_property:
        raise ValueError("Sub-property is required for CSS verifications")
    
    escaped_sub_property = escape_js_string(sub_property)
    if check == 'contains':
        return f"await expect({element_selector}).toHaveCSS('{escaped_sub_property}', /{escape_regex(value)}/);"
    elif check == 'is':
        escaped_value = escape_js_string(value)
        return f"await expect({element_selector}).toHaveCSS('{escaped_sub_property}', '{escaped_value}');"
    raise ValueError(f"Unsupported CSS check: {check}")


def escape_regex(value: str) -> str:
    """
    Escape special regex characters in a string.
    
    Args:
        value: The string to escape
    
    Returns:
        Escaped string
    """
    import re
    return re.escape(value)


def negate_verification(verification_code: str) -> str:
    """
    Negate a verification by converting positive assertions to negative ones.
    Focuses on element-level verifications only.
    
    Args:
        verification_code: The original verification code
    
    Returns:
        Negated verification code
    """
    return verification_code\
        .replace('.toBeVisible()', '.not.toBeVisible()')\
        .replace('.toBeChecked()', '.not.toBeChecked()')\
        .replace('.toBeEmpty()', '.not.toBeEmpty()')\
        .replace('.toBeInViewport()', '.not.toBeInViewport()')\
        .replace('.toHaveText(', '.not.toHaveText(')\
        .replace('.toHaveClass(', '.not.toHaveClass(')\
        .replace('.toHaveAttribute(', '.not.toHaveAttribute(')\
        .replace('.toHaveValue(', '.not.toHaveValue(')\
        .replace('.toHaveCSS(', '.not.toHaveCSS(')\
        .replace('.toHaveCount(', '.not.toHaveCount(')\
        .replace('.toBeGreaterThan(', '.not.toBeGreaterThan(')\
        .replace('.toBeLessThan(', '.not.toBeLessThan(')\
        .replace('.toBeGreaterThanOrEqual(', '.not.toBeGreaterThanOrEqual(')\
        .replace('.toBeLessThanOrEqual(', '.not.toBeLessThanOrEqual(')


def generate_verify_scripts_for_selectors(selectors: list, verify_params: dict) -> list:
    """
    Generate Playwright element verification scripts for an array of selectors.
    
    Args:
        selectors: List of selector objects
        verify_params: Verification parameters including property, check, value, etc.
    
    Returns:
        List of updated selector objects with element verification scripts
    """
    return generate_playwright_scripts_for_selectors(selectors, 'verify', None, verify_params)


def map_action_to_playwright(action: str) -> str:
    """
    Map action to correct Playwright method based on LitmusAgent implementation.
    
    Args:
        action: The action to map
    
    Returns:
        Correct Playwright action method
    """
    return ACTION_TO_PW_METHOD.get(action, action)
