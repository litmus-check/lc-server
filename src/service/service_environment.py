import re
import json
import traceback
import uuid
from database import db
from log_config.logger import logger
from models.Schedule import Schedule
from models.Environment import Environment
from service.service_suite import return_suite_obj
from utils.utils_constants import ENV_VARIABLE_REGEX_PATTERN


def create_environment_implementation(current_user: dict, data: dict) -> tuple[dict, int]:
    """
    Create a new environment
    Args:
        current_user: Dictionary containing user information including role and org_id
        data: Dictionary containing environment data
    Returns:
        Tuple of (response_dict, status_code)
    """
    try:
        environment_name = data.get('environment_name')
        suite_id = data.get('suite_id')
        variables = data.get('variables', {})

        # Strip the environment name
        environment_name = environment_name.strip()

        # Validate required fields
        if not environment_name:
            return {"error": "environment_name is required"}, 400
        if not suite_id:
            return {"error": "suite_id is required"}, 400

        # Check if suite exists and user has access to it
        suite_obj = return_suite_obj(current_user, suite_id)
        if not suite_obj:
            return {"error": "Suite not found or user does not have access to it"}, 404

        # Check if environment name already exists in this suite
        existing_env = Environment.query.filter_by(
            environment_name=environment_name,
            suite_id=suite_id
        ).first()
        
        if existing_env:
            logger.info(f"Environment with name '{environment_name}' already exists in this suite")
            return {"error": f"Environment with name '{environment_name}' already exists in this suite"}, 409

        # Validate variables
        if variables and type(variables) != dict:
            return {"error": "Variables must be JSON-serializable"}, 400

        # Create new environment
        environment = Environment(
            environment_id=str(uuid.uuid4()),
            environment_name=environment_name,
            suite_id=suite_id,
            variables=json.dumps(variables) if variables else None
        )

        db.session.add(environment)
        db.session.commit()

        logger.info(f"Environment with name '{environment_name}' created successfully in suite {suite_id}")
        return environment.serialize(), 201

    except Exception as e:
        logger.error(f"Error in create_environment_implementation: {str(e)}")
        logger.debug(traceback.format_exc())
        db.session.rollback()
        return {"error": "Internal server error"}, 500


def get_environment_by_id_implementation(current_user: dict, environment_id: str) -> tuple[dict, int]:
    """
    Get environment by ID
    Args:
        current_user: Dictionary containing user information including role and org_id
        environment_id: UUID of the environment
    Returns:
        Tuple of (response_dict, status_code)
    """
    try:
        environment = Environment.query.filter_by(environment_id=environment_id).first()
        
        if not environment:
            return {"error": "Environment not found"}, 404

        # Check if user has access to the suite
        suite_obj = return_suite_obj(current_user, environment.suite_id)
        if not suite_obj:
            return {"error": "User does not have access to this environment"}, 404

        return environment.serialize(), 200

    except Exception as e:
        logger.error(f"Error in get_environment_by_id_implementation: {str(e)}")
        logger.debug(traceback.format_exc())
        return {"error": "Internal server error"}, 500


def get_environments_by_suite_implementation(current_user: dict, suite_id: str) -> tuple[dict, int]:
    """
    Get all environments for a specific suite
    Args:
        current_user: Dictionary containing user information including role and org_id
        suite_id: UUID of the suite
    Returns:
        Tuple of (response_dict, status_code)
    """
    try:
        # Check if suite exists and user has access to it
        suite_obj = return_suite_obj(current_user, suite_id)
        if not suite_obj:
            return {"error": "Suite not found or user does not have access to it"}, 404

        # Get all environments for the suite
        environments = Environment.query.filter_by(suite_id=suite_id).all()

        environments_data = []

        for environment in environments:
            serialized_data = environment.serialize()

            # pop suite_id, created_at, modified_at
            serialized_data.pop('suite_id', None)
            serialized_data.pop('created_at', None)
            serialized_data.pop('modified_at', None)

            environments_data.append(serialized_data)
        
        return {"environments": environments_data}, 200

    except Exception as e:
        logger.error(f"Error in get_environments_by_suite_implementation: {str(e)}")
        logger.debug(traceback.format_exc())
        return {"error": "Internal server error"}, 500


def update_environment_implementation(current_user: dict, environment_id: str, request_data: dict) -> tuple[dict, int]:
    """
    Update an existing environment
    Args:
        current_user: Dictionary containing user information including role and org_id
        environment_id: UUID of the environment
        request_data: Dictionary containing updated environment data
    Returns:
        Tuple of (response_dict, status_code)
    """
    try:
        environment = Environment.query.filter_by(environment_id=environment_id).first()
        
        if not environment:
            return {"error": "Environment not found"}, 404

        # Check if user has access to the suite
        suite_obj = return_suite_obj(current_user, environment.suite_id)
        if not suite_obj:
            return {"error": "User does not have access to this environment"}, 404

        # Update fields if provided
        if 'environment_name' in request_data:
            new_name = request_data['environment_name']
            # Check if new name already exists in this suite (excluding current environment)
            existing_env = Environment.query.filter_by(
                environment_name=new_name,
                suite_id=environment.suite_id
            ).filter(Environment.environment_id != environment_id).first()
            
            if existing_env:
                logger.info(f"Environment with name '{new_name}' already exists in this suite")
                return {"error": f"Environment with name '{new_name}' already exists in this suite"}, 409
            
            environment.environment_name = new_name

        # Replace variables with new variables
        if 'variables' in request_data:
            new_variables = request_data['variables']
            # validate if new variables is a dictionary
            if not isinstance(new_variables, dict):
                return {"error": "Variables must be a valid JSON object"}, 400
            environment.variables = json.dumps(new_variables)

        environment.modified_at = db.func.now()

        db.session.commit()

        logger.info(f"Environment with name '{environment.environment_name}' updated successfully in suite {environment.suite_id}")
        return environment.serialize(), 200

    except Exception as e:
        logger.error(f"Error in update_environment_implementation: {str(e)}")
        logger.debug(traceback.format_exc())
        db.session.rollback()
        return {"error": "Internal server error"}, 500


def delete_environment_implementation(current_user: dict, environment_id: str) -> tuple[dict, int]:
    """
    Delete an environment
    Args:
        current_user: Dictionary containing user information including role and org_id
        environment_id: UUID of the environment
    Returns:
        Tuple of (response_dict, status_code)
    """
    try:
        environment = Environment.query.filter_by(environment_id=environment_id).first()
        
        if not environment:
            return {"error": "Environment not found"}, 404

        # Check if user has access to the suite
        suite_obj = return_suite_obj(current_user, environment.suite_id)
        if not suite_obj:
            logger.info(f"User does not have access to this environment")
            return {"error": "User does not have access to this environment"}, 404

        # Check if the environment is referenced in any schedules
        schedules = Schedule.query.filter_by(environment_id=environment_id).all()
        if schedules:
            logger.info(f"Cannot delete environment as it is referenced in schedules with id: " + ", ".join([schedule.id for schedule in schedules]))
            return {"error": "Cannot delete environment as it is referenced in schedules with id: " + ", ".join([schedule.id for schedule in schedules])}, 400

        db.session.delete(environment)
        db.session.commit()

        logger.info(f"Environment with name '{environment.environment_name}' deleted successfully in suite {environment.suite_id}")
        return {"message": "Environment deleted successfully"}, 200

    except Exception as e:
        logger.error(f"Error in delete_environment_implementation: {str(e)}")
        logger.debug(traceback.format_exc())
        db.session.rollback()
        return {"error": "Internal server error"}, 500


def validate_environment_access_implementation(current_user: dict, environment_id: str, environment_name: str, test_suite_id: str) -> tuple[Environment, str, int]:
    """
    Validate if environment exists and user has access to it, and if it belongs to the same suite as the test
    Args:
        current_user: Dictionary containing user information including role and org_id
        environment_id: UUID of the environment
        environment_name: Name of the environment
        test_suite_id: UUID of the test's suite
    Returns:
        Tuple of (environment_obj, error_message, status_code)
    """
    try:
        # Check if environment exists
        if environment_id:
            environment = Environment.query.filter_by(environment_id=environment_id).first()
        elif environment_name:
            environment = Environment.query.filter_by(environment_name=environment_name, suite_id=test_suite_id).first()

        if not environment:
            logger.info(f"Environment not found")
            return None, "Environment not found", 404

        # Check if user has access to the environment's suite
        suite_obj = return_suite_obj(current_user, environment.suite_id)
        if not suite_obj:
            logger.info(f"User does not have access to this environment")
            return None, "User does not have access to this environment", 403

        # Check if environment belongs to the same suite as the test
        if environment.suite_id != test_suite_id:
            logger.info(f"Environment does not belong to the same suite as the test")
            return None, "Environment does not belong to the same suite as the test", 400

        return environment, None, 200

    except Exception as e:
        logger.error(f"Error in validate_environment_access_implementation: {str(e)}")
        logger.debug(traceback.format_exc())
        return None, "Internal server error", 500


def get_environment_variables_from_instruction(playwright_instructions: dict=None, instruction: dict=None):
    """
    Extract environment variables from test instructions in {{env.variable_name}} format
    Args:
        playwright_instructions: Dictionary of playwright instructions. Format: {"uuid":["instruction1", "instruction2", "instruction3"]}
        instruction: Dictionary of instruction. Format: {"id": "1", "type": "Non-AI", "args": [{"key": "value"}], "prompt": "prompt"}
    Returns:
        List of environment variable names
    """
    
    env_variables = set()
    
    try:
        # Get the variables from the playwright instructions
        if playwright_instructions:
            logger.info(f"Extracting environment variables from playwright instructions with {len(playwright_instructions)} instruction groups")
            for ins_id, ins_list in playwright_instructions.items():
                for play_wright_ins in ins_list:
                    matches = re.findall(ENV_VARIABLE_REGEX_PATTERN, play_wright_ins)
                    for match in matches:
                        variable_name = match
                        env_variables.add(variable_name)
        
        # Get the variables from the instruction args
        if instruction and 'args' in instruction:
            logger.info("Extracting environment variables from instruction args")
            args = instruction['args']
            if isinstance(args, list):
                for arg in args:
                    for key, value in arg.items():
                        if isinstance(value, str):
                            matches = re.findall(ENV_VARIABLE_REGEX_PATTERN, value)
                            for match in matches:
                                variable_name = match
                                env_variables.add(variable_name)
        
        env_variables_list = list(env_variables)
        logger.info(f"Found {len(env_variables_list)} unique environment variables: {env_variables_list}")
        return env_variables_list
        
    except Exception as e:
        logger.error(f"Error in get_environment_variables_from_instructions: {str(e)}")
        logger.debug(traceback.format_exc())
        return []

def validate_environment_variables_implementation(available_variables: list, required_variables: list) -> tuple[str, int]:
    """
    Validate if all required environment variables are present in the environment
    Args:
        available_variables: List of available variable names
        required_variables: List of required variable names
    Returns:
        str: Error message if validation fails
        int: Status code
    """
    try:
        if not required_variables or len(required_variables) == 0:
            return None, 200

        for var in required_variables:
            if var not in available_variables:
                return f"Variable '{var}'s not found in the environment", 400
        
        return None, 200
    except Exception as e:
        logger.error(f"Error in validate_environment_variables_implementation: {str(e)}")
        logger.debug(traceback.format_exc())
        return "Internal server error", 500