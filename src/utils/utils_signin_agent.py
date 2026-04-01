import json
import traceback
import re
import uuid

from log_config.logger import logger
from service.service_redis import get_compose_session_from_redis, get_instruction_statuses
from utils.utils_constants import COMPOSE_AGENT_SIGN_IN, COMPOSE_AGENT_SIGN_UP
from utils.action_constants import *
from utils.utils_compose import get_compose_session_from_db
from service.service_compose import create_test_from_compose_session_implementation


def compile_instructions_from_sign_in_agent(compose_session: dict) -> list:
    """
    Compile instructions from the sign in agent.
    
    Args:
        compose_session (dict): The compose session dictionary containing instructions and goal_details
        
    Returns:
        list: Processed instructions array with playwright_actions, selectors, and scripts added
    """
    try:
        logger.info("Compiling instructions from sign in agent")
        
        processed_instructions = []
        instructions = compose_session.get("instructions", [])
        goal_details = compose_session.get("goal_details", {})
        playwright_actions = compose_session.get("playwright_actions", {})

        go_to_url_added = False
        
        for instruction in instructions:
            instruction_type = instruction.get("type", "")
            instruction_id = instruction.get("id", "")
            instruction_action = instruction.get("action", "")

            if instruction_type == NON_AI_ACTION and instruction_action == GO_TO_URL and not go_to_url_added:
                # get playwright_actions by instruction id
                playwright_actions_for_instruction = playwright_actions.get(instruction_id, [])
                instruction["playwright_actions"] = playwright_actions_for_instruction
                processed_instructions.append(instruction)
                go_to_url_added = True
            
            if instruction_type == GOAL_ACTION and instruction_id == SIGN_IN_GOAL_INSTRUCTION:
                # For Goal type, get instructions from goal_details
                if instruction_id in goal_details:
                    goal_instruction_list = goal_details[instruction_id].get("instructions", [])
                    actions_responses = goal_details[instruction_id].get("actionsResponses", [])
                    
                    # Process each instruction in the goal
                    for idx, goal_instruction in enumerate(goal_instruction_list):
                        processed_instruction = goal_instruction.copy()
                        
                        # Add scripts and selectors from actionsResponses based on array index
                        if idx < len(actions_responses):
                            action_response = actions_responses[idx]
                            processed_instruction["scripts"] = action_response.get("scripts", [])
                            processed_instruction["selectors"] = action_response.get("selectors", {})
                        
                        processed_instructions.append(processed_instruction)
            
            else:
                continue
        
        logger.info(f"Successfully compiled {len(processed_instructions)} instructions")
        return processed_instructions
        
    except Exception as e:
        logger.error(f"Error in compile_instructions_from_sign_in_agent: {str(e)}")
        logger.debug(traceback.format_exc())
        raise e


def create_suite_and_test_from_sign_in_agent(run_id: str, current_user: dict) -> None:
    """
    Create a new suite and test from the sign in agent.
    Checks for instruction failures and only creates suite/test if no failures occurred.
    
    Args:
        run_id (str): The run ID of the sign in agent
    """
    try:
        from app import app
        with app.app_context():
            logger.info(f"Creating suite and test from sign in agent with run_id: {run_id}")
            # get the compose session from the redis
            compose_session = get_compose_session_from_redis(run_id)
            if not compose_session:
                logger.error(f"Compose session not found for run_id: {run_id}")
                return None, 200
            
            # get compose object from the db
            compose_obj = get_compose_session_from_db(run_id)
            # create a new suite
            agent_type = compose_obj["agent_type"]
            agent_args = compose_obj["agent_args"]

            
            if agent_type == COMPOSE_AGENT_SIGN_IN or agent_type == COMPOSE_AGENT_SIGN_UP:
                instruction_status = get_instruction_statuses(run_id)
                
                # Check if any instruction failed
                has_failure = False
                for instruction_id, status in instruction_status.items():
                    if status == "failed":
                        has_failure = True
                        logger.info(f"Instruction {instruction_id} failed in compose session {run_id}")
                        break
                
                if has_failure:
                    logger.info(f"Compose session {run_id} has instruction failures, skipping suite/test creation")
                    return None, 200
                
                # check if instruction_status for sign_in_goal_instruction is "success"
                if instruction_status.get(SIGN_IN_GOAL_INSTRUCTION) != "success":
                    return None, 200
                suite_name = agent_args["suite_name"]
                test_name = agent_args["test_name"]
                instructions = compile_instructions_from_sign_in_agent(compose_session)
                # create a new test
                data = {
                    "suite_name": suite_name,
                    "name": test_name,
                    "instructions": instructions
                }
                logger.info(f"Creating test with data: {data}")
                response = create_test_from_compose_session_implementation(current_user, data)
                logger.info(f"Test created with response: {response}")
                return response, 200
    except Exception as e:
        logger.error(f"Error in create_suite_and_test_from_sign_in_agent: {str(e)}")
        logger.debug(traceback.format_exc())
        raise e

def get_default_suite_and_test_name(url: str, suite_name: str, test_name: str) -> str:
    """
    Get the default suite name from the url.
    Args:
        url (str): The url to get the default suite name from
    Returns:
        str: The default suite name
    """
    if not suite_name:
        # Remove protocol (text before //) if present
        if '//' in url:
            url_without_protocol = url.split('//', 1)[1]
        else:
            url_without_protocol = url
        
        # Keep only text until the first dot
        if '.' in url_without_protocol:
            url_until_first_dot = url_without_protocol.split('.')[0]
        else:
            url_until_first_dot = url_without_protocol
        
        # Remove special characters and keep only alphanumeric and hyphens
        suite_name = re.sub(r'[^a-zA-Z0-9\-]', '', url_until_first_dot)
    # if test name is none, use the suite name as the test name
    if not test_name:
        test_name = 'SIGN IN FLOW'

    return suite_name, test_name

def create_instructions_for_sign_in_flow(url: str, username: str, password: str) -> list:
    """
    Create instructions for the sign in flow.
    
    Args:
        url (str): The URL of the sign in page
        username (str): The username for the sign in
        password (str): The password for the sign in
    """
    # create an intructions list with action go_to_url, and 2 goals: find sign up page, and complete sign up with username and password
    instructions = [
        get_go_to_url_instruction(url),
        get_sign_in_goal_instruction(username, password),
        get_stop_instruction()
    ]
    return instructions;

def create_instructions_for_sign_up_flow(url: str, username: str, password: str) -> list:
    """
    Create instructions for the sign up flow.
    """
    return [
        get_go_to_url_instruction(url),
        get_sign_up_goal_instruction(username, password),
        get_verify_email_goal_instruction(url, username),
        get_clear_browser_instruction(),
        get_go_to_url_instruction(url),
        get_sign_in_goal_instruction(username, password),
        get_stop_instruction()
    ]

def get_go_to_url_instruction(url: str) -> dict:
    """
    Get the go to url instruction.
    Args:
        url (str): The URL to go to
    Returns:
        dict: The go to url instruction
    """
    return {
        "id": str(uuid.uuid4()),
        "action": GO_TO_URL,
        "args": [{"key": "url", "value": url}],
        "type": NON_AI_ACTION
    }

def get_sign_in_goal_instruction(username: str, password: str) -> dict:
    """
    Get the sign in goal instruction.
    Args:
        username (str): The username for the sign in
        password (str): The password for the sign in
    Returns:
        dict: The sign in goal instruction
    """
    # strip all characters after @ and remove the + sign from the username
    username_cleaned = username.split('@')[0]
    username_cleaned = username_cleaned.replace('+', '')

    return {
        "id": SIGN_IN_GOAL_INSTRUCTION,
        "action": AI_GOAL,
        "args": [{"key": "prompt", "value": f"Find the sign in page and sign in with username or email as {username} and password as {password}."}],
        "type": GOAL_ACTION
    }

def get_sign_up_goal_instruction(username: str, password: str) -> dict:
    """
    Get the sign up goal instruction.
    Args:
        username (str): The username for the sign up
        password (str): The password for the sign up
    Returns:
        dict: The sign up goal instruction
    """
    # strip all characters after @ and remove the + sign from the username
    username_cleaned = username.split('@')[0]
    username_cleaned = username_cleaned.replace('+', '')

    return {
        "id": SIGN_UP_GOAL_INSTRUCTION,
        "action": AI_GOAL,
        "args": [{"key": "prompt", "value": f"Find the sign up page and sign up with username or email as {username} and password as {password}. \
            If username is not accepted with special characters, use {username_cleaned} \
            Only if mandatory, use the following details: Name: John Doe, First Name: Mehul, Last Name: Jain, \
            Company: LitmusCheck, Address: 1st block,2nd street, City: New York, State: NY, Zip: 10001, \
            Country: USA, Phone: 1234567890, Mobile: 1234567890, Email: {username}. \
            You can generate random inputs to complete any onboarding steps like choosing role, industry, etc. \
            Mark the goal as completed if you end up at the email verification step or the logged in dashboard page. \
            You can click on Continue, Register, Sign up buttons as many times as needed. \
            Mark as failure if you see a captcha or any error message, or if you fail twice."}],
        "type": GOAL_ACTION
    }

def get_verify_email_goal_instruction(url: str, username: str) -> dict:
    """
    Get the verify email goal instruction.
    Args:
        username (str): The username for the verify email
    Returns:
        dict: The verify email goal instruction
    """
    return {
        "id": str(uuid.uuid4()),
        "action": VERIFY_EMAIL,
        "args": [{"key": "prompt", "value":f"Verify the email: {username} using verification code or link, if required. \
            If the current screen is an error screen, mark the step as failure. \
            Else If the current screen is not a verification screen, mark the step as successful without taking any additional steps."}],
        "type": GOAL_ACTION
    }

def get_clear_browser_instruction() -> dict:
    """
    Get the clear browser instruction.
    Returns:
        dict: The clear browser instruction
    """
    return {
        "id": str(uuid.uuid4()),
        "action": CLEAR_BROWSER,
        "type": CLEAR_ACTION
    }

def get_stop_instruction() -> dict:
    """
    Get the stop instruction.
    Returns:
        dict: The stop instruction
    """
    return {
        "id": str(uuid.uuid4()),
        "type": STOP_ACTION
    }