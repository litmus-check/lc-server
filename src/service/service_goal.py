import json
from log_config.logger import logger
from service.service_redis import create_goal_in_redis, get_compose_session_from_redis, get_goal_from_redis, set_compose_session_in_redis, update_instruction_statuses
from service.service_compose import create_compose_session_implemenation
import uuid
import traceback
from utils.utils_constants import COMPOSE_AGENT_SIGN_IN, COMPOSE_AGENT, COMPOSE_AGENT_SIGN_UP, BROWSERBASE_ENV
from utils.utils_signin_agent import create_instructions_for_sign_in_flow, create_instructions_for_sign_up_flow


def create_goal_implementation(compose_id: str, prompt: str) -> str:
    """
    Create a goal implementation using the Redis service.
    
    Args:
        compose_id (str): The compose session ID
        prompt (str): The prompt for the goal
    Returns:
        str: The generated goal ID
    """
    try:
        logger.info(f"Creating goal for compose_id: {compose_id}, prompt: {prompt}")
        goal_id = create_goal_in_redis(compose_id, prompt)
        return goal_id
        
    except Exception as e:
        logger.error(f"Error in create_goal_implementation: {str(e)}")
        raise e


def get_goal_status(compose_id: str, goal_id: str) -> dict:
    """
    Get goal status, instructions and playwright code from Redis.
    
    Args:
        compose_id (str): The compose session ID
        goal_id (str): The goal ID
        
    Returns:
        dict: Goal data containing status, instructions and playwright code, or None if not found
    """
    try:
        logger.info(f"Getting goal status for compose_id: {compose_id}, goal_id: {goal_id}")
        goal_data = get_goal_from_redis(compose_id, goal_id)
        return goal_data
        
    except Exception as e:
        logger.error(f"Error in get_goal_status: {str(e)}")
        raise e
    
def create_sign_in_flow_implementation(compose_id: str, url: str, username: str, password: str) -> str:
    """
    Create a sign in flow implementation using the Redis service.
    
    Args:
        compose_id (str): The compose session ID
        url (str): The URL of the sign in page
        username (str): The username for the sign in
        password (str): The password for the sign in
    """

    # create instructions for the sign in flow
    try:
        instructions = create_instructions_for_sign_in_flow(url, username, password)
        add_instructions_to_compose_session(compose_id, instructions, stop_on_error=True)
        return 200;
    except Exception as e:
        logger.error(f"Error in create_instructions_for_sign_in_flow: {str(e)}")
        logger.debug(traceback.format_exc())
        return 500;

def add_instructions_to_compose_session(compose_id: str, instructions: list, stop_on_error: bool = False) -> None:
    """
    Add instructions to the compose session.
    
    Args:
        compose_id (str): The compose session ID
        instructions (list): The instructions to add
    """
    try:# get the compose session from the redis
        compose_session = get_compose_session_from_redis(compose_id)
        # add the instructions to the compose session
        new_instruction_ids = []
        for instruction in instructions:
            compose_session["instructions"].append(instruction)
            new_instruction_ids.append(str(instruction["id"]))
        # update statuses first, then publish updated session/instructions
        pending_updates = {}
        for inst_id in new_instruction_ids:
            pending_updates[inst_id] = "pending"
        update_instruction_statuses(compose_id, pending_updates)
        # store the compose session in the redis
        compose_session["stop_on_error"] = stop_on_error
        set_compose_session_in_redis(compose_id, compose_session)
    except Exception as e:
        logger.error(f"Error in add_instructions_to_compose_session: {str(e)}")
        logger.debug(traceback.format_exc())
        raise e
    

def create_sign_up_flow_implementation(compose_id: str, url: str, username: str, password: str) -> str:
    """
    Create a sign up flow implementation using the Redis service.
    
    Args:
        compose_id (str): The compose session ID
        url (str): The URL of the sign up page
        username (str): The username for the sign up
        password (str): The password for the sign up
    """

    # create instructions for the sign up flow
    try:
        instructions = create_instructions_for_sign_up_flow(url, username, password)
        add_instructions_to_compose_session(compose_id, instructions, stop_on_error=True)
        return 200;
    except Exception as e:
        logger.error(f"Error in create_instructions_for_sign_up_flow: {str(e)}")
        logger.debug(traceback.format_exc())
        return 500;


def create_compose_session_and_sign_in_flow(current_user, request_data, agent_args):
    """
    Create a compose session and sign in flow implementation.
    
    Args:
        current_user: The current user object
        request_data: The request data containing url, username, password
        agent_args: Additional agent arguments
        
    Returns:
        tuple: (compose_session, status_code) or (None, error_status_code)
    """
    try:
        # Get environment query parameter, default to 'browserbase' if not provided
        environment = request_data.get('environment', BROWSERBASE_ENV)

        # create a new compose session
        compose_session, status_code = create_compose_session_implemenation(
            current_user, 
            environment, 
            request_data, 
            source=COMPOSE_AGENT, 
            agent_type=COMPOSE_AGENT_SIGN_IN, 
            agent_args=agent_args
        )
        if status_code != 200:
            return None, status_code
        
        logger.info(f"Created compose session: {compose_session}")

        url = request_data.get('url')
        username = request_data.get('username')
        password = request_data.get('password')
        
        status_code = create_sign_in_flow_implementation(compose_session["compose_id"], url, username, password)
        if status_code != 200:
            logger.error(f"Failed to create sign in flow: {status_code}")
            return None, status_code
            
        return compose_session, 200
        
    except Exception as e:
        logger.error(f"Error in create_compose_session_and_sign_in_flow: {str(e)}")
        logger.error(traceback.format_exc())
        return None, 500


def create_compose_session_and_sign_up_flow(current_user, request_data, agent_args):
    """
    Create a compose session and sign up flow implementation.
    
    Args:
        current_user: The current user object
        request_data: The request data containing url, username, password
        agent_args: Additional agent arguments
        
    Returns:
        tuple: (compose_session, status_code) or (None, error_status_code)
    """
    try:
        # Get environment query parameter, default to 'browserbase' if not provided

        environment = request_data.get('environment', BROWSERBASE_ENV)

        # create a new compose session
        compose_session, status_code = create_compose_session_implemenation(
            current_user, 
            environment, 
            request_data, 
            source=COMPOSE_AGENT, 
            agent_type=COMPOSE_AGENT_SIGN_UP, 
            agent_args=agent_args
        )
        if status_code != 200:
            return None, status_code
        
        logger.info(f"Created compose session: {compose_session}")

        url = request_data.get('url')
        username = request_data.get('username')
        password = request_data.get('password')
        
        status_code = create_sign_up_flow_implementation(compose_session["compose_id"], url, username, password)
        if status_code != 200:
            logger.error(f"Failed to create sign up flow: {status_code}")
            return None, status_code
            
        return compose_session, 200
        
    except Exception as e:
        logger.error(f"Error in create_compose_session_and_sign_up_flow: {str(e)}")
        logger.error(traceback.format_exc())
        return None, 500

