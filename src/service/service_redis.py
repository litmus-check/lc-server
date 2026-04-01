import os
import json
import redis
import traceback
import uuid
from utils.action_constants import *
from utils.utils_constants import *
from log_config.logger import logger

redis_client = redis.from_url(os.getenv('REDIS_URL'), socket_timeout=5)

INSTRUCTION_STATUS_KEY_SUFFIX = ":instruction_status"


def get_instruction_status_key(run_id: str) -> str:
    """Return Redis hash key used to store instruction statuses for a run."""
    return f"{run_id}{INSTRUCTION_STATUS_KEY_SUFFIX}"


def _decode_redis_value(value):
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return value


def get_instruction_statuses(run_id: str) -> dict:
    """
    Get all instruction statuses for a run from the dedicated Redis hash key.
    """
    try:
        status_key = get_instruction_status_key(run_id)
        raw_statuses = redis_client.hgetall(status_key) or {}
        return {_decode_redis_value(k): _decode_redis_value(v) for k, v in raw_statuses.items()}
    except Exception as e:
        logger.error(f"Error in get_instruction_statuses: {str(e)}")
        logger.debug(traceback.print_exc())
        return {}


def update_instruction_statuses(run_id: str, updates: dict, ttl: int = None) -> None:
    """
    Update statuses for only the given instruction IDs in the dedicated hash key.
    Never touches other instruction IDs.
    """
    if not updates:
        return
    if ttl is None:
        ttl = REDIS_DATA_TTL
    try:
        status_key = get_instruction_status_key(run_id)
        payload = {str(k): str(v) for k, v in updates.items()}
        redis_client.hset(status_key, mapping=payload)
        redis_client.expire(status_key, ttl)
    except Exception as e:
        logger.error(f"Error in update_instruction_statuses: {str(e)}")
        logger.debug(traceback.format_exc())
        raise


def delete_instruction_statuses(run_id: str) -> None:
    """Delete instruction statuses hash key for a run."""
    try:
        redis_client.delete(get_instruction_status_key(run_id))
    except Exception as e:
        logger.error(f"Error in delete_instruction_statuses: {str(e)}")
        logger.debug(traceback.print_exc())
        raise
    
def add_log_to_redis(testrun_id: str, log: dict) -> None:
    """
    Add a log entry to Redis for a given test run ID.
    """
    try:
        log_data = redis_client.get(testrun_id)
        if log_data:
            log_data = json.loads(log_data)
            logs = log_data.setdefault("logs", {})  # If logs key is not present, then create it
            log_data.setdefault("counter", 0)      # If counter key is not present, then create it
        else:
            log_data = {"logs": {}, "counter": 0}
            logs = log_data["logs"]

        if log:
            # Check if the previous log for the instructionId is same as current instructionId
            current_logs = logs.get('current_logs', [])
            previous_log = current_logs[-1] if current_logs else None
            if previous_log and previous_log.get("instruction") == "system":
                # If the previous log is same as current instructionId, then add the log to the previous log
                previous_log["logs"].append(log)
                log_data["logs"]["current_logs"] = current_logs
            else:
                # If the previous log is not same as current instructionId, then add the log to the new instructionId
                current_logs.append(
                    {
                        "instruction":"system",
                        "logs": [log]
                    }
                )
                log_data["logs"]["current_logs"] = current_logs
        redis_client.set(testrun_id, json.dumps(log_data), ex=REDIS_DATA_TTL)

    except Exception as e:
        logger.error(f"Error in add_logs_to_redis: {str(e)}")
        logger.debug(traceback.print_exc())

def clear_entry_from_redis(testrun_id: str) -> None:
    """
    Function to clear logs from Redis for a given test run ID.
    """
    try:
        redis_client.delete(testrun_id)
        redis_client.delete(get_instruction_status_key(testrun_id))
        logger.info(f"Logs cleared for test run ID: {testrun_id}")
    except Exception as e:
        logger.error(f"Error in clear_entry_from_redis: {str(e)}")
        logger.debug(traceback.print_exc())

def get_logs_from_redis(testrun_id: str) -> dict:
    """
    Function to get logs from Redis for a given test run ID.
    """
    try:
        log_data = redis_client.get(testrun_id)
        if log_data:
            log_data = json.loads(log_data)
            return log_data['logs']
        return None
    except Exception as e:
        logger.error(f"Error in get_logs_from_redis: {str(e)}")
        logger.debug(traceback.print_exc())
        return None
    
def get_test_result_from_redis(testrun_id: str) -> dict:
    """
    Function to get test run data from Redis for a given test run ID.
    Args:
        testrun_id (str): The ID of the test run
    Returns:
        dict: The test run data, or None if not found
    """
    try:
        test_run_data = redis_client.get(testrun_id)
        if test_run_data:
            test_run_data = json.loads(test_run_data)
            return test_run_data.get('test_result')
        return None
    except Exception as e:
        logger.error(f"Error in get_test_run_data_from_redis: {str(e)}")
        logger.debug(traceback.print_exc())
        return None
    
def create_log_instruction_from_instruction_dict(instruction: dict) -> str:
    """
    Function to create a log instruction from an instruction dictionary.
    """
    instruction_str = instruction.get('action', '')

    # If action type is AI then add prompt to instruction string
    if instruction.get('action') in SUPPORTED_AI_ACTIONS:
        instruction_str += f" | {instruction.get('prompt')}"

    # If action type is Run Script then donot add script arg to instruction string
    if instruction.get('action') == RUN_SCRIPT:
        return instruction_str
        
    for arg in instruction.get('args', []):
        instruction_str += f" | {arg['value']}"
    return instruction_str

def store_browserbase_urls(testrun_id: str, url: str) -> None:
    """
    Store the Browserbase URLs for a test run.
    
    Args:
        testrun_id (str): The ID of the test run
        urls: The Browserbase URLs data
    """
    try:
        logger.info(f"Storing browserbase URLs for test run {testrun_id}")
        redis_client.set(testrun_id, url, ex=REDIS_DATA_TTL)
        logger.info(f"Successfully stored browserbase URLs for test run {testrun_id}")
    except Exception as e:
        logger.error(f"Error storing browserbase URLs: {str(e)}")
        logger.debug(traceback.format_exc())

def get_browserbase_urls(testrun_id: str) -> str:
    """
    Get the Browserbase URLs for a test run.
    
    Args:
        testrun_id (str): The ID of the test run
        
    Returns:
        str: The Browserbase URLs data, or None if not found
    """
    try:
        logger.info(f"Retrieving browserbase URLs for test run {testrun_id}")
        live_stream_url = redis_client.get(testrun_id)
        logger.info(f"Retrieved browserbase URLs: {live_stream_url}")
        if live_stream_url:
            # Decode bytes to string
            return live_stream_url.decode('utf-8')
        return None
    except Exception as e:
        logger.error(f"Error getting debug URLs: {str(e)}")
        logger.debug(traceback.format_exc())
        return None

def get_active_org_ids_from_current_runs() -> list[str]:
    """
    Get the active org ids from the current runs in redis. Structure in redis
    current_runs: {
        "testrun_id": "org_id",
        "suite_run_id": "org_id",
    }
    """
    try:
        current_runs = redis_client.get('current_runs')
        if current_runs:
            current_runs = json.loads(current_runs)
            return list(set(current_runs.values()))
        return []
    except Exception as e:
        logger.error(f"Error in get_active_org_ids_from_current_runs: {str(e)}")
        logger.debug(traceback.print_exc())
        return []

def add_to_current_runs(run_id: str, org_id: str) -> None:
    """
    Add the org id to the current runs in redis.
    """
    try:
        current_runs = redis_client.get('current_runs')
        if current_runs:
            current_runs = json.loads(current_runs)
            current_runs[run_id] = org_id
        else:
            current_runs = {run_id: org_id}
        redis_client.set('current_runs', json.dumps(current_runs))
    except Exception as e:
        logger.error(f"Error in add_to_current_runs: {str(e)}")
        logger.debug(traceback.print_exc())

def remove_from_current_runs(run_id: str) -> None:
    """
    Remove the org id from the current runs in redis.
    """
    try:
        current_runs = redis_client.get('current_runs')
        if current_runs:
            current_runs = json.loads(current_runs)
            current_runs.pop(run_id, None)
        redis_client.set('current_runs', json.dumps(current_runs))
    except Exception as e:
        logger.error(f"Error in remove_from_current_runs: {str(e)}")
        logger.debug(traceback.print_exc())

def _get_rate_limit_key(org_id: str) -> str:
    """
    Generate Redis key for rate limit.
    Args:
        org_id: Organization ID
    Returns:
        Redis key string (just the org_id)
    """
    return org_id

def get_available_rate_limits(org_ids: list[str]) -> dict[str, dict]:
    """
    Get available rate limits for all orgs from Redis.
    Returns dict of org_id -> {"available_limit": int, "max_limit": int}
    Each org is stored as a separate key (org_id) with JSON value.
    """
    try:
        result = {}
        for org_id in org_ids:
            org_data = redis_client.get(org_id)
            
            if org_data:
                limits = json.loads(org_data)
                result[org_id] = {
                    "available_limit": int(limits.get("available_limit", 0)),
                    "max_limit": int(limits.get("max_limit", 0))
                }
        
        return result
    except Exception as e:
        logger.error(f"Error in get_available_rate_limits: {str(e)}")
        logger.debug(traceback.print_exc())
        return {}

def decrement_available_rate_limit(org_id: str):
    """
    Decrement available rate limit for org_id.
    Uses Lua script for atomic operation.
    """
    try:
        rate_limit_key = _get_rate_limit_key(org_id)
        
        # Lua script for atomic decrement
        lua_script = """
        local key = KEYS[1]
        local data = redis.call('GET', key)
        
        if data == false then
            return nil
        end
        
        local limits = cjson.decode(data)
        local available = tonumber(limits.available_limit)
        
        if available > 0 then
            limits.available_limit = available - 1
            redis.call('SET', key, cjson.encode(limits))
            return limits.available_limit
        else
            return -1
        end
        """
        
        result = redis_client.eval(lua_script, 1, rate_limit_key)
        
        if result is None:
            raise Exception(f"Org {org_id} not found in available rate limits")
        
        logger.info(f"Decremented available rate limit for org {org_id}: {result}")
    except Exception as e:
        logger.error(f"Error in decrement_available_rate_limit: {str(e)}")
        logger.debug(traceback.print_exc())
        raise e

def increment_available_rate_limit(org_id: str) -> None:
    """
    Increment available rate limit for org_id.
    Won't exceed max_limit. Uses Lua script for atomic operation.
    """
    try:
        rate_limit_key = _get_rate_limit_key(org_id)
        
        # Lua script for atomic increment with max limit check
        lua_script = """
        local key = KEYS[1]
        local data = redis.call('GET', key)
        
        if data == false then
            return nil
        end
        
        local limits = cjson.decode(data)
        local available = tonumber(limits.available_limit)
        local max_limit = tonumber(limits.max_limit)
        
        if available < max_limit then
            limits.available_limit = available + 1
            redis.call('SET', key, cjson.encode(limits))
            return limits.available_limit
        else
            return available
        end
        """
        
        result = redis_client.eval(lua_script, 1, rate_limit_key)
        
        if result is None:
            raise Exception(f"Org {org_id} not found in available rate limits")
        
        new_value = int(result)
        logger.info(f"Incremented available rate limit for org {org_id}: {new_value}")
    except Exception as e:
        logger.error(f"Error in increment_available_rate_limit: {str(e)}")
        logger.debug(traceback.print_exc())

def initialize_available_rate_limits() -> None:
    """
    Initialize available rate limits from DB to Redis.
    Should be called on app startup. While creating check if the org_id is already in redis. If not then add it.
    Each org is stored as a separate key with JSON value.
    """
    try:
        from app import app
        with app.app_context():
            from models.OrgQueueConfig import OrgQueueConfig
            configs = OrgQueueConfig.query.all()

            for config in configs:
                max_limit = int(config.rate_limit)
                org_id = config.org_id
                rate_limit_key = _get_rate_limit_key(org_id)
                
                # If the org_id is not in redis then add it
                if redis_client.get(rate_limit_key) is None:
                    org_data = {
                        "available_limit": max_limit,
                        "max_limit": max_limit
                    }
                    redis_client.set(rate_limit_key, json.dumps(org_data))
                    logger.info(f"Initialized rate limits for org {org_id}: available={max_limit}, max={max_limit}")
            
            logger.info(f"Initialized available rate limits for {len(configs)} orgs")
    except Exception as e:
        logger.error(f"Error in initialize_available_rate_limits: {str(e)}")
        logger.debug(traceback.print_exc())

def add_new_org_to_available_rate_limits(org_id: str, rate_limit: int) -> None:
    """
    Add a new org to the available rate limits.
    Each org is stored as a separate key with JSON value.
    """
    try:
        rate_limit_key = _get_rate_limit_key(org_id)
        org_data = {
            "available_limit": rate_limit,
            "max_limit": rate_limit
        }
        redis_client.set(rate_limit_key, json.dumps(org_data))
        logger.info(f"Added rate limits for org {org_id}: available={rate_limit}, max={rate_limit}")
    except Exception as e:
        logger.error(f"Error in add_new_org_to_available_rate_limits: {str(e)}")
        logger.debug(traceback.print_exc())

def update_org_rate_limit_in_redis(org_id: str, new_rate_limit: int) -> None:
    """
    Update an organization's max and available rate limits in Redis.
    - Sets max_limit to new_rate_limit
    - If available_limit > max_limit after update, clamp to max_limit
    - If org not present, create entry with available_limit=max_limit=new_rate_limit
    Each org is stored as a separate key with JSON value.
    Uses Lua script for atomic operation.
    """
    try:
        rate_limit_key = _get_rate_limit_key(org_id)
        new_rate_limit_int = int(new_rate_limit)
        
        # Lua script for atomic update
        lua_script = """
        local key = KEYS[1]
        local new_max = tonumber(ARGV[1])
        local data = redis.call('GET', key)
        
        if data == false then
            -- Org not present, create entry
            local org_data = {
                available_limit = new_max,
                max_limit = new_max
            }
            redis.call('SET', key, cjson.encode(org_data))
            return cjson.encode({available = new_max, max = new_max, created = true})
        else
            -- Org exists, update limits
            local limits = cjson.decode(data)
            local current_available = tonumber(limits.available_limit) or 0
            local current_max = tonumber(limits.max_limit) or 0
            
            if new_max > current_max then
                -- Rate limit increased: add difference to available_limit
                local increase_amount = new_max - current_max
                limits.available_limit = current_available + increase_amount
                limits.max_limit = new_max
            else
                -- Rate limit decreased: clamp available_limit to max_limit if needed
                limits.max_limit = new_max
                if current_available > new_max then
                    limits.available_limit = new_max
                end
            end
            
            redis.call('SET', key, cjson.encode(limits))
            return cjson.encode({
                available = limits.available_limit,
                max = limits.max_limit,
                created = false
            })
        end
        """
        
        result = redis_client.eval(lua_script, 1, rate_limit_key, new_rate_limit_int)
        result_data = json.loads(result)
        
        if result_data.get("created"):
            logger.info(f"Created rate limits for org {org_id}: available={result_data['available']}, max={result_data['max']}")
        else:
            logger.info(f"Updated rate limits for org {org_id}: available={result_data['available']}, max={result_data['max']}")
    except Exception as e:
        logger.error(f"Error in update_org_rate_limit_in_redis: {str(e)}")
        logger.debug(traceback.print_exc())

def add_compose_session_to_redis(compose_id: str, browserbase_session_id: str, variables_dict: dict, suite_id: str):
    """
    Add a compose session to Redis for a test run.
    
    Args:
        compose_id (str): The ID of the compose session
        browserbase_session_id (str): The ID of the browserbase session
        variables_dict (dict): The variables dictionary
        suite_id (str): The ID of the suite
    """
    try:
        logger.info(f"[{compose_id}] Adding compose session to redis")
        # Pickle the agent object before storing in redis
        data = {
            "instructions": [],
            "playwright_actions": {},
            "selectors": {},                         # Store selectors for each instruction
            "scripts": {},                           # Store scripts for each instruction
            "reset": False,                          # Flag to check if the run has to start from the beginning
            "browserbase_session_id": browserbase_session_id,
            "variables_dict": variables_dict,
            "ai_credits": 0.00,                       # AI credits consumed by the compose session,
            "stop_on_error": False,
            "suite_id": suite_id,
        }
        redis_client.set(compose_id, json.dumps(data), ex=REDIS_DATA_TTL)
        # Ensure no stale status hash remains for this run key.
        delete_instruction_statuses(compose_id)
    except Exception as e:
        logger.error(f"Error in add_compose_session_to_redis: {str(e)}")
        logger.debug(traceback.print_exc())

def get_compose_session_from_redis(compose_id: str) -> dict:
    """
    Get the compose session from Redis for a test run.
    """
    try:
        session_data = redis_client.get(compose_id)
        if session_data:
            session = json.loads(session_data)
            # instruction_status is stored separately as a Redis hash.
            session["instruction_status"] = get_instruction_statuses(compose_id)
            return session
        return None
    except Exception as e:
        logger.error(f"Error in get_compose_session_from_redis: {str(e)}")
        logger.debug(traceback.print_exc())

def set_compose_session_in_redis(compose_id: str, data: dict) -> None:
    """
    Set the compose session in Redis for a test run.
    """
    try:
        # instruction_status is stored in a dedicated hash key, never in session JSON.
        if isinstance(data, dict):
            data = dict(data)
            data.pop("instruction_status", None)
        redis_client.set(compose_id, json.dumps(data), ex=REDIS_DATA_TTL)
    except Exception as e:
        logger.error(f"Error in set_compose_session_in_redis: {str(e)}")
        logger.debug(traceback.print_exc())

def update_compose_instructions_batch(compose_id: str, modified_instructions: list) -> None:
    """
    Update all modified instructions in the compose session by replacing them with updated versions.
    This approach updates all modified instructions at once to prevent data loss.
    
    Args:
        compose_id: The compose session ID
        modified_instructions: List of instruction objects that have been modified
    """
    try:
        # Get current session data
        current_session = get_compose_session_from_redis(compose_id)
        if not current_session:
            logger.warning(f"No compose session found for {compose_id}")
            return
        
        # Get current instructions
        current_instructions = current_session.get("instructions", [])
        if not current_instructions:
            logger.warning(f"No instructions found in compose session {compose_id}")
            return
        
        # Create a mapping of instruction IDs to modified instructions for quick lookup
        modified_instructions_map = {inst.get("id"): inst for inst in modified_instructions}
        
        # Update the instructions list with modified versions
        instructions_updated = False
        for i, instruction in enumerate(current_instructions):
            instruction_id = instruction.get("id")
            if instruction_id in modified_instructions_map:
                # Replace the instruction with the modified version
                current_instructions[i] = modified_instructions_map[instruction_id]
                instructions_updated = True
                logger.debug(f"Updated instruction {instruction_id} in compose session {compose_id}")
        
        if instructions_updated:
            # Update the session with modified instructions
            current_session["instructions"] = current_instructions
            set_compose_session_in_redis(compose_id, current_session)
            logger.info(f"Batch updated {len(modified_instructions)} instructions in compose session {compose_id}")
        else:
            logger.warning(f"No matching instructions found for updates in compose session {compose_id}")
            
    except Exception as e:
        logger.error(f"Error in update_compose_instructions_batch: {str(e)}")
        logger.debug(traceback.print_exc())

def clear_instruction_from_redis(compose_id: str) -> None:
    """
    Clear the instruction, instruction status and playwright actions from Redis for a test run.
    """
    try:
        data = get_compose_session_from_redis(compose_id)
        data["instructions"] = []
        data["playwright_actions"] = {}
        data["selectors"] = {}
        data["scripts"] = {}
        data["reset"] = True
        set_compose_session_in_redis(compose_id, data)
        delete_instruction_statuses(compose_id)
    except Exception as e:
        logger.error(f"Error in clear_instruction_from_redis: {str(e)}")
        logger.debug(traceback.print_exc())

def add_test_run_retries_to_redis(testrun_id: str, retries: int) -> None:
    """
    Add new key in logs with key as attempt number and value as log
    """
    try:
        logger.info(f"Adding test run retries to redis for test run {testrun_id} {retries}")
        complete_redis_data = redis_client.get(testrun_id)
        try:
            complete_redis_data = json.loads(complete_redis_data)
        except Exception as e:
            logger.error(f"Error in adding test run retries to redis: {str(e)}")
            logger.debug(traceback.print_exc())
            return
        
        logger.info(f"Complete redis data: {complete_redis_data}")
        old_logs = complete_redis_data.get('logs', {})

        # Get current logs
        current_logs = old_logs.get('current_logs', [])

        # Add new key in logs with key as attempt number and value as log
        old_logs[f"failed_attempt_{retries}"] = current_logs

        # Make current logs empty
        old_logs['current_logs'] = []

        logger.info(f"New logs dict: {old_logs}")
        complete_redis_data['logs'] = old_logs

        logger.info(f"Complete redis data after adding test run retries: {complete_redis_data}")
        redis_client.set(testrun_id, json.dumps(complete_redis_data))
    except Exception as e:
        logger.error(f"Error in add_test_run_retries_to_redis: {str(e)}")
        logger.debug(traceback.print_exc())

def create_goal_in_redis(compose_id: str, prompt: str) -> str:
    """
    Create a new goal in Redis for a given compose session.
    
    Args:
        compose_id (str): The ID of the compose session
        prompt (str): The prompt for the goal
    Returns:
        str: The generated goal ID
    """
    try:
        logger.info(f"Creating goal for compose_id: {compose_id}")
        
        # Generate a unique goal ID
        goal_id = str(uuid.uuid4())
        
        # Get the compose session from Redis
        session_data = get_compose_session_from_redis(compose_id)
        if not session_data:
            logger.error(f"No session data found for compose_id: {compose_id}, cannot create goal")
            raise Exception(f"No session data found for compose_id: {compose_id}, cannot create goal")
        
        # Initialize goal_data if it doesn't exist
        if "goal_data" not in session_data:
            session_data["goal_data"] = {}
        
        # Create the goal entry
        session_data["goal_data"][goal_id] = {
            "status": "pending",
            "instructions": [],
            "prompt": prompt
        }
        
        # Store the updated session data back to Redis
        set_compose_session_in_redis(compose_id, session_data)
        
        logger.info(f"Goal created successfully with ID: {goal_id}")
        return goal_id
        
    except Exception as e:
        logger.error(f"Error in create_goal_in_redis: {str(e)}")
        logger.error(traceback.format_exc())
        raise e

def get_goal_from_redis(compose_id: str, goal_id: str) -> dict:
    """
    Get goal data from Redis for a given compose session and goal ID.
    
    Args:
        compose_id (str): The compose session ID
        goal_id (str): The goal ID
        
    Returns:
        dict: Goal data containing status, instructions and playwright code, or None if not found
    """
    try:
        logger.info(f"Getting goal data for compose_id: {compose_id}, goal_id: {goal_id}")
        
        # Get the compose session from Redis
        session_data = get_compose_session_from_redis(compose_id)
        if not session_data:
            logger.warning(f"No session data found for compose_id: {compose_id}")
            raise Exception(f"No session data found for compose_id: {compose_id}")
            
        # Check if goal_data exists and contains the goal_id
        if "goal_data" not in session_data or goal_id not in session_data["goal_data"]:
            logger.warning(f"No goal data found for goal_id: {goal_id}")
            raise Exception(f"No goal data found for goal_id: {goal_id}")
        
        goal_data = session_data["goal_data"][goal_id]
        
        # Return the goal data with playwright code, selectors, and scripts
        result = {
            "status": goal_data.get("status", ""),
            "output": goal_data.get("output", ""),
            "reasoning": goal_data.get("reasoning", ""),
            "instructions": goal_data.get("instructions", []),
        }
        
        # Process instructions to add selectors with embedded scripts to each instruction
        if "instructions" in result and result["instructions"]:
            for instruction in result["instructions"]:
                instruction_id = instruction.get("id")
                if instruction_id:
                    # Get selectors and scripts for this instruction
                    instruction_selectors = session_data.get("selectors", {}).get(instruction_id, [])
                    instruction_scripts = session_data.get("scripts", {}).get(instruction_id, [])
                    
                    # Add scripts to corresponding selectors
                    if instruction_selectors and instruction_scripts:
                        # Match scripts to selectors based on index
                        for i, selector in enumerate(instruction_selectors):
                            if i < len(instruction_scripts):
                                selector["script"] = instruction_scripts[i]
                            else:
                                selector["script"] = ""
                    elif instruction_selectors:
                        # If no scripts, add empty script to each selector
                        for selector in instruction_selectors:
                            selector["script"] = ""
                    
                    # Add selectors to the instruction
                    instruction["selectors"] = instruction_selectors
        
        logger.info(f"Retrieved goal data: {result}")
        return result
        
    except Exception as e:
        logger.error(f"Error in get_goal_from_redis: {str(e)}")
        logger.error(traceback.format_exc())
        raise e


def get_org_id_for_entity(test_id: str = None, suite_obj: dict = None) -> str:
    """
    Resolve org_id using either test_id, or suite_obj.
    Priority: suite_obj.org_id > test_id lookup
    """
    try:
        # First priority: use suite_obj if available
        if suite_obj and isinstance(suite_obj, dict) and suite_obj.get('org_id'):
            return suite_obj['org_id']
        
        # Second priority: lookup by test_id
        if test_id:
            from app import app
            with app.app_context():
                from models.Test import Test
                test = Test.query.filter_by(id=test_id).first()
                if test and test.suite:
                    return test.suite.org_id
        
        return None
    except Exception as e:
        logger.error(f"Error in get_org_id_for_entity: {str(e)}")
        logger.debug(traceback.print_exc())
        return None