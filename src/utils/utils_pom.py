import traceback
from log_config.logger import logger
from models.Element import Element
from utils.utils_playwright_generator import generate_playwright_scripts_for_selectors

def update_instruction_with_element_data(current_user: dict, instruction: dict, element: Element) -> tuple[dict, int]:
    """
    Update a single instruction with the element data.
    
    Args:
        current_user: The current user
        instruction: The instruction -> format: {"args": [{"key": "element_id", "value": "element_id"}], "prompt": "prompt"}
        element: The element object
    Returns:
        The updated instruction and status code
    """
    try:
        logger.info(f"Updating instruction with element data")

        # Serialize the element object
        element_obj = element.serialize()
        instruction_args = instruction.get("args", [])
        element_id = element_obj.get("element_id")

        # Check if the element has selectors
        selectors = element_obj.get("selectors", [])

        # If the element has no selectors, use the element prompt
        if not selectors or len(selectors) == 0:
            logger.info(f"Element {element_id} has no selectors. Using element prompt.")
            instruction["prompt"] = element_obj.get("element_prompt")
            return instruction, 200

        # Get the action type from the instruction
        action_type = instruction.get("action")
        action_value = None
        verify_params = None
        
        # Handle verify actions specially
        if action_type == "verify":
            # Extract verify parameters from args
            verify_params = {}
            for arg in instruction_args:
                key = arg.get("key")
                value = arg.get("value")
                if key in ["property", "check", "value", "sub_property", "expected_result", "fail_test"]:
                    verify_params[key] = value
            
            # Only process element verifications (not page verifications)
            target = None
            for arg in instruction_args:
                if arg.get("key") == "target":
                    target = arg.get("value")
                    break
            
            if target != "element":
                logger.info(f"Skipping non-element verification for element {element_id}")
                instruction["prompt"] = element_obj.get("element_prompt")
                return instruction, 200
        else:
            # Get value from args if present for non-verify actions
            for arg in instruction_args:
                if arg.get("key") == "value":
                    action_value = arg.get("value")
                    break

        updated_selectors = generate_playwright_scripts_for_selectors(
            selectors, 
            action_type, 
            action_value,
            verify_params
        )
        # Update the instruction with the generated scripts
        instruction["selectors"] = updated_selectors
        logger.info(f"Generated {len(updated_selectors)} scripts for element {element_id}")

        logger.info(f"Updated selectors for element {element_id}: {updated_selectors}")

        logger.info(f"Updated instruction with selectors: {instruction}")
        # Add the playwright actions to the instruction
        if updated_selectors:
            instruction["playwright_actions"] = [updated_selectors[0].get("script")]

        logger.info(f"Updated instruction with playwright actions: {instruction}")
        logger.info(f"Added playwright actions for element {element_id}")

        return instruction, 200

    except Exception as e:
        logger.error(f"Error updating instruction with element data: {str(e)}")
        logger.debug(traceback.format_exc())
        return {"error": str(e)}, 500

def check_if_element_id_is_present_in_instruction(instruction: dict) -> str | None:
    """
    Check if element_id is present in the instruction at root level
    """
    if instruction.get("element_id"):
        return instruction.get("element_id")
    return None