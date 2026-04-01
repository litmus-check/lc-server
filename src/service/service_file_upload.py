import traceback
from log_config.logger import logger
from models.File import File
from utils.action_constants import AI_FILE_UPLOAD


def replace_file_upload_instruction(current_user: dict, instruction: dict) -> tuple[dict, int]:
    """
    Add fil_url to the instrcution arg if the action is ai_file_upload
    Args:
        current_user: dict
        instruction: dict
    Returns:
        tuple[dict, int]: tuple containing the updated instruction and status code
    """
    try:
        # If the instruction is ai_file_upload, add the file url to the instruction
        if instruction.get("action") == AI_FILE_UPLOAD:
            args = instruction.get("args", [])

            file_id = None
            for each_arg in args:
                if each_arg.get("key") == "file_id":
                    file_id = each_arg.get("value")
                    break

            file_obj, status_code = get_file_implementation(current_user, file_id)
            if status_code != 200:
                return file_obj, status_code
            
            # Get the file url
            file_url = file_obj.get("file_url")

            # Add new argument to the instruction
            args.append(
                {
                    "key": "file_url",
                    "value": file_url
                }
            )

        return instruction, 200
    except Exception as e:
        logger.error(f"Error in replace_file_upload_instruction: {e}")
        logger.error(traceback.format_exc())
        raise e

def get_file_implementation(current_user, file_id) -> tuple[dict, int]:
    """
    Get a file by ID
    Args:
        current_user: Dictionary containing user information including role and org_id
        file_id: UUID of the file
    Returns:
        Tuple of (response_dict, status_code)
    """
    try:
        
        # Check if file exists and user has access
        file = File.query.filter_by(file_id=file_id).first()
        if not file:
            return {"error": "File not found"}, 404

        # Check if user has access to the suite
        from service.service_suite import return_suite_obj
        suite = return_suite_obj(current_user, file.suite_id)
        if not suite:
            return {"error": "Suite not found or user does not have access to it"}, 404
        
        return file.serialize(), 200
    except Exception as e:
        logger.error(f"Error in get_file_implementation: {str(e)}")
        logger.debug(traceback.print_exc())
        return {"error": str(e)}, 400