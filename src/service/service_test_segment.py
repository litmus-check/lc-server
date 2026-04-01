import json
import uuid
import traceback
from database import db
from models.Test import Test
from log_config.logger import logger
from sqlalchemy.orm import joinedload
from access_control.roles import ADMIN
from models.TestSegment import TestSegment
from service.service_suite import return_suite_obj
from service.service_file_upload import get_file_implementation
from utils.utils_pom import update_instruction_with_element_data, check_if_element_id_is_present_in_instruction
from service.service_element import return_element_obj
from utils.action_constants import TEST_SEGMENT, RUN_SCRIPT, AI_FILE_UPLOAD
from utils.utils_test import validate_if_playwright_instructions_exist, validate_playwright_instructions_against_instructions


def create_test_segment_implementation(current_user: dict, data: dict) -> tuple[dict, int]:
    """
    Create a test segment
    Args:
        current_user: dict
        data: dict
    Returns:
        tuple[dict, int]: The test segment and status code
    """
    try:
        test_id = data.get('test_id')
        segment_name = data.get('segment_name')
        start_instruction_id = data.get('start_instruction_id')
        end_instruction_id = data.get('end_instruction_id')

        if not test_id or not start_instruction_id or not end_instruction_id:
            return {"error": "Required fields are missing. Fields required: test_id, start_instruction_id, end_instruction_id"}, 400

        # Check if segment_name is not None
        if not segment_name or segment_name == "":
            return {"error": "Segment name is required"}, 400

        # Validate test exists and get its suite_id
        from service.service_test import return_test_obj
        test = return_test_obj(current_user, test_id)
        if not test:
            return {"error": "Test not found or user does not have access to it"}, 404

        # Prevent duplicate segment names within the same suite
        existing = TestSegment.query.filter_by(suite_id=test.suite_id, segment_name=segment_name).first()
        if existing:
            return {"error": f"A segment with name '{segment_name}' already exists in this suite"}, 409

        # Validate instruction IDs exist in test and are in correct order
        validation_result, status_code = validate_instruction_ids(test, start_instruction_id, end_instruction_id)
        if status_code != 200:
            return validation_result, status_code

        segment = TestSegment(
            segment_id=str(uuid.uuid4()),
            segment_name=segment_name,
            test_id=test_id,
            suite_id=test.suite_id,
            start_instruction_id=str(start_instruction_id),
            end_instruction_id=str(end_instruction_id)
        )
        db.session.add(segment)
        db.session.commit()
        return segment.serialize(), 201
    except Exception as e:
        logger.error(f"Error creating test segment: {str(e)}")
        db.session.rollback()
        return {"error": "Internal server error"}, 500


def get_test_segment_by_id_implementation(current_user: dict, segment_id: str) -> tuple[dict, int]:
    """
    Get a test segment by id
    Args:
        current_user: dict
        segment_id: str
    Returns:
        tuple[dict, int]: The test segment and status code
    """
    try:
        segment = return_test_segment_obj(current_user, segment_id)
        if not segment:
            return {"error": "Test segment not found or user does not have access to it"}, 404
        
        return segment.serialize(), 200
    except Exception as e:
        logger.error(f"Error fetching test segment: {str(e)}")
        return {"error": "Internal server error"}, 500


def get_test_segments_by_suite_implementation(current_user: dict, suite_id: str) -> tuple[dict, int]:
    """
    Get test segments by suite
    Args:
        current_user: dict
        suite_id: str
    Returns:
        tuple[dict, int]: The test segments and status code
    """
    try:
        # First validate user has access to the suite
        suite = return_suite_obj(current_user, suite_id)
        if not suite:
            return {"error": "Suite not found or user does not have access to it"}, 404
        
        # Then get segments for the suite
        segments = TestSegment.query.filter_by(suite_id=suite_id).order_by(TestSegment.created_at.desc()).all()
        return {
            "test_segments": [s.serialize() for s in segments]
        }, 200
    except Exception as e:
        logger.error(f"Error fetching test segments by suite: {str(e)}")
        return {"error": "Internal server error"}, 500


def update_test_segment_implementation(current_user: dict, segment_id: str, data: dict) -> tuple[dict, int]:
    """
    Update a test segment
    Args:
        current_user: dict
        segment_id: str
        data: dict
    Returns:
        tuple[dict, int]: The test segment and status code
    """
    try:
        segment = return_test_segment_obj(current_user, segment_id)
        if not segment:
            return {"error": "Test segment not found or user does not have access to it"}, 404

        start_instruction_id = data.get('start_instruction_id')
        end_instruction_id = data.get('end_instruction_id')
        segment_name = data.get('segment_name', None)
        test_id = data.get('test_id', None)

        if segment_name is not None and segment_name != segment.segment_name:
            # Prevent duplicate segment names within the same suite
            existing = TestSegment.query.filter_by(suite_id=segment.suite_id, segment_name=segment_name).first()
            if existing:
                return {"error": f"A segment with name '{segment_name}' already exists in this suite"}, 409

            segment.segment_name = segment_name

        if test_id is not None and test_id != segment.test_id:
            # Get the test object
            from service.service_test import return_test_obj
            test = return_test_obj(current_user, test_id)
            if not test:
                return {"error": "Test not found or user does not have access to it"}, 404
            segment.test_id = test_id
            segment.test = test

        if start_instruction_id is not None:
            segment.start_instruction_id = str(start_instruction_id)
        if end_instruction_id is not None:
            segment.end_instruction_id = str(end_instruction_id)

        # Validate instruction IDs exist in test and are in correct order
        validation_result, status_code = validate_instruction_ids(segment.test, start_instruction_id, end_instruction_id)
        if status_code != 200:
            return validation_result, status_code

        segment.modified_at = db.func.now()

        db.session.commit()
        return segment.serialize(), 200
    except Exception as e:
        logger.error(f"Error updating test segment: {str(e)}")
        db.session.rollback()
        return {"error": "Internal server error"}, 500


def delete_test_segment_implementation(current_user: dict, segment_id: str) -> tuple[dict, int]:
    """
    Delete a test segment
    Args:
        current_user: dict
        segment_id: str
    Returns:
        tuple[dict, int]: The test segment and status code
    """
    try:
        segment = return_test_segment_obj(current_user, segment_id)
        if not segment:
            return {"error": "Test segment not found or user does not have access to it"}, 404
        db.session.delete(segment)
        db.session.commit()
        return {"message": "Test segment deleted successfully"}, 200
    except Exception as e:
        logger.error(f"Error deleting test segment: {str(e)}")
        db.session.rollback()
        return {"error": "Internal server error"}, 500


def return_test_segment_instruction(current_user: dict, test_obj: dict, instruction_id: str) -> tuple[dict, str]:
    """
    Return the test segment instruction. Return the run_script instruction with the test segment instructions, playwright instructions
    Args:
        test_obj: dict
        instruction_id: str
    Returns:
        dict: The test segment instruction as run_script instruction
    """
    try:
        # Get the instructions from the test
        instructions = test_obj.get("instructions")

        # Get the playwright instructions from the test
        playwright_instructions = test_obj.get("playwright_instructions")

        # Create the playwright script
        playwright_script = create_playwright_script_string(playwright_instructions, instructions)

        # Build run_script instruction dict
        run_script_instruction = {
            "id": instruction_id,
            "type": "Non-AI",
            "action": RUN_SCRIPT,
            "args": [
                {
                    "key": "description",
                    "value": f"Test Segment: {test_obj.get('name')}"
                },
                {
                    "key": "script",
                    "value": playwright_script
                }
            ]
        }

        # If instruction is a file upload instruction, then add the file url to the args
        logger.info(f"Printing Instructions: {instructions}")
        for instruction in instructions:
            if instruction.get("action") == AI_FILE_UPLOAD:
                args = instruction.get("args", [])
                for arg in args:
                    if arg.get("key") == "file_id":
                        file_id = arg.get("value")
                        break
                    
                file_obj, status_code = get_file_implementation(current_user, file_id)
                if status_code != 200:
                    return file_obj, status_code
                
                # Get the file url
                file_url = file_obj.get("file_url")

                # Add new argument to the run_script instruction
                run_script_instruction["args"].append(
                        {
                            "key": "file_url",
                            "value": file_url
                        }
                    )

        logger.info(f"Printing Run Script Instruction: {run_script_instruction}")

        # RUn script playwright instruction
        run_script_playwright_instruction = playwright_script

        return run_script_instruction, run_script_playwright_instruction
    except Exception as e:
        logger.error(f"Error in return_test_segment_instruction: {e}")
        logger.error(traceback.format_exc())
        raise e

def create_playwright_script_string(playwright_instructions: dict, instructions: list) -> str:
    """
    Create a playwright script string from the playwright actions
    Args:
        playwright_instructions: dict
        instructions: list
    Returns:
        str: The playwright script string
    """
    try:
        # Create run_script type non ai instruction from the test
        playwright_script = ""
        for instruction in instructions:
            playwright_actions = playwright_instructions.get(instruction.get("id")) if playwright_instructions.get(instruction.get("id")) else []

            for each_action in playwright_actions:
                playwright_script += each_action + "\n"

        return playwright_script
    except Exception as e:
        logger.error(f"Error in create_playwright_script_string: {e}")
        logger.error(traceback.format_exc())
        raise e

def replace_test_segment_instruction(current_user: dict, instructions: list, playwright_instructions: dict, suite_id: str=None) -> tuple[dict, int]:
    """
    Replace the test segment instruction with its child instructions (expanded).
    Similar to compose flow, segments are expanded into individual instructions with IDs like parent_id_1, parent_id_2, ..., parent_id_0
    Args:
        current_user: dict
        instructions: list
        playwright_instructions: dict
        suite_id: str
    Returns:
        tuple[dict, int]: The updated instructions and playwright instructions
    """
    try:
        # We need to iterate backwards or build a new list to handle insertions
        new_instructions = []
        new_playwright_instructions = {}
        
        for instruction in instructions:
            if instruction.get('type') == TEST_SEGMENT:
                # log instruction before updating
                logger.info(f"Instruction is a test segment, expanding into child instructions: {instruction}")
                
                # Use the same function as compose flow to get expanded instructions
                segment_instructions, status_code = validate_test_segment_existence_and_replace_with_test_segment_instruction(current_user, instruction)
                if status_code != 200:
                    # segment_instructions holds the error message
                    if isinstance(segment_instructions, list) and len(segment_instructions) > 0 and "error" in segment_instructions[0]:
                        return segment_instructions[0], status_code
                    return {"error": "Failed to validate test segment"}, status_code
                
                logger.info(f"Got {len(segment_instructions)} instructions from test segment")
                
                # Add all expanded instructions to the new list
                for segment_instr in segment_instructions:
                    new_instructions.append(segment_instr)
                    # Add playwright actions for each expanded instruction
                    segment_instr_id = str(segment_instr.get("id"))
                    if segment_instr.get("playwright_actions"):
                        new_playwright_instructions[segment_instr_id] = segment_instr.get("playwright_actions")
                    else:
                        # If no playwright_actions, set empty list
                        new_playwright_instructions[segment_instr_id] = []
            else:
                # Regular instruction - check if there is element_id in the instruction args
                element_id = check_if_element_id_is_present_in_instruction(instruction)
                if element_id:
                    element = return_element_obj(current_user, element_id, suite_id)
                    if not element:
                        return {"error": "Element not found"}, 400

                    # Update the instruction with the element data
                    instruction, status_code = update_instruction_with_element_data(current_user, instruction, element)
                    if status_code != 200:
                        return {"error": instruction}, status_code

                    # Replace playwright instructions with the updated instruction
                    new_playwright_instructions[instruction.get("id")] = instruction.get("playwright_actions")
                else:
                    new_playwright_instructions[instruction.get("id")] = playwright_instructions.get(instruction.get("id"))
                
                new_instructions.append(instruction)

        # Update instructions list
        instructions = new_instructions

        # Check if playwright instructions are present in the test and are valid
        if new_playwright_instructions is None or len(new_playwright_instructions) == 0 or not validate_if_playwright_instructions_exist(new_playwright_instructions, instructions):
            return {"error": "Playwright instructions are empty or one of the instruction is missing playwright instructions in the test segment"}, 400

        # Validate the playwright instructions against the instructions
        if not validate_playwright_instructions_against_instructions(new_playwright_instructions, instructions):
            return {"error": "Playwright instructions are not valid"}, 400

    except Exception as e:
        logger.error(f"Error in replace_test_segment_instruction: {e}")
        logger.error(traceback.format_exc())
        raise e
    
    return {"instructions": instructions, "playwright_instructions": new_playwright_instructions}, 200

def _flatten_test_segment_instructions(current_user: dict, test_obj: dict, suite_id: str) -> tuple[list, int]:
    """
    Helper function to flatten test segment instructions recursively without assigning IDs.
    Returns a list of instruction dictionaries with their original IDs preserved for playwright lookup.
    """
    temp_instructions = []  # List of (instruction_dict, original_id, playwright_source)
    
    for each_instruction in test_obj.get("instructions", []):
        if each_instruction.get("type") == TEST_SEGMENT:
            # Recursively process nested segment
            nested_test_obj, status_code = validate_test_segment_existence_helper(current_user, each_instruction)
            if status_code != 200:
                return nested_test_obj, status_code
            
            # Recursively flatten nested segment
            nested_instructions, status_code = _flatten_test_segment_instructions(
                current_user, nested_test_obj, nested_test_obj.get("suite_id")
            )
            if status_code != 200:
                return nested_instructions, status_code
            
            # Add nested instructions to temp list
            for nested_instr, nested_orig_id, nested_source in nested_instructions:
                temp_instructions.append((nested_instr, nested_orig_id, nested_source))
        else:
            # Regular instruction - check if there is element_id in the instruction args
            element_id = check_if_element_id_is_present_in_instruction(each_instruction)
            if element_id:
                element = return_element_obj(current_user, element_id, suite_id)
                if not element:
                    return [{"error": "Element not found"}], 400

                # Update the instruction with the element data
                updated_instruction, status_code = update_instruction_with_element_data(current_user, each_instruction, element)
                if status_code != 200:
                    return [{"error": updated_instruction}], status_code
                each_instruction = updated_instruction

            # Store original ID for playwright lookup
            original_id = str(each_instruction.get("id"))
            temp_instructions.append((each_instruction, original_id, test_obj))
    
    return temp_instructions, 200


def validate_test_segment_existence_and_replace_with_test_segment_instruction(current_user: dict, instruction: dict, root_segment_id: str = None) -> tuple[list, int]:
    """
    Validate the test segment existence and replace the test segment instruction with its child instructions.
    This will also replace nested test segments recursively, using root segment ID for all leaf instructions.
    Args:
        current_user: dict
        instruction: dict
        root_segment_id: str - The root segment ID to use for all leaf instruction IDs (for nested segments)
    Returns:
        tuple[list, int]: List of instructions (with updated IDs) and status code
    """
    try:
        # Get the root segment ID - use the current instruction ID if not provided (first level)
        if root_segment_id is None:
            root_segment_id = str(instruction.get("id"))
        
        # Call the helper function to validate the test segment existence
        test_obj, status_code = validate_test_segment_existence_helper(current_user, instruction)
        if status_code != 200:
            return test_obj, status_code

        # Extract suite_id from the instruction
        suite_id = test_obj.get("suite_id")

        # log test_obj before updating
        logger.info(f"Test object before updating: {test_obj}")

        # Flatten all instructions (including nested segments) without assigning IDs yet
        temp_instructions, status_code = _flatten_test_segment_instructions(current_user, test_obj, suite_id)
        if status_code != 200:
            return temp_instructions, status_code

        # Now assign IDs to all flattened instructions using root segment ID
        # Last instruction gets _0, others get _1, _2, _3, etc.
        flattened_instructions = []
        flattened_playwright_instructions = {}
        total_count = len(temp_instructions)
        
        for idx, (each_instruction, original_id, playwright_source) in enumerate(temp_instructions):
            # Create new instruction with updated ID
            new_instruction = each_instruction.copy()
            
            # Last instruction gets _0, others get _1, _2, etc.
            if idx == total_count - 1:
                new_instruction["id"] = f"{root_segment_id}_0"
            else:
                new_instruction["id"] = f"{root_segment_id}_{idx + 1}"
            
            # Get playwright actions for this instruction
            from utils.action_constants import AI_ASSERT
            if each_instruction.get("playwright_actions"):
                # Already has playwright_actions (from element resolution)
                playwright_actions = each_instruction.get("playwright_actions")
                new_instruction["playwright_actions"] = playwright_actions
                flattened_playwright_instructions[new_instruction["id"]] = playwright_actions
            elif each_instruction.get('action') == AI_ASSERT or each_instruction.get('ai_use') == 'always_ai':
                # For ai_assert or always_ai, set empty playwright_actions
                new_instruction["playwright_actions"] = []
                flattened_playwright_instructions[new_instruction["id"]] = []
            else:
                # Get from test_obj's playwright_instructions
                playwright_actions = playwright_source["playwright_instructions"][original_id]
                new_instruction["playwright_actions"] = playwright_actions
                flattened_playwright_instructions[new_instruction["id"]] = playwright_actions
            
            flattened_instructions.append(new_instruction)

        # log flattened instructions after updating
        logger.info(f"Flattened instructions after updating: {flattened_instructions}")

        # Validate that all instructions have playwright actions (skip ai_assert and always_ai)
        from utils.action_constants import AI_ASSERT
        for instr in flattened_instructions:
            instr_id = str(instr.get("id"))
            # Skip validation for ai_assert or always_ai instructions
            if instr.get('ai_use') == 'always_ai' or instr.get('action') == AI_ASSERT:
                continue
            if instr_id not in flattened_playwright_instructions and not instr.get("playwright_actions"):
                return [{"error": f"Playwright instructions are missing for instruction {instr_id} in the test segment"}], 400

        # Validate the playwright instructions against the instructions
        if not validate_playwright_instructions_against_instructions(flattened_playwright_instructions, flattened_instructions):
            return [{"error": "Playwright instructions are not valid"}], 400

        return flattened_instructions, 200
    except Exception as e:
        logger.error(f"Error in validate_test_segment_existence_and_replace_with_test_segment_instruction: {e}")
        logger.error(traceback.format_exc())
        raise e
                
        

def validate_test_segment_existence_only(current_user: dict, instruction: dict) -> tuple[dict, int]:
    """
    Validate the test segment existence only
    Args:
        current_user: dict
        instruction: dict
    Returns:
        tuple[dict, int]: The test object and status code
    """
    try:
        # Call the helper function to validate the test segment existence
        test_obj, status_code = validate_test_segment_existence_helper(current_user, instruction)
        if status_code != 200:
            return test_obj, status_code

        # Now recursively check if the nested test segments are valid
        for instruction in test_obj.get("instructions"):
            if instruction.get("type") == TEST_SEGMENT:
                test_segment_obj, status_code = validate_test_segment_existence_only(current_user, instruction)
                if status_code != 200:
                    return test_segment_obj, status_code

        return test_obj, 200
    except Exception as e:
        logger.error(f"Error in validate_test_segment_existence_only: {e}")
        logger.error(traceback.format_exc())
        raise e

def validate_test_segment_existence_helper(current_user: dict, instruction: dict) -> tuple[dict, int]:
    """
    Validate the test segment existence helper.
    If segment_id is present, then validate the test segment existence and return instructions that are part of the segment.
    Args:
        current_user: dict
        instruction: dict
    Returns:
        tuple[dict, int]: The test object and status code
    """
    try:
        # Check if the test_id is present in instruction.args
        source_test_id = None
        segment_id = None
        for arg in instruction.get("args", []):
            if arg.get("key") == "source_test_id":
                source_test_id = arg.get("value")
                break
        if source_test_id is None:
            return {"error": "Test id is required for test segment"}, 400

        # Check if the test segment is valid and user has access to it
        from service.service_test import return_test_obj
        test_obj = return_test_obj(current_user, source_test_id)
        if not test_obj:
            return {"error": "Test not found or user does not have access to it"}, 404

        # Also read optional segment_id from args (new format)
        for arg in instruction.get("args", []):
            if arg.get("key") == "segment_id":
                segment_id = arg.get("value")
                break

        # Serialize the test object
        test_obj = test_obj.serialize()

        # json load the playwright instructions
        test_obj["playwright_instructions"] = json.loads(test_obj.get("playwright_instructions"))

        # If segment_id is provided, trim instructions and playwright actions to that segment window
        if segment_id:
            # Fetch segment with auth check
            segment_obj = return_test_segment_obj(current_user, segment_id)
            if not segment_obj:
                return {"message": "Test segment not found or user does not have access to it"}, 404
            # Ensure the segment belongs to the same source test
            if str(segment_obj.test_id) != str(source_test_id):
                return {"message": "Segment does not belong to the provided source test"}, 400

            # Validate instruction ids are present in the segment
            validation_result, status_code = validate_instruction_ids(segment_obj.test, segment_obj.start_instruction_id, segment_obj.end_instruction_id)
            if status_code != 200:
                return {"message": "Instruction ids are not present in the segment"}, status_code

            # Trim instructions/playwright instructions by start/end ids
            test_obj = slice_test_by_instruction_range(
                test_obj,
                str(segment_obj.start_instruction_id),
                str(segment_obj.end_instruction_id)
            )

        return test_obj, 200
    except Exception as e:
        logger.error(f"Error in validate_test_segment_existence_helper: {e}")
        logger.error(traceback.format_exc())
        raise e


def slice_test_by_instruction_range(test_obj: dict, start_instruction_id: str, end_instruction_id: str) -> dict:
    """
    Return a shallow-copied test_obj with instructions and playwright_instructions
    sliced to the inclusive [start, end] instruction_id window.
    Args:
        test_obj: dict
        start_instruction_id: str
        end_instruction_id: str
    Returns:
        dict: The sliced test_obj
    """
    try:
        instructions = test_obj.get("instructions", [])
        playwright_instructions = test_obj.get("playwright_instructions", {})

        instruction_ids = [str(inst.get("id", "")) for inst in instructions]

        start_index = instruction_ids.index(start_instruction_id)
        end_index = instruction_ids.index(end_instruction_id)

        sliced_instructions = instructions[start_index:end_index + 1]
        sliced_ids = {str(inst.get("id")) for inst in sliced_instructions}

        sliced_playwright = {k: v for k, v in playwright_instructions.items() if str(k) in sliced_ids}

        # Build new object to avoid mutating caller's reference unexpectedly
        new_test_obj = dict(test_obj)
        new_test_obj["instructions"] = sliced_instructions
        new_test_obj["playwright_instructions"] = sliced_playwright
        return new_test_obj
    except Exception as e:
        logger.error(f"Error in slice_test_by_instruction_range: {e}")
        logger.error(traceback.format_exc())
        raise e
    
def return_test_segment_obj(current_user: dict, segment_id: str) -> TestSegment | None:
    """
    Return the test segment object
    Args:
        current_user: dict
        segment_id: str
    Returns:
        TestSegment | None: The test segment object
    """
    try:
        result = TestSegment.query.filter_by(segment_id=segment_id).options(joinedload(TestSegment.suite), joinedload(TestSegment.test)).first()
        
        # Check permissions
        if not result or (current_user['role'] != ADMIN and result.suite.org_id != current_user['org_id']):
            return None
            
        return result
    except Exception as e:
        logger.error("Unable to return role based test segment, " + str(e))
        logger.debug(traceback.format_exc())
        return None


def validate_instruction_ids(test: Test, start_instruction_id: str, end_instruction_id: str) -> tuple[dict, int]:
    """
    Validate that instruction IDs exist in test and start comes before end. Validating in instruction list only because
    playwright instructions also have the same ids as the instruction list.
    Args:
        test: Test object
        start_instruction_id: str
        end_instruction_id: str
    Returns:
        dict or None: Error response if validation fails, None if valid
    """
    try:
        # Get test instructions
        instructions = test.serialize().get('instructions', [])
        
        # Find instruction IDs in the list
        instruction_ids = [str(inst.get('id', '')) for inst in instructions]
        
        # Check if start_instruction_id exists
        if str(start_instruction_id) not in instruction_ids:
            return {"error": f"start_instruction_id '{start_instruction_id}' not found in test instructions"}, 400
        
        # Check if end_instruction_id exists
        if str(end_instruction_id) not in instruction_ids:
            return {"error": f"end_instruction_id '{end_instruction_id}' not found in test instructions"}, 400
        
        # Check if start comes before end
        start_index = instruction_ids.index(str(start_instruction_id))
        end_index = instruction_ids.index(str(end_instruction_id))
        
        if start_index > end_index:
            return {"error": "start_instruction_id must come before end_instruction_id in the test instructions"}, 400
        
        return None, 200
    except Exception as e:
        logger.error(f"Error validating instruction IDs: {str(e)}")
        return {"error": "Error validating instruction IDs"}, 500

def check_if_the_test_has_segment(instructions: []) -> tuple[bool, int]:
    """
    Check if the test has a segment
    Args:
        instructions: list
    Returns:
        tuple[bool, int]: True if the test has a segment, False otherwise
    """
    try:
        for instruction in instructions:
            if instruction.get("type") == TEST_SEGMENT:
                return True, 200
        return False, 200
        
    except Exception as e:
        logger.error(f"Error checking if the test has a segment: {str(e)}")
        return False, 500