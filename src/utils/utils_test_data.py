from log_config.logger import logger
import traceback
import re
import csv
import os
from models.Test import Test
from utils.util_blob import fetch_blob
from utils.utils_constants import VARIABLE_REGEX_PATTERN

def get_variables_from_instructions(playwright_instructions: dict=None, instruction: dict=None) -> list:
    """
    Get the variables from the playwright instructions and instruction args.
    playwright_instructions is a dictionary with the following structure:
    {"uuid":["instruction1", "instruction2", "instruction3"]}
    instruction is a dictionary with the following structure:
    {"id": "1", "type": "Non-AI", "args": [{"key": "value"}], "prompt": "prompt"}
    Args:
        playwright_instructions (dict): The playwright instructions.
        instruction (dict): The instruction.
    Returns:
        list: The variables.
    """
    try:
        variables = set()
        # Use constant regex pattern to match ${variable_name}
        
        # Get the variables from the playwright instructions
        if playwright_instructions:
            logger.info(f"Extracting variables from playwright instructions with {len(playwright_instructions)} instruction groups")
            for ins_id, ins_list in playwright_instructions.items():
                for play_wright_ins in ins_list:
                    matches = re.findall(VARIABLE_REGEX_PATTERN, play_wright_ins)
                    for match in matches:
                        variable_name = match
                        variables.add(variable_name)
        
        # Get the variables from the instruction args
        if instruction and 'args' in instruction:
            logger.info("Extracting variables from instruction args")
            args = instruction['args']
            if isinstance(args, list):
                for arg in args:
                    for key, value in arg.items():
                        if isinstance(value, str):
                            matches = re.findall(VARIABLE_REGEX_PATTERN, value)
                            for match in matches:
                                variable_name = match
                                variables.add(variable_name)
        
        variables_list = list(variables)
        logger.info(f"Found {len(variables_list)} unique variables: {variables_list}")
        return variables_list
    except Exception as e:
        logger.error("Unable to get variables from instructions, " + str(e))
        logger.debug(traceback.format_exc())
        raise e

def validate_column_names_and_variables(headers: list, req_variables: list) -> tuple[str, int]:
    """
    Validate the column names and variables. We check if every required variable is present in the headers.
    Args:
        headers (list): The headers.
        req_variables (list): The required variables.
    Returns:
        tuple:
            - str: The error message.
            - int: The status code.
    """
    try:
        logger.info(f"Validating {len(req_variables)} required variables against {len(headers)} CSV headers")
        logger.info(f"Required variables: {req_variables}")
        logger.info(f"CSV headers: {headers}")
        
        # Validate the column names and variables
        for each_variable in req_variables:
            if each_variable not in headers:
                logger.info(f"Variable '{each_variable}' not found in CSV headers")
                return f"Variable {each_variable} not found in the headers. Add columns for all variables to the file.", 400
        
        logger.info("All required variables found in CSV headers - validation successful")
        return "Column names and variables are valid", 200
    except Exception as e:
        logger.error("Unable to validate column names and variables, " + str(e))
        logger.debug(traceback.format_exc())
        raise e

def replace_variables_in_playwright_instructions(playwright_instructions: dict) -> str:
    """
    Replace the variables in the playwright instructions with the values from the file.
    Args:
        playwright_instructions (dict): The playwright instructions. Format: {"uuid":["instruction1", "instruction2", "instruction3"]}
    Returns:
        dict: The new playwright instructions.
    """
    try:
        global_variables = ""
        # Search for ${variable} and replace it with the variable
        matches = re.findall(VARIABLE_REGEX_PATTERN, playwright_instructions)
        for match in matches:
            variable = match
            global_variables += f"{variable} = \"\";\n"
            playwright_instructions = playwright_instructions.replace(match, f"${{{variable}}}")

        # Add global variables to the playwright instructions first instruction
        playwright_instructions[list(playwright_instructions.keys())[0]][0] = global_variables + playwright_instructions[list(playwright_instructions.keys())[0]][0]

        # Update the script with the global variables
        return playwright_instructions
    except Exception as e:
        logger.error("Unable to replace variables in script, " + str(e))
        logger.debug(traceback.format_exc())
        raise e

def load_test_data_variables_from_csv(test_id: str) -> tuple[dict, int]:
    """
    Load test data variables from CSV file.
    
    Args:
        test_id (str): The test ID to check and load data for
        
    Returns:
        tuple:
            - dict: Variables dictionary with header:value pairs
            - int: Status code (200 for success, 404/400 for errors)
    """
    try:
        logger.info(f"Loading test data variables from CSV for test_id: {test_id}")
        local_file_path = None
        # Check if the test_id is received
        if not test_id:
            logger.error("Test ID is required but not provided")
            return {"error": "Test ID is required"}, 400
            
        # Check if the test exists
        test_obj = Test.query.filter_by(id=test_id).first()
        if not test_obj:
            logger.error(f"Test with id {test_id} not found in database")
            return {"error": f"Test with id {test_id} not found"}, 404
            
        # Check if the test has_test_data is true
        if not test_obj.has_test_data:
            logger.error(f"Test {test_id} does not have test data enabled")
            return {"error": f"Test {test_id} does not have test data"}, 400

        file_obj = test_obj.file
        logger.info(f"Retrieved file object for test {test_id}: {file_obj.file_name if file_obj else 'None'}")

        if not file_obj:
            logger.error(f"Test {test_id} does not have a file associated")
            return {"error": f"Test {test_id} does not have a file associated"}, 400
            
        # Check if file_id exists
        if not file_obj.file_id:
            logger.error(f"Test {test_id} does not have a file associated")
            return {"error": f"Test {test_id} does not have a file associated"}, 400
            
        # Get file URL from test
        file_url = file_obj.file_url
        if not file_url:
            logger.error(f"Test {test_id} does not have a file URL")
            return {"error": f"Test {test_id} does not have a file URL"}, 400
            
        # Download the file from blob storage
        try:
            local_file_path = f"{file_obj.file_name}"
            logger.info(f"Downloading file from {file_url} to {local_file_path}")
            fetch_blob(file_url, local_file_path)
            logger.info(f"Successfully downloaded file for test {test_id}")
        except Exception as e:
            logger.error(f"Error downloading file for test {test_id}: {str(e)}")
            return {"error": f"Failed to download file for test {test_id}: {str(e)}"}, 400
            
        # Read the first row from CSV
        try:
            # Parse CSV content using context manager to ensure file is properly closed
            with open(local_file_path, 'r') as csv_file:
                csv_reader = csv.reader(csv_file)
                headers = next(csv_reader, None)  # Get headers
                first_row = next(csv_reader, None)  # Get first data row
                
                if not headers:
                    logger.error(f"No headers found in CSV file for test {test_id}")
                    return {"error": f"No headers found in CSV file for test {test_id}"}, 400
                    
                if not first_row:
                    logger.error(f"No data rows found in CSV file for test {test_id}")
                    return {"error": f"No data rows found in CSV file for test {test_id}"}, 400
                
                logger.info(f"CSV headers: {headers}")
                logger.info(f"First row data: {first_row}")
                    
                # Create variables dictionary with header:value pairs
                variables_dict = {}
                for i, header in enumerate(headers):
                    if i < len(first_row):
                        variables_dict[header] = first_row[i]
                    else:
                        variables_dict[header] = ""
                        
                logger.info(f"Successfully loaded {len(variables_dict)} variables from CSV for test {test_id}")
                logger.info(f"Variables dictionary: {variables_dict}")
                return variables_dict, 200
            
        except Exception as e:
            logger.error(f"Error parsing CSV file for test {test_id}: {str(e)}")
            return {"error": f"Failed to parse CSV file for test {test_id}: {str(e)}"}, 400
        finally:
            # Delete the local file if it exists
            if local_file_path and os.path.exists(local_file_path):
                logger.info(f"Cleaning up local file: {local_file_path}")
                os.remove(local_file_path)
            
    except Exception as e:
        logger.error(f"Error in load_test_data_variables_from_csv: {str(e)}")
        logger.debug(traceback.format_exc())
        return {"error": f"Unexpected error loading test data variables: {str(e)}"}, 500