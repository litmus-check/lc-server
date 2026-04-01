from models.Suite import Suite
from utils.encryption import decrypt_string
from log_config.logger import logger
import traceback
import csv

def get_suite_data(suite: Suite):
    """
    Get the data for a given suite.
    Args:
        suite: Suite object
    Returns:
        dict: Suite data containing sign_in_url, username and password
    """
    try:
        if not suite:
            return None
        suite_data = {
            'data': {
                'sign_in_url': suite.sign_in_url
            },
            'sensitive_data': {
                'username': decrypt_string(suite.username) if suite.username != '' else "",
                'password': decrypt_string(suite.password) if suite.password != '' else ""
            }
        }
        logger.info(f"Suite data: {suite_data.get('data').keys()}, {suite_data.get('sensitive_data').keys()}")
        return suite_data
    except Exception as e:
        logger.error(f"Error in get_suite_data: {str(e)}")
        logger.debug(traceback.format_exc())
        return None

def validate_csv_headers_for_typescript(file_path: str) -> tuple[dict, int]:
    """
    Validate CSV headers to ensure they are valid TypeScript variable names.
    Args:
        file_path: Path to the CSV file
    Returns:
        Tuple of (response_dict, status_code). If validation passes, returns (None, 200).
        If validation fails, returns (error_dict, 400).
    """
    try:
        with open(file_path, 'r', encoding='utf-8-sig') as csv_file:
            reader = csv.reader(csv_file)
            headers = next(reader, None)
            
            if not headers:
                return {"error": "CSV file is empty or has no headers"}, 400
            
            # Validate each header as a TypeScript variable name
            invalid_headers = []
            from utils.utils_instruction_validations import validate_state_variable_name
            for header in headers:
                # Strip whitespace from header
                header = header.strip()
                if not header:
                    invalid_headers.append("(empty header)")
                    continue
                
                is_valid, error_msg = validate_state_variable_name(header)
                if not is_valid:
                    invalid_headers.append(f"'{header}'")
            
            if invalid_headers:
                headers_str = ", ".join(invalid_headers)
                return {
                    "error": f"Invalid CSV headers. Headers must be valid TypeScript variable names (start with a letter and contain only letters, numbers, and underscores). Invalid headers: {headers_str}"
                }, 400
            
            logger.info(f"CSV headers validated successfully: {headers}")
            return None, 200
    except Exception as e:
        logger.error(f"Error reading CSV file for header validation: {str(e)}")
        return {"error": f"Error reading CSV file: {str(e)}"}, 400