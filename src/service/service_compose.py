import traceback
import uuid
import json
from log_config.logger import logger
from service.service_browserbase import *
from models.Test import Test
from service.service_redis import *
from service.service_test import *
from service.service_suite import *
from database import db
from utils.utils_docker import DockerManager
from utils.utils_compose import *
from service.service_test_segment import *
from utils.utils_pom import *
from utils.utils_playwright_config import get_config_from_request
from service.service_file_upload import replace_file_upload_instruction
from utils.utils_test_data import load_test_data_variables_from_csv
from utils.utils_test import add_script_to_playwright_instruction
from service.service_credits import check_if_user_has_enough_ai_credits, check_if_user_has_enough_credits
from utils.utils_constants import DUMMY_SUITE_ID, COMPOSE_AGENT_SIGN_IN, COMPOSE_AGENT_SIGN_UP, COMPOSE_MODE, COMPOSE_AGENT

docker_manager = DockerManager()

def create_compose_session_implemenation(current_user: dict, environment: str = 'browserbase', request_data: dict = None, source: str = COMPOSE_USER, agent_type: str = None, agent_args: dict = None) -> dict:
    """
    Create a compose session.
    Args:
        current_user: dict
        environment: str - 'browserbase' or 'litmus_cloud'
        request_data: dict - request data
    Returns:
        dict: response
    """
    # Initialize IDs outside try block to ensure they're available in exception handler
    compose_id = str(uuid.uuid4())
    activity_log_id = str(uuid.uuid4())
    
    try:
        logger.info(f"Starting compose session creation for user {current_user.get('user_id')} with environment {environment}")

        # Check if suite_id is present in the request data
        suite = None
        suite_id = request_data.get("suite_id")
        is_dummy_suite = (suite_id == DUMMY_SUITE_ID)
        
        if suite_id and not is_dummy_suite:
            # check if suite_id is valid and user has access to it
            suite = return_suite_obj(current_user, suite_id)
            logger.info(f"Suite found: {suite}")

        # For dummy suite_id, we'll use org_id from current_user (for credit decrement)
        if is_dummy_suite:
            org_id = current_user.get('org_id')
            if not org_id:
                return {"error": "Org ID not found in current_user"}, 400
            logger.info(f"Using dummy suite_id, org_id from current_user: {org_id}")
        elif not suite:
            return {"error": "Suite not found"}, 404
        else:
            org_id = suite.org_id

        # Check if the org has enough credits
        if is_dummy_suite:
            # For dummy suite_id, check credits using org_id from current_user
            credits_check_resp, status_code = check_if_user_has_enough_credits(org_id=org_id)
            if status_code != 200:
                return credits_check_resp, status_code
        else:
            # Check if the org that owns the suite/test has enough credits
            credits_check_resp, status_code = check_if_user_has_enough_credits(suite_id=suite.suite_id)
            if status_code != 200:
                return credits_check_resp, status_code

        # get config from request_data
        # For dummy suite, pass None as suite parameter
        config, status_code = get_config_from_request(request_data, suite if not is_dummy_suite else None)
        if status_code != 200:
            return config, status_code
        
        # Check if the request data has test_id and load variables if available
        test_id = request_data.get("test_id")
        has_test_data = request_data.get("has_test_data", False)
        data_driven_variables_dict = {}
        global_variables_dict = {}
        environment_variables_dict = {}
        
        if has_test_data:
            # Load test data variables from CSV if test has data
            logger.info(f"[{compose_id}] Loading test data variables from test_id: {test_id}")
            data_driven_variables_dict, status_code = load_test_data_variables_from_csv(test_id)
            if status_code != 200:
                logger.warning(f"[{compose_id}] Failed to load test data variables: {data_driven_variables_dict}")
                return data_driven_variables_dict, status_code

        # Check if environment_id is present in request_data, if yes validate it
        environment_id = request_data.get('environment_id')
        environment_name = request_data.get('environment_name')
        if environment_id or environment_name:
            # suite has to be present in request_data (not dummy)
            if is_dummy_suite or not suite:
                return {"error": "Suite not found or suite_id is missing in request_data"}, 404
            
            # check if environment_id is valid and user has access to it
            var_environment, error_msg, status_code = validate_environment_access_implementation(current_user, environment_id, environment_name, suite.suite_id)
            if status_code != 200:
                return {"error": error_msg}, status_code

            # Add all the environment variables to the variables_dict
            if var_environment:
                environment_obj = var_environment.serialize()
                environment_variables_dict = environment_obj.get('variables',{})

        # Add both global and environment variables to the global_variables_dict
        global_variables_dict['data_driven_variables'] = data_driven_variables_dict
        global_variables_dict['environment_variables'] = environment_variables_dict
        
        
        try:
            additional_labels = {}
            additional_labels["source"] = source
            if source == COMPOSE_AGENT:
                additional_labels["agent_type"] = agent_type
            
            browserbase_session_id, live_url = compose_session_creation_helper(current_user, compose_id, activity_log_id, environment, config, global_variables_dict, additional_labels)
        except Exception as e:
            return {"error": str(e)}, 500
            
        # Create new compose session object
        create_compose_session_db(current_user, compose_id, environment, browserbase_session_id, config=config, test_id=test_id, source=source, agent_type=agent_type, agent_args=agent_args, environment_variables=environment_variables_dict)

        # Add activity log entry
        logger.info(f"[{compose_id}] Adding activity log entry")
        # Create new user where org_id is from suite or current_user (for dummy suite)
        new_user = {
            "user_id": current_user.get("user_id"),
            "org_id": org_id  # Use org_id we determined above
        }
        create_activity_log(new_user, activity_log_id, compose_id, COMPOSE_MODE, environment)

        # Add compose session to Redis
        suite_id_to_store = suite_id if suite_id else None
        add_compose_session_to_redis(compose_id, browserbase_session_id, global_variables_dict, suite_id_to_store)
        
        logger.info(f"[{compose_id}] Compose session creation completed successfully")
        return {"compose_id": compose_id, "live_url": live_url, "config": config}, 200
            
    except Exception as e:
        logger.error(f"[{compose_id}] Error in create_compose_session_implemenation: {e}")
        logger.debug(traceback.format_exc())
        return {"error": f"Failed to create compose session: {str(e)}"}, 500

def run_instructions_one_by_one_implementation(current_user: dict, compose_id: str, request_data: dict, environment: str) -> dict:
    """
    Run the instructions one by one by calling the agent
    """
    try:

        compose_session = get_compose_session_from_redis(compose_id)
        # check if compose_session is not None
        if compose_session is None:
            return {"message": "Compose session not found"}, 404
        
        live_url = None
        browserbase_session_id = compose_session["browserbase_session_id"]

        # Get the variables dict from the compose session redis. This will be non empty only if the test has test data
        variables_dict = compose_session.get("variables_dict", {})
        logger.info(f"Variables dict: {variables_dict}")
        data_driven_variables_dict = variables_dict.get("data_driven_variables", {})
        environment_variables_dict = variables_dict.get("environment_variables", {})

        # check if run_from_start is true
        if request_data.get("run_from_start"):
            logger.info(f"[{compose_id}] Running from start")

            # Clear instruction status,instructions and playwright actions and set reset flag to true
            clear_instruction_from_redis(compose_id)

            # Check if the environment_id is also present in the request
            environment_id = request_data.get("environment_id")
            if environment_id:
                # suite has to be present in request_data
                suite_id = request_data.get("suite_id")
                if not suite_id:
                    return {"error": "Suite not found or suite_id is missing in request_data"}, 404
                # check if environment_id is valid and user has access to it
                environment, error_msg, status_code = validate_environment_access_implementation(current_user, environment_id, suite_id)
                if status_code != 200:
                    return {"error": error_msg}, status_code

                environment_variables_dict = environment.serialize().get("variables")

                # Update compose session with the environment variables
                compose_session["environment_variables"] = environment_variables_dict
                set_compose_session_in_redis(compose_id, compose_session)
                logger.info(f"[{compose_id}] Compose session updated in redis with environment variables")

                # Update the environment in the compose session db
                update_compose_session_db(compose_id, environment_variables=environment_variables_dict)

            # Update the browserbase session timeout to 20 mins only if browserbase_session_id exists
            if compose_session["browserbase_session_id"]:
                update_browserbase_session(compose_session["browserbase_session_id"], timeout=BROWSERBASE_SESSION_TIMEOUT)

        suite_id = compose_session.get("suite_id", None)
        new_instructions = request_data["instructions"]
        new_instruction_ids = []
        for instruction in new_instructions:
            ins_index = instruction.get("id")

            # Check if the element_id is present
            element_id = check_if_element_id_is_present_in_instruction(instruction)
            if element_id:
                if not suite_id:
                    return {"error": "Suite is necessary when element_id is present in the instruction"}, 404
                element = return_element_obj(current_user, element_id, suite_id)
                logger.info(f"Element found: {element}")
                if not element:
                    return {"error": "Element not found"}, 404

                instruction, status_code = update_instruction_with_element_data(current_user, instruction, element)
                if status_code != 200:
                    return {"error": instruction}, status_code
            
            # First check if the instruction has playwright actions
            response, status_code = check_if_instruction_has_ai_instruction(current_user, instruction, suite_id)
            if status_code != 200:
                logger.info(f"Error in check_if_instruction_has_ai_instruction for instruction {ins_index}: {response}")
                return response, status_code
                

            logger.info(f"Instruction after updating with element data: {instruction}")

            # Before appending check if the instruction is a test segment
            if instruction.get("type") == TEST_SEGMENT:

                logger.info(f"Instruction is a test segment, validating test segment existence and replacing with child instructions {instruction}")
                # Now get list of instructions from the test segment
                segment_instructions, status_code = validate_test_segment_existence_and_replace_with_test_segment_instruction(current_user, instruction)
                if status_code != 200:
                    # segment_instructions holds the error message
                    if isinstance(segment_instructions, list) and len(segment_instructions) > 0 and "error" in segment_instructions[0]:
                        return segment_instructions[0], status_code
                    return {"error": "Failed to validate test segment"}, status_code

                logger.info(f"Got {len(segment_instructions)} instructions from test segment")
                
                # Process each instruction from the segment
                for segment_instruction in segment_instructions:
                    # If the instruction is ai_file_upload, add the file url to the instruction args
                    response, status_code = replace_file_upload_instruction(current_user, segment_instruction)
                    if status_code != 200:
                        return response, status_code
                    
                    segment_instruction = response

                    # Validate the instruction with the variables dict
                    data_driven_req_variables = get_variables_from_instructions(instruction=segment_instruction)
                    logger.info(f"Request data driven variables for instruction {segment_instruction.get('id')}: {data_driven_req_variables}")

                    # Validate the instruction with the environment variables dict
                    environment_req_variables = get_environment_variables_from_instruction(instruction=segment_instruction)
                    logger.info(f"Request environment variables for instruction {segment_instruction.get('id')}: {environment_req_variables}")
                    response, status_code = validate_environment_variables_implementation(list(environment_variables_dict.keys()), environment_req_variables)
                    if status_code != 200:
                        logger.error(f"Error in validate_environment_variables for instruction {segment_instruction.get('id')}: {response}")
                        return {"error": response}, status_code

                    # Use the instruction ID from the segment (already formatted as parent_id_1, parent_id_2, etc.)
                    segment_instruction_id = str(segment_instruction.get("id"))
                    compose_session["instructions"].append(segment_instruction)
                    new_instruction_ids.append(segment_instruction_id)
                    
                    # Store playwright actions if present
                    if segment_instruction.get("playwright_actions"):
                        compose_session["playwright_actions"][segment_instruction_id] = segment_instruction.get("playwright_actions")
                
                # Skip processing the original segment instruction since we've processed its children
                continue

            # If the instruction is ai_file_upload, add the file url to the instruction args
            response, status_code = replace_file_upload_instruction(current_user, instruction)
            if status_code != 200:
                return response, status_code
            
            instruction = response

            # Validate the instruction with the variables dict
            data_driven_req_variables = get_variables_from_instructions(instruction=instruction)
            logger.info(f"Request data driven variables for instruction {ins_index}: {data_driven_req_variables}")
            # response, status_code = validate_column_names_and_variables(list(data_driven_variables_dict.keys()), data_driven_req_variables)
            # if status_code != 200:
            #     logger.error(f"Error in validate_column_names_and_variables for instruction {ins_index}: {response}")
            #     return {"error": response}, status_code

            # Validate the instruction with the environment variables dict
            environment_req_variables = get_environment_variables_from_instruction(instruction=instruction)
            logger.info(f"Request environment variables for instruction {ins_index}: {environment_req_variables}")
            response, status_code = validate_environment_variables_implementation(list(environment_variables_dict.keys()), environment_req_variables)
            if status_code != 200:
                logger.error(f"Error in validate_column_names_and_variables for instruction {ins_index}: {response}")
                return {"error": response}, status_code

            instruction["id"] = str(ins_index)    # Change the id to string, to maintain consistency
            compose_session["instructions"].append(instruction)
            new_instruction_ids.append(str(ins_index))

        
        # check if the docker container is running with the label mode=compose and run_id=compose_id. If not create a new one
        label = {"mode": "compose", "run_id": compose_id}
        # Check the environment and check if the container/pod is running
        is_crashed = False
        curr_env = os.getenv('ENVIRONMENT', DEFAULT_ENV)
        if curr_env == DEFAULT_ENV:
            if not docker_manager.check_if_docker_container_is_running(label):

                is_crashed, exit_time = docker_manager.container_is_crashed(label)
                if is_crashed:
                    logger.info(f"[{compose_id}] Docker container is crashed at {exit_time}, creating new compose session")
        else:
            from utils.utils_aks import AksManager
            aks_manager = AksManager()
            if not aks_manager.check_if_aks_pod_is_running(label):
                is_crashed, exit_time = aks_manager.aks_pod_is_crashed(label)
                if is_crashed:
                    logger.info(f"[{compose_id}] AKS pod is crashed at {exit_time}, creating new compose session")

        if is_crashed:
            logger.info(f"[{compose_id}] {is_crashed} container/pod is crashed, creating a new one")
            try:
                new_activity_log_id = str(uuid.uuid4())

                # Get the config from the compose session. Create new session with old config
                compose_session_db = get_compose_session_from_db(compose_id)
                config = compose_session_db.get("config")

                browserbase_session_id, live_url = compose_session_creation_helper(current_user, compose_id, new_activity_log_id, environment, config, variables_dict)

                # Add activity log entry
                logger.info(f"[{compose_id}] Adding activity log entry")
                create_activity_log(current_user, new_activity_log_id, compose_id, COMPOSE_MODE, environment)

                
            except Exception as e:
                return {"message": str(e)}, 500

            # Update the browserbase session id, env, status and end_date to null in the compose session db
            update_compose_session_db(compose_id, browserbase_session_id=browserbase_session_id, environment=environment, status="running")

            # Update the instrcution_status to pending for all the instructions
            new_instruction_ids = [str(instruction["id"]) for instruction in compose_session["instructions"]]

         
        # Update the browserbase session id in the compose session redis. When the container is started again, you need to update the browserbase session id in the redis
        compose_session["browserbase_session_id"] = browserbase_session_id
        
        # Update statuses first, then publish updated session/instructions.
        # This avoids exposing new instructions before their status entries exist.
        if new_instruction_ids:
            pending_updates = {}
            for inst_id in new_instruction_ids:
                pending_updates[inst_id] = "pending"
            update_instruction_statuses(compose_id, pending_updates)
        # Add the compose session to the redis
        set_compose_session_in_redis(compose_id, compose_session)
        logger.info(f"[{compose_id}] Compose session updated in redis")
        logger.info(get_compose_session_from_redis(compose_id))
        response = {"message": "Run started successfully", "live_url": live_url}   # live_url is None if docker is already running

        return response, 200
        
    except Exception as e:
        logger.error(f"Error in run_instructions_one_by_one: {e}")
        logger.debug(traceback.format_exc())
        raise e

def get_compose_status_implementation(compose_id: str, instruction_id: str) -> dict:
    """
    Get the status of the compose session
    Args:
        compose_id: str
        instruction_id: str
    Returns:
        dict: response
    Args:
        compose_id: str
        instruction_id: str
    Returns:
        dict: response
    """
    try:
        # Get the compose session from the redis
        compose_session = get_compose_session_from_redis(compose_id)

        # Check if the compose session is not None
        if compose_session is None:
            return {"message": "Compose session not found"}, 404

        instruction_status = compose_session["instruction_status"]

        # Add playwright instructions to the result
        playwright_actions = compose_session["playwright_actions"]

        result = []
        
        # Get selectors and scripts for this instruction
        selectors = compose_session.get("selectors", {}).get(instruction_id, []) if instruction_status.get(instruction_id, "") == "success" else []
        scripts = compose_session.get("scripts", {}).get(instruction_id, []) if instruction_status.get(instruction_id, "") == "success" else []
        
        # Add scripts to corresponding selectors
        if selectors and scripts:
            # Match scripts to selectors based on index
            for i, selector in enumerate(selectors):
                if i < len(scripts):
                    selector["script"] = scripts[i]
                else:
                    selector["script"] = ""
        elif selectors:
            # If no scripts, add empty script to each selector
            for selector in selectors:
                selector["script"] = ""
        
        # Check if this instruction_id was expanded into a segment (look for instructions with instruction_id + "_" prefix)
        # For example, if instruction_id is "abc123", look for "abc123_1", "abc123_2", "abc123_0" in Redis
        related_instruction_ids = []
        for ins_id in instruction_status.keys():
            if ins_id.startswith(f"{instruction_id}_"):
                related_instruction_ids.append(ins_id)
        
        status = instruction_status.get(instruction_id, "pending")
        
        # If we found related instructions with "_" suffix, it means this instruction was expanded into a segment
        if related_instruction_ids:
            # Find first instruction (should be _1) and last instruction (should be _0)
            first_instruction_id = None
            last_instruction_id = None
            
            # Last instruction is always _0
            last_instruction_id = f"{instruction_id}_0"
            if last_instruction_id not in related_instruction_ids:
                # If _0 doesn't exist, it might be a single instruction case
                # In that case, find the instruction with the highest numeric suffix
                sorted_ids = sorted(
                    related_instruction_ids,
                    key=lambda x: int(x.rsplit("_", 1)[1]) if x.rsplit("_", 1)[1].isdigit() else -1,
                    reverse=True
                )
                last_instruction_id = sorted_ids[0] if sorted_ids else None
            
            # First instruction should be _1, or if not found, the one with smallest numeric suffix (excluding _0)
            first_instruction_id = f"{instruction_id}_1"
            if first_instruction_id not in related_instruction_ids:
                # Sort by the numeric suffix, excluding _0
                sorted_ids = sorted(
                    [ins_id for ins_id in related_instruction_ids if not ins_id.endswith("_0")],
                    key=lambda x: int(x.rsplit("_", 1)[1]) if x.rsplit("_", 1)[1].isdigit() else 999
                )
                first_instruction_id = sorted_ids[0] if sorted_ids else last_instruction_id
            
            # Get statuses for all related segment instructions.
            related_statuses = [
                instruction_status.get(related_id, "pending") for related_id in related_instruction_ids
            ]
            
            # Apply robust aggregate logic:
            # - If any instruction failed -> failed
            # - If all instructions are completed/success -> success
            # - If any instruction is running -> running
            # - If some are success/completed and others are still pending -> running
            # - Otherwise -> pending
            if any(status_value == "failed" for status_value in related_statuses):
                status = "failed"
            elif all(status_value in ["success", "completed"] for status_value in related_statuses):
                status = "success"
            elif any(status_value == "running" for status_value in related_statuses):
                status = "running"
            elif (
                any(status_value in ["success", "completed"] for status_value in related_statuses)
                and any(status_value == "pending" for status_value in related_statuses)
            ):
                status = "running"
            else:
                status = "pending"
        
        new_result = {
            "id": instruction_id,
            "status": status,
            "playwright_actions": playwright_actions[instruction_id] if instruction_id in playwright_actions and status == "success" else [],
            "selectors": selectors
        }

        result.append(new_result)

        return {"result": result}, 200
    except Exception as e:
        logger.error(f"Error in get_compose_status_implementation: {e}")
        logger.debug(traceback.format_exc())
        return {"error": "Unable to get compose status"}, 500
    
def create_test_from_compose_session_implementation(current_user, request_data: dict) -> dict:
    """
    Create a test from a compose session
    """
    try:

        suite_id = request_data.get("suite_id")
        test_name = request_data.get("name")

        # Check if the test has test data. Validate the file. 
        error, status_code = validate_test_data_file(request_data)
        if status_code != 200:
            return {"message": error}, status_code

        # Validate description word limit if present
        description = request_data.get('description')
        error, status_code = validate_description_word_limit(description)
        if status_code != 200:
            return {"error": error}, status_code

        if suite_id is not None:
            # check if suite_id is valid and user has access to it
            suite_obj = return_suite_obj(current_user, suite_id)
            if not suite_obj:
                return {
                    "error": f"Suite with id {suite_id} not found or user does not have access to it"
                }, 404
            
        if not request_data.get("instructions"):
            return {"message": "Instructions are required"}, 400
        
        raw_instructions = request_data.get("instructions")

        instructions = []
        playwright_actions = {}
        instruction_status = {}
        # selectors = {}
        logger.info(f"Processing instructions for saving to test")
        for each_instruction in raw_instructions:
            if each_instruction.get("id") is None:
                return {"message": "Instruction id is required is missing for one of the instructions"}, 400
            id = str(each_instruction["id"])
            playwright_actions[id] = each_instruction.get("playwright_actions", [])
            instruction_status[id] = each_instruction.get("status", "")
            # selectors[id] = each_instruction.get("selectors", [])

            # Check if the instruction is a test segment
            if each_instruction.get("type") == TEST_SEGMENT:
                # Make playwright actions empty for the test segment instruction
                playwright_actions[id] = []

            # Check if the instruction type is run_script and check if the script is empty
            playwright_actions[id] = add_script_to_playwright_instruction(each_instruction, playwright_actions[id])
            
            each_instruction.pop("playwright_actions", None)
            each_instruction.pop("status", None)
            # each_instruction.pop("selectors", None)
            instructions.append(each_instruction)

        # Create a new test with status draft
        status = TEST_STATUS_DRAFT
            
        # Validate instructions and playwright actions
        is_valid, error = validate_instructions(current_user, instructions)
        if not is_valid:
            return {
                "error": error
            }, 400
        logger.info(f"Validated instructions")

        if playwright_actions is not None:
            logger.info(f"[{instructions}, {playwright_actions}] Validating playwright actions")
            is_valid = validate_playwright_instructions_against_instructions(playwright_actions, instructions)
            if not is_valid:
                return {
                    "error": "Invalid playwright actions"
                }, 400
        
        logger.info(f"Validated playwright actions")

        if suite_id is None:              # Create suite first
            config, status_code = get_config_from_request(request_data)
            if status_code != 200:
                return config, status_code
            response, status_code = create_suite_implementation(current_user, {'name': request_data.get('suite_name'), 'config': config})
            if status_code != 200:
                return response, status_code
            suite_id = response.get('suite_id')


        # Validate custom_test_id uniqueness within suite if provided
        custom_test_id = request_data.get("custom_test_id")
        if custom_test_id and suite_id:
            existing = Test.query.filter_by(
                custom_test_id=custom_test_id,
                suite_id=suite_id
            ).first()
            if existing:
                return {
                    "error": f"Test with custom_test_id '{custom_test_id}' already exists in this suite"
                }, 400

        # Create a new test
        test = Test(
            id=str(uuid.uuid4()),
            name=test_name,
            description=request_data.get('description'),
            instructions=json.dumps(instructions),
            playwright_instructions=json.dumps(playwright_actions),
            # selectors=json.dumps(selectors),
            suite_id=suite_id,
            status=status,
            has_test_data=request_data.get("has_test_data", False),
            file_id=request_data.get("file_id", None),
            custom_test_id=custom_test_id,
        )
        db.session.add(test)
        db.session.commit()
        logger.info(f"Test created with id: {test.id}")
        return test.serialize(), 200
    except Exception as e:
        logger.error(f"Error in create_test_from_compose_session_implementation: {e}")
        logger.debug(traceback.format_exc())
        return {"error": str(e)}, 500

def update_test_from_compose_session_implementation(current_user, test_id: str, request_data: dict) -> dict:
    """
    Update a test from a compose session
    """
    try:
        if not request_data.get("instructions"):
            return {"message": "Instructions are required"}, 400
        
        raw_instructions = request_data.get("instructions")

        instructions = []
        playwright_actions = {}
        instruction_status = {}
        # selectors = {}
            
        for each_instruction in raw_instructions:
            if each_instruction.get("id") is None:
                return {"message": "Instruction id is required is missing for one of the instructions"}, 400
            id = str(each_instruction["id"])
            playwright_actions[id] = each_instruction.get("playwright_actions", [])
            instruction_status[id] = each_instruction.get("status", "")
            # selectors[id] = each_instruction.get("selectors", [])

            # Check if the instruction is a test segment
            if each_instruction.get("type") == TEST_SEGMENT:
                # Make playwright actions empty for the test segment instruction
                playwright_actions[id] = []

            # Check if the instruction type is run_script and check if the script is empty
            playwright_actions[id] = add_script_to_playwright_instruction(each_instruction, playwright_actions[id])
            
            each_instruction.pop("playwright_actions", None)
            each_instruction.pop("status", None)
            # each_instruction.pop("selectors")
            instructions.append(each_instruction)

        request_data["playwright_instructions"] = playwright_actions
        response, status_code = update_test_implementation(current_user, request_data, test_id)
        
        return response, status_code
    except Exception as e:
        logger.error(f"Error in update_test_from_compose_session_implementation: {e}")
        logger.debug(traceback.format_exc())
        return {"error": str(e)}, 500

def close_compose_session_implementation(current_user: dict, compose_id: str) -> dict:
    """
    Close a compose session
    """
    try:
        compose_session = get_compose_session_from_redis(compose_id)
        logger.info(f"[{compose_id}] Compose session found in redis: {compose_session}")

        # Check if the compose session is not None
        if compose_session is None:
            logger.error(f"[{compose_id}] Compose session not found")
            return {"message": "Compose session not found"}, 404
        
        curr_env = os.getenv('ENVIRONMENT', DEFAULT_ENV)
        if curr_env == DEFAULT_ENV:
            # kill the docker containers with label mode=compose and run_id=compose_id
            logger.info("Killing container by label")
            docker_manager.kill_container_with_label({"mode": "compose", "run_id": compose_id})
            logger.info("Container killed")
        else:
            from utils.utils_aks import AksManager
            aks_manager = AksManager()
            aks_manager.kill_pods_with_label({"mode": "compose", "run_id": compose_id})
            logger.info("AKS pod deleted")

        # Get the compose session from db and do not update credits if the session is already completed
        compose_session_from_db = get_compose_session_from_db(compose_id)
        if compose_session_from_db and compose_session_from_db.get("status") == "completed":
            logger.info(f"[{compose_id}] Compose session is already completed, not updating credits")
            return {"message": "Compose session is already closed"}, 200

        # Change the status of the compose session to completed
        update_compose_session_db(compose_id, status="completed")
        logger.info("Compose session status updated to completed")

        # Get the ai_credits from the compose session
        ai_credits = compose_session.get("ai_credits") if compose_session else None

        # Update the activity log table
        logger.info(f"[{compose_id}] Updating activity log, to end the compose session")
        update_activity_log(current_user, reference_id=compose_id, end_time=datetime.now(timezone.utc), ai_credits_consumed=ai_credits)

        return {"message": "Compose session closed successfully"}, 200
    except Exception as e:
        logger.error(f"Error in close_compose_session_implementation: {e}")
        logger.debug(traceback.format_exc())
        return {"error": str(e)}, 500

def send_live_urls_implementation(current_user: dict, compose_id: str) -> dict:
    """
    Send live URLs to the user
    """
    try:
        compose_session = get_compose_session_from_redis(compose_id)
        if compose_session is None:
            return {"message": "Compose session not found"}, 404
        
        browserbase_session_id = compose_session["browserbase_session_id"]

        # Get the live urls from the browserbase session
        try:
            session = get_session_debug_urls(browserbase_session_id)
            pages = session.pages
        except Exception as e:
            logger.error(f"Error in get_session_debug_urls: {e}")
            return {"error": str(e)}, 500

        live_urls = []
        for page in pages:
            live_urls.append({"live_url": page.debugger_fullscreen_url, "title": page.title, "url": page.url})

        return {"live_urls": live_urls}, 200
    except Exception as e:
        logger.error(f"Error in send_live_urls_implementation: {e}")
        logger.debug(traceback.format_exc())
        return {"error": str(e)}, 500

def check_if_instruction_has_ai_instruction(current_user: dict, instruction: dict, suite_id: str) -> tuple[dict, int]:
    """
    Check if the instruction has an AI instruction
    Args:
        current_user: dict
        instruction: dict
        suite_id: Suite ID
    Returns:
        tuple[dict, int]: Message if the instruction has an AI instruction, False otherwise
    """
    try:
        has_playwright_scripts = (instruction.get("playwright_actions") and 
                                        len(instruction.get("playwright_actions", [])) > 0)
            
        # If the instruction has playwright actions, don't check AI credits
        if not has_playwright_scripts:
            # Check AI credits for AI instructions or verification with prompt
            instruction_type = instruction.get("type")
            action = instruction.get("action")


            is_ai_instruction = (instruction_type == "AI")
            is_verification_with_prompt = (action == "verify" and instruction.get("args") and 
                                        any(arg.get("key") == "prompt" and arg.get("value") for arg in instruction.get("args", [])))
            is_goal = (action == "goal")
            
            if is_ai_instruction or is_verification_with_prompt or is_goal:
                logger.info(f"Checking if user has enough AI credits for instruction {instruction}")
                # Check if user has enough AI credits
                try:
                    credits_check_resp, status_code = check_if_user_has_enough_ai_credits(suite_id=suite_id)
                    if status_code != 200:
                        return credits_check_resp, status_code
                except Exception as e:
                    logger.error(f"Error checking AI credits: {e}")
                    return {"error": "Error checking AI credits"}, 500
        logger.info(f"No AI instruction found or AI credits are sufficient for instruction {instruction}")
        return {"message": "No AI instruction found or AI credits are sufficient"}, 200
    except Exception as e:
        logger.error(f"Error in check_if_instruction_has_ai_instruction: {e}")
        logger.debug(traceback.format_exc())
        return {"error": "Error checking AI credits"}, 500