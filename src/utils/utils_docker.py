import json
import docker
import traceback
import uuid
from docker.errors import APIError
from docker.models.containers import Container
from log_config.logger import logger
from datetime import datetime, timedelta, timezone
from utils.utils_constants import *
from utils.utils_constants import SUITE_COMPLETED_STATUS
from service.service_redis import get_test_result_from_redis, get_compose_session_from_redis, add_log_to_redis
from utils.utils_test import update_test_result_status, update_test_status, update_suite_run_status
from service.service_runner import TestRunner
from service.service_test import *
from service.service_queue import enqueue_run_request
from service.service_activity_log import update_activity_log
from service.service_triage import add_test_to_queue_with_triage_mode
from service.service_heal import add_test_to_queue_with_heal_mode
from utils.instruction_formatter import format_instruction_for_display
from dotenv import load_dotenv, find_dotenv
from database import db
import os
load_dotenv(find_dotenv("app.env"))

test_runner = TestRunner()
class DockerManager:
    """
    A singleton class that manages Docker container operations.
    This class ensures only one instance exists throughout the application lifecycle,
    preventing multiple Docker client connections and maintaining consistent state.
    """
    _instance = None

    def __new__(cls):
        """
        Implements the singleton pattern by ensuring only one instance is created.
        Returns the existing instance if one exists, otherwise creates a new one.
        """
        if cls._instance is None:
            cls._instance = super(DockerManager, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        """
        Initializes the Docker client connection.
        This method is called only once when the singleton instance is first created.
        """
        try:
            self.docker_client = docker.client.from_env()
        except Exception as e:
            logger.error(f"Failed to initialize Docker client: {e}")
            raise

    def check_and_cleanup_compose_containers(self):
        from utils.utils_compose import update_compose_session_db
        """
        Checks for and cleans up compose containers that have been running longer than the timeout period.
        This method:
        1. Lists all containers with the 'mode=compose' label
        2. Identifies containers that have been running longer than BROWSERBASE_SESSION_TIMEOUT minutes
        3. Uses kill_container_with_label to stop and remove these containers
        4. Logs the cleanup process
        """
        try:
            containers = self.docker_client.containers.list(all=True, filters={"label": "mode=compose"})
            
            for container in containers:
                try:
                    # Refresh container state to get latest status
                    container.reload()

                    current_user = json.loads(container.labels.get("current_user"))
                    activity_log_id = container.labels.get("activity_log_id")
                    compose_id = container.labels.get("run_id")
                    run_id = container.labels.get("run_id")

                    end_time = None
                    
                    if container.attrs["State"]["Status"] == "running":
                        # Check if container has been running longer than timeout
                        start_time = datetime.fromisoformat(container.attrs["State"]["StartedAt"][:-1]).replace(tzinfo=timezone.utc)
                        current_time = datetime.now(timezone.utc)
                        
                        if current_time - start_time > timedelta(seconds=BROWSERBASE_SESSION_TIMEOUT + 30):
                            
                            logger.info(f"Found long-running compose container {container.id} with run_id {run_id}, attempting cleanup")
                            
                            try:
                                end_time = datetime.now(timezone.utc)
                                
                                # Kill the container
                                self.kill_container_with_label({"mode": "compose", "run_id": run_id})

                                from app import app
                                with app.app_context():
                                    # Update the compose session status to completed
                                    update_compose_session_db(compose_id, status="completed")
                                    logger.info(f"Updated compose session status to completed for compose_id {compose_id}")
                            except Exception as cleanup_err:
                                logger.warning(f"Failed to cleanup compose container {container.id}: {cleanup_err}")
                                # Don't raise the exception to continue processing other containers
                                continue
                    
                    elif container.attrs["State"]["Status"] in ["exited", "dead"]:
                        # Check if the container has been running longer than the timeout
                        run_id = container.labels.get("run_id")
                        logger.info(f"Compose container {container.id} has been running longer than the timeout, attempting cleanup")

                        # check if additional labels source and agent_type are present
                        current_user = json.loads(container.labels.get("current_user"))
                        source = container.labels.get("source")
                        agent_type = container.labels.get("agent_type")
                        if source and agent_type and source == COMPOSE_AGENT and (agent_type == COMPOSE_AGENT_SIGN_IN or agent_type == COMPOSE_AGENT_SIGN_UP):
                            logger.info(f"Compose container {container.id} is a sign in/sign up container, attempting cleanup")
                            # call method from service_goal - it will check for failures internally
                            try:
                                from utils.utils_signin_agent import create_suite_and_test_from_sign_in_agent
                                create_suite_and_test_from_sign_in_agent(run_id, current_user)
                            except Exception as e:
                                logger.error(f"Error in create_suite_and_test_from_sign_in_agent: {str(e)}")
                                logger.debug(traceback.format_exc())
                                container.remove()
                                logger.info(f"✅ Removed container {container.id}")
                                continue
                        
                        # Clear logs from redis
                        container.remove()
                        logger.info(f"✅ Removed container {container.id}")
                        # clear_entry_from_redis(run_id)

                        # get the end time from the container
                        end_time = datetime.fromisoformat(container.attrs["State"]["FinishedAt"][:-1]).replace(tzinfo=timezone.utc)

                            
                        from app import app
                        with app.app_context():
                            # Update the compose session status to completed
                            update_compose_session_db(compose_id, status="completed")
                            logger.info(f"Updated compose session status to completed for compose_id {compose_id}")

                    # check for ai_credits and update the activity_log and credits table
                    compose_session = get_compose_session_from_redis(compose_id)
                    ai_credits = compose_session.get("ai_credits") if compose_session else None

                    if end_time:
                        # Update executed_seconds and ai_credits in the activity log and credits table.
                        update_activity_log(current_user, log_id=activity_log_id, end_time=end_time, ai_credits_consumed=ai_credits)
                    else:
                        # Update ai_credits in the activity log and credits table.
                        update_activity_log_with_ai_credits(current_user, log_id=activity_log_id, ai_credits_consumed=ai_credits)
                
                except docker.errors.NotFound:
                    logger.info(f"Container {container.id} no longer exists, skipping")
                    continue
                except Exception as e:
                    logger.error(f"Error processing compose container {container.id}: {e}")
                    continue
                
        except Exception as e:
            logger.error(f"Failed to check and cleanup compose containers: {e}")
            logger.debug(traceback.format_exc())
            # Don't raise the exception to prevent the entire cleanup process from failing

    def check_exited_containers_and_cleanup(self):
        """
        Checks for and cleans up exited Docker containers with the specified label.
        
        Args:
            label_selector (str): The label to filter containers by. Defaults to "mode=script".
        
        This method:
        1. Lists all containers (including stopped ones) with the specified label mode=script
        2. Identifies containers in 'exited' or 'dead' state
        3. Updates database with test run results
        4. Removes these containers to free up system resources
        5. Increases the rate limit
        6. Clears the logs from redis
        7. Add log entry in activity log table
        8. Checks and cleanup compose containers. Removes long running compose containers.
        9. Checks and cleanup exited triage containers.
        """
        try:
            # Include stopped containers with `all=True`
            label_selector = "mode=script"
            containers = self.docker_client.containers.list(all=True, filters={"label": label_selector})

            for container in containers:
                try:
                    status = container.attrs["State"]["Status"]
                    if status in ["exited", "dead"]:
                        run_id = container.labels.get("run_id")
                        queue_obj_str = container.labels.get("queue_obj")
                        
                        # Skip if queue_obj is None or empty
                        if not queue_obj_str:
                            logger.warning(f"No queue_obj found for container {container.id}")
                            continue
                            
                        try:
                            queue_obj = json.loads(queue_obj_str)
                        except json.JSONDecodeError as json_err:
                            logger.error(f"Failed to parse queue_obj for container {container.id}: {json_err}")
                            continue

                        # Get request data from queue_obj
                        test_id = queue_obj.get('test_id', None)
                        run_mode = queue_obj.get('run_mode', None)
                        suite_run_id = queue_obj.get('suite_run_id', None)
                        test_obj = queue_obj.get('test_obj', None)
                        container_retries = int(queue_obj.get("container_retries", 0))
                        test_run_retries = int(queue_obj.get("test_run_retries", 0))
                        current_user = queue_obj.get('current_user', None)
                        activity_log_id = queue_obj.get('activity_log_id', None)
                        row_number = queue_obj.get('row_number', None)
                        suite_obj = queue_obj.get('suite_obj', None)

                        # Get the data from redis
                        test_result = get_test_result_from_redis(run_id)

                        # Get the time when the container is exited
                        container_exit_time = self.get_container_exit_time(container.id)

                        # Get ai_credits from redis session if available
                        session = get_compose_session_from_redis(run_id)
                        ai_credits = session.get("ai_credits") if session else None

                        # Update activity log, this will also update the credits table
                        update_activity_log(current_user, log_id=activity_log_id, end_time=container_exit_time, ai_credits_consumed=ai_credits)
                        logger.info(f"Successfully updated activity log for test run {run_id} with end time {container_exit_time} and ai_credits {ai_credits}")

                        # Remove container to free space
                        container.remove()
                        logger.info(f"✅ Cleaned up container for run {run_id}")

                        # Increase rate limit since container has exited
                        run_org_id = get_org_id_for_entity(test_id=test_id, suite_obj=suite_obj)
                        test_runner.increase_rate_limit(org_id=run_org_id)

                        # Remove the org id from the current runs
                        remove_from_current_runs(run_id)

                        # The container is exited before the test result is updated in redis.
                        if test_result is None:
                            if container_retries < DOCKER_MAX_RETRIES:
                                # Add the test_obj back to queue to retry
                                container_retries = container_retries + 1
                                queue_obj["container_retries"] = container_retries

                                logger.info(f"Test result from container {container.id} not found in redis. Added test_obj back to queue to retry for run_id {run_id}")

                                add_log_to_redis(run_id, {"error": "Retrying the test", 'timestamp': datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",})

                                # Add logs to redis with attempt number as key
                                add_test_run_retries_to_redis(run_id, container_retries + test_run_retries)

                                enqueue_run_request(queue_obj)
                                continue
                            else:
                                logger.info(f"No test result found in redis for run_id {run_id}")
                                add_log_to_redis(run_id, {"error": "No test result received from container", 'timestamp': datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",})
                                test_result = {}

                        gif_url = test_result.get('gif_url', None)
                        trace_url = test_result.get('trace_url', None)
                        status = test_result.get('status', FAILED_STATUS)

                        if test_run_retries < TEST_MAX_RUN_RETRIES and status == FAILED_STATUS:
                            test_run_retries = test_run_retries + 1
                            queue_obj["test_run_retries"] = test_run_retries

                            logger.info(f"Test run failed for run_id {run_id}. Retrying the test for {test_run_retries} times")

                            add_log_to_redis(run_id, {"error": "Retrying the test as the test failed for the first time", 'timestamp': datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",})

                            # Add logs to redis with attempt number as key
                            add_test_run_retries_to_redis(run_id, container_retries + test_run_retries)

                            # Enqueue the test again
                            enqueue_run_request(queue_obj)
                            continue

                        # Create output based on the status
                        output = "Test run completed successfully" if status == SUCCESS_STATUS else "Test run failed"

                        # Check if the test_result is still None. It means the container is exited before the test result is updated in redis after max retries.
                        if test_result is None:
                            status = ERROR_STATUS
                            if row_number:
                                output = f"Server Error in row {row_number}. Please contact {SUPPORT_EMAIL}"
                            else:
                                output = f"Server Error. Please contact {SUPPORT_EMAIL}"

                        result = {
                            "output": output,
                            "gif_url": gif_url,
                            "trace_url": trace_url,
                            "retries": test_run_retries,
                        }

                        # Check if the status is failed, if yes then add the logs to redis with attemp number as key
                        if status == FAILED_STATUS or status == ERROR_STATUS:
                            logger.info(f"Entering the expected state {test_run_retries + container_retries}")
                            add_test_run_retries_to_redis(run_id, test_run_retries + container_retries + 1)

                        # Update the test result table
                        update_test_result_status(None, run_id, status, mode=run_mode, result=result, retries=test_run_retries, suite_run_id=suite_run_id)

                        # Update the test table
                        if status == FAILED_STATUS:
                            last_run_status = FAILED_STATUS

                            
                            # If the run mode is not triage and the suite run id is present, then add the test to the triage queue
                            if run_mode != TRIAGE_MODE and suite_run_id:
                                # Update the suite run triage status to running and increment the triage count
                                update_suite_run_status(suite_run_id, status=None, triage_count=1)

                                # Get failure data from Redis session if available
                                failure_data = test_result.get("failure_data", None)
                                if failure_data:
                                    queue_obj["failure_data"] = failure_data
                                    logger.info(f"Added failure data to triage queue for run_id {run_id}: instruction_id={failure_data.get('instruction', {}).get('id', 'unknown')}, has_image={bool(failure_data.get('image'))}")

                                # Add the test to the triage queue
                                add_test_to_queue_with_triage_mode(queue_obj)
                        
                        elif status == ERROR_STATUS :
                            last_run_status = ERROR_STATUS
                        else:
                            last_run_status = SUCCESS_STATUS if test_run_retries==0 else SUCCESS_FLAKY_STATUS
                        
                        update_test_status(test_id, last_run_status, run_mode)

                        # Extract environment name and config from queue_obj
                        environment_name = queue_obj.get('environment_name')
                        config = queue_obj.get('config', {})
                        config_string = format_config_string(config)

                        # Send message to slack
                        send_message_to_slack(
                            message = "🔄 Test Execution Complete",
                            obj = test_obj,
                            type = "test",
                            send_to_integration=False,
                            Test_Run_ID = run_id,
                            Status = status,
                            Mode = run_mode,
                            Retries = test_run_retries,
                            Environment = environment_name,
                            Config = config_string,
                            result_urls = {
                                "trace_url": trace_url
                            }
                        )

                        # Update the suite run table
                        if suite_run_id:
                            from utils.utils_test import handle_suite_run_completion
                            handle_suite_run_completion(suite_run_id, queue_obj, status, output, test_id, test_obj, environment_name, config_string, config)


                        logger.info(f"Successfully updated database for test run {run_id}")

                        # Clear logs from redis
                        clear_entry_from_redis(run_id)

                except Exception as e:
                    logger.error(f"❌ Failed to handle container {container.id}: {e}")
                    logger.debug(traceback.format_exc())

            # Check and cleanup compose containers
            self.check_and_cleanup_compose_containers()

            # Check and cleanup triage containers
            self.check_exited_triage_containers_and_cleanup()

        except Exception as e:
            logger.error(f"Failed to check and cleanup containers: {e}")
            logger.debug(traceback.format_exc())
            raise e

    def check_exited_triage_containers_and_cleanup(self):
        """
        Checks for and cleans up exited Docker containers with label mode=triage.

        This method performs ONLY the following actions:
        1. Lists all containers (including stopped ones) with label mode=triage
        2. Identifies containers in 'exited' or 'dead' state
        3. Increases the rate limit
        4. Updates the suite run triage result/status (see handle_triage_container_exit)
        5. Updates the test result status using data fetched from Redis only
        6. Removes the container
        """
        try:
            containers = self.docker_client.containers.list(all=True, filters={"label": "mode=triage"})

            for container in containers:
                try:
                    status = container.attrs["State"]["Status"]
                    if status not in ["exited", "dead"]:
                        continue

                    run_id = container.labels.get("run_id")
                    queue_obj_str = container.labels.get("queue_obj")

                    # Get the time when the container is exited
                    container_exit_time = self.get_container_exit_time(container.id)

                    # Remove the container
                    container.remove()
                    logger.info(f"✅ Removed triage container {run_id}")

                    if not queue_obj_str:
                        logger.warning(f"No queue_obj found for triage container {run_id}")
                        # Increase rate limit even if metadata is missing
                        continue

                    try:
                        queue_obj = json.loads(queue_obj_str)
                    except json.JSONDecodeError as json_err:
                        logger.error(f"Failed to parse queue_obj for triage container {run_id}: {json_err}")
                        continue

                    # Extract minimal fields
                    run_mode = queue_obj.get('run_mode', None)
                    suite_run_id = queue_obj.get('suite_run_id', None)
                    current_user = queue_obj.get('current_user', None)
                    activity_log_id = queue_obj.get('activity_log_id', None)
                    suite_run_id = queue_obj.get('suite_run_id', None)
                    test_id = queue_obj.get('test_id', None)
                    test_obj = queue_obj.get('test_obj', None)
                    test_name = test_obj.get('name', None)
                    row_number = queue_obj.get('row_number', None)
                    suite_obj = queue_obj.get('suite_obj', None)
                    config = queue_obj.get('config',{})

                    # Increase rate limit
                    run_org_id = get_org_id_for_entity(test_id=test_id, suite_obj=suite_obj)
                    test_runner.increase_rate_limit(org_id=run_org_id)

                    # Remove the org id from the current runs
                    remove_from_current_runs(run_id)

                    # Read triage result from Redis only
                    test_result = get_test_result_from_redis(run_id) or {}
                    if not test_result:
                        logger.warning(f"No test result found for triage container {run_id}")
                        continue

                    # Update the suite run db
                    result_object = {
                        "test_name": test_name,
                        "row_number": row_number,
                        "test_id": test_id,
                        "category": test_result.get('category', None),
                        "reasoning": test_result.get('reasoning', None),
                        "error_instruction": test_result.get('error_instruction', None),
                        "prompt": test_result.get('prompt', None)
                    }

                    # If test result has sub category, then add it to the result object
                    if test_result.get('sub_category', None):
                        result_object['sub_category'] = test_result.get('sub_category', None)

                    # Update suite run with triage result
                    suite_run_obj = update_suite_run_status(suite_run_id, status=None, triage_result=result_object)
                    
                    # Check if all triage tests are completed and send consolidated message
                    if suite_run_obj and suite_run_obj.get('triage_status', None) == SUITE_COMPLETED_STATUS:
                        logger.info(f"All triage tests are completed and sending consolidated message")

                        from utils.utils_slack import send_triage_findings_message
                        send_triage_findings_message(suite_run_id, suite_run_obj.get('triage_result'), queue_obj.get('suite_obj', None), send_to_integration=True)
                        logger.info(f"Sent consolidated triage findings message for suite run {suite_run_id}")

                    logger.info(f"Successfully updated suite run status for suite run {suite_run_id} with triage result {result_object}")

                    # Check if healing should be triggered
                    category = test_result.get('category', None)
                    heal_test_enabled = suite_obj.get('heal_test', False)
                    
                    # If sub_category is replace_step or re_generate_script and heal_test is enabled, enqueue for healing
                    if category in [TRIAGE_CATEGORIES['RAISE_BUG'], TRIAGE_CATEGORIES['UPDATE_SCRIPT']] and heal_test_enabled:
                        logger.info(f"Healing enabled for test {test_id}. Category: {category}. Enqueueing for healing.")
                        
                        try:
                            add_test_to_queue_with_heal_mode(queue_obj, result_object)
                        except Exception as e:
                            logger.error(f"Failed to enqueue test for healing: {str(e)}")
                            logger.debug(traceback.format_exc())

                    # Get gif_url and trace_url from redis
                    gif_url = test_result.get('gif_url', None)
                    trace_url = test_result.get('trace_url', None)

                    # Update test result status using Redis-only data
                    update_test_result_status(
                        None,
                        run_id,
                        test_result.get('status', FAILED_STATUS),
                        result={"output": "Traige agent completed the analysis", "gif_url": gif_url, "trace_url": trace_url},
                    )

                    # Get the ai_credits from redis
                    session = get_compose_session_from_redis(run_id)
                    ai_credits = session.get("ai_credits") if session else None

                    # Update executed_seconds and ai_credits in the activity log and credits table.
                    update_activity_log(current_user, log_id=activity_log_id, end_time=container_exit_time, ai_credits_consumed=ai_credits)

                    # Extract environment name and config from queue_obj
                    environment_name = queue_obj.get('environment_name')
                    config = queue_obj.get('config', {})
                    config_string = format_config_string(config)

                    # Create kwargs for send_message_to_slack
                    kwargs = {
                        "Category": test_result.get('category', None),
                        "Reasoning": test_result.get('reasoning', None),
                        "Error_Instruction": format_instruction_for_display(test_result.get('error_instruction', None)),
                        "Environment": environment_name,
                        "Config": config_string
                    }

                    if test_result.get('sub_category') is not None:
                        kwargs['Sub_Category'] = test_result.get('sub_category', None)

                    send_message_to_slack(
                            message = "Triage Agent Analysis Complete",
                            obj = test_obj,
                            type = "test",
                            send_to_integration=False,
                            Test_Run_ID = run_id,
                            Status = test_result.get('status', FAILED_STATUS),
                            Mode = run_mode,
                            result_urls = {
                                "trace_url": trace_url
                            },
                            **kwargs
                        )

                    # clear redis session
                    clear_entry_from_redis(run_id)
                    logger.info(f"✅ Cleared redis session for triage container {run_id}")

                except Exception as e:
                    logger.error(f"❌ Failed to handle triage container {run_id}: {e}")
                    logger.debug(traceback.format_exc())
                    continue

        except Exception as e:
            logger.error(f"Failed to check and cleanup triage containers: {e}")
            logger.debug(traceback.format_exc())
            raise e

    def check_exited_heal_containers_and_cleanup(self):
        """
        Checks for and cleans up exited Docker containers with label mode=heal.

        This method performs ONLY the following actions:
        1. Lists all containers (including stopped ones) with label mode=heal
        2. Identifies containers in 'exited' or 'dead' state
        3. Increases the rate limit
        4. Gets heal_results from Redis and stores in HealingSuggestion database
        5. Updates the test result status using data fetched from Redis only
        6. Removes the container
        """
        try:
            containers = self.docker_client.containers.list(all=True, filters={"label": "mode=heal"})

            for container in containers:
                try:
                    status = container.attrs["State"]["Status"]
                    if status not in ["exited", "dead"]:
                        continue

                    run_id = container.labels.get("run_id")
                    queue_obj_str = container.labels.get("queue_obj")

                    # Get the time when the container is exited
                    container_exit_time = self.get_container_exit_time(container.id)

                    # Remove the container
                    container.remove()
                    logger.info(f"✅ Removed heal container {run_id}")

                    if not queue_obj_str:
                        logger.warning(f"No queue_obj found for heal container {run_id}")
                        # Increase rate limit even if metadata is missing
                        continue

                    try:
                        queue_obj = json.loads(queue_obj_str)
                    except json.JSONDecodeError as json_err:
                        logger.error(f"Failed to parse queue_obj for heal container {run_id}: {json_err}")
                        continue

                    # Extract minimal fields
                    suite_run_id = queue_obj.get('suite_run_id', None)
                    current_user = queue_obj.get('current_user', None)
                    activity_log_id = queue_obj.get('activity_log_id', None)
                    test_id = queue_obj.get('test_id', None)
                    test_obj = queue_obj.get('test_obj', None)
                    suite_obj = queue_obj.get('suite_obj', None)
                    config = queue_obj.get('config', {})

                    # Get suite_id from suite_obj or test_obj
                    suite_id = None
                    if suite_obj:
                        suite_id = suite_obj.get('suite_id')
                    elif test_obj:
                        suite_id = test_obj.get('suite_id')

                    # Increase rate limit
                    run_org_id = get_org_id_for_entity(test_id=test_id, suite_obj=suite_obj)
                    test_runner.increase_rate_limit(org_id=run_org_id)

                    # Remove the org id from the current runs
                    remove_from_current_runs(run_id)

                    # Get session from Redis to access heal_results and triage_result
                    session = get_compose_session_from_redis(run_id)
                    if not session:
                        logger.warning(f"No session found in Redis for heal container {run_id}")
                        continue

                    # Get heal_results from session
                    heal_results = session.get('heal_results', {})
                    if not heal_results:
                        logger.warning(f"No heal_results found in Redis for heal container {run_id}")
                        continue

                    # Get triage_result from session
                    triage_result = session.get('triage_result', {})

                    # Get original failed testrun_id
                    # Note: This should be stored in queue_obj when creating heal queue
                    # For now, try to get it from queue_obj or use the run_id as fallback
                    failed_test_run_id = queue_obj.get('original_testrun_id') or queue_obj.get('failed_testrun_id') or run_id
                    
                    # Get heal_status and reasoning
                    heal_status = heal_results.get('heal_status', 'unknown')
                    reasoning = heal_results.get('reasoning', '')

                    # Get suggested_test data
                    suggested_test = heal_results.get('suggested_test', {})
                    if not suggested_test:
                        logger.warning(f"No suggested_test found in heal_results for heal container {run_id}")
                        continue

                    # Create current_test dict with only instructions from test_obj
                    current_test = {}
                    if test_obj and test_obj.get('instructions'):
                        current_test = {
                            'instructions': json.loads(test_obj.get('instructions', [])),
                            'playwright_actions': json.loads(test_obj.get('playwright_instructions', {}))
                        }

                    # Store in HealingSuggestion database
                    try:
                        from models.HealingSuggestion import HealingSuggestion
                        from app import app
                        
                        with app.app_context():
                            healing_suggestion = HealingSuggestion(
                                id=str(uuid.uuid4()),
                                suite_id=suite_id,
                                suite_run_id=suite_run_id,
                                test_id=test_id,
                                failed_test_run_id=failed_test_run_id,
                                triage_result=json.dumps(triage_result) if triage_result else None,
                                suggested_test=json.dumps(suggested_test),  # Store suggested_test directly
                                reasoning=reasoning,
                                status=heal_status,
                                current_test=json.dumps(current_test) if current_test else None
                            )
                            
                            db.session.add(healing_suggestion)
                            db.session.commit()
                            logger.info(f"✅ Stored healing suggestion in database for heal container {run_id}")
                    except Exception as e:
                        logger.error(f"Failed to store healing suggestion in database for heal container {run_id}: {e}")
                        logger.debug(traceback.format_exc())
                        try:
                            from app import app
                            with app.app_context():
                                db.session.rollback()
                        except Exception as rollback_err:
                            logger.error(f"Failed to rollback database session: {rollback_err}")

                    # Get test result from Redis
                    test_result = get_test_result_from_redis(run_id) or {}
                    
                    # Get gif_url and trace_url from redis
                    gif_url = test_result.get('gif_url', None)
                    trace_url = test_result.get('trace_url', None)

                    # Update test result status using Redis-only data
                    update_test_result_status(
                        None,
                        run_id,
                        heal_status,
                        result={"output": "Heal agent completed", "gif_url": gif_url, "trace_url": trace_url},
                    )

                    # Get the ai_credits from redis
                    ai_credits = session.get("ai_credits") if session else None

                    # Update executed_seconds and ai_credits in the activity log and credits table.
                    update_activity_log(current_user, log_id=activity_log_id, end_time=container_exit_time, ai_credits_consumed=ai_credits)

                    # clear redis session
                    clear_entry_from_redis(run_id)
                    logger.info(f"✅ Cleared redis session for heal container {run_id}")

                except Exception as e:
                    logger.error(f"❌ Failed to handle heal container {run_id}: {e}")
                    logger.debug(traceback.format_exc())
                    continue

        except Exception as e:
            logger.error(f"Failed to check and cleanup heal containers: {e}")
            logger.debug(traceback.format_exc())
            raise e

    def spin_up_docker_container(self, playwright_instructions: str, instructions: str, mode: str, run_id: str, browser: str, browserbase_session_id: str, cdp_url: str, config: dict=None, variables_dict: dict=None, blob_url: str=None, labels: dict = {}):
        """
        Creates and starts a new Docker container with the specified configuration.
        
        Args:
            playwright_instructions (str): Instructions for the Playwright container
            mode (str): The mode in which the container should run.
            run_id (str): The ID of the run.
            browser (str): The browser to use.
            browserbase_session_id (str): The ID of the browserbase session.
            cdp_url (str): The CDP URL of the browserbase session.
            config (dict): The config for the container.
            labels (dict): The labels to add to the container.
            variables_dict (dict): The variables dictionary.
            blob_url (str): Optional blob URL for large queue objects.
        Returns:
            Container: The created Docker container object
        
        This method:
        1. Constructs the command for the container
        2. Runs a new container with the specified image and configuration
        3. Returns the container object for further operations
        """
        try:
            # Construct command with arguments

            command = [
                "node", "dist/index.js",
                playwright_instructions,
                instructions,
                mode,
                run_id,
                browser,
                browserbase_session_id,
                cdp_url,
                config,
                json.dumps(variables_dict),
                blob_url or ''  # Add blob_url as 11th argument (empty string if not provided)
            ]

            # Mount docker logs to a file 
            docker_logs_dir = os.getenv("DOCKER_LOGS_DIR")
            if docker_logs_dir is None:
                logger.error("DOCKER_LOGS_DIR is not set")
                return
            
            # Create the directory if it doesn't exist
            os.makedirs(docker_logs_dir, exist_ok=True)

            # Create run-specific directory
            host_log_dir = os.path.abspath(os.path.join(docker_logs_dir, run_id))
            os.makedirs(host_log_dir, exist_ok=True)

            # Container log file path (app.log inside /app/logs/)
            container_log_file_path = "/app/logs"

            # Expose port 8080 for websocket server if in compose mode
            ports = {}
            if mode == "compose":
                # Map container port 8080 to host port 8080
                # Note: Only one compose session can run at a time with this setup
                # For multiple sessions, you'd need dynamic port allocation
                ports['8080/tcp'] = 8080
            
            # Extract agent_type from labels and add as environment variable
            environment_vars = {}
            if labels.get("agent_type"):
                environment_vars["AGENT_TYPE"] = labels.get("agent_type")

            container = self.docker_client.containers.run(
                image=LITMUS_TEST_RUNNER_IMAGE,
                command=command,
                labels={"mode": mode, "run_id": run_id, **labels},
                environment=environment_vars,
                network=LITMUS_TEST_RUNNER_NETWORK_NAME,
                detach=True,  # Run container in detached mode (background)
                ports=ports if ports else None,
                volumes={
                    host_log_dir: {
                        "bind": container_log_file_path,
                        "mode": "rw"
                    }
                }
            )

            return container

        except Exception as e:
            logger.error(f"Failed to spin up Docker container: {e}")
            logger.debug(traceback.format_exc())
            raise e

    def kill_container_with_label(self, labels: dict):
        """
        Kills all containers matching the given labels.
        
        Args:
            labels (dict): Dictionary of labels to filter containers by.
        
        Example:
            labels = {"mode": "compose", "run_id": "abc123"}
        """
        try:
            # List all containers with the specified label
            containers = self.docker_client.containers.list(all=True, filters={"label": [f"{k}={v}" for k, v in labels.items()]})
            logger.info(f"Found {len(containers)} containers with label {labels}")
            for container in containers:
                try:
                    # Check if container is already being removed or doesn't exist
                    try:
                        logger.info(f"Reloading container {container.id}")
                        container.reload()  # Refresh container state
                        logger.info(f"Container {container.id} reloaded")
                    except docker.errors.NotFound:
                        logger.info(f"Container {container.id} no longer exists, skipping")
                        continue
                    
                    # Check if container is already in removal state
                    if container.attrs["State"]["Status"] in ["removing", "dead"]:
                        logger.info(f"Container {container.id} is already being removed or dead, skipping")
                        continue
                    # Kill the container directly
                    if container.attrs["State"]["Status"] == "running":
                        logger.info(f"Killing container {container.id}")
                        container.kill()
                        logger.info(f"✅ Killed container {container.id}")
                    
                    # Remove the container
                    logger.info(f"Removing container {container.id}")
                    container.remove()
                    logger.info(f"✅ Removed container {container.id}")

                except APIError as e:
                    if e.response is not None and e.response.status_code == 409:
                        logger.info(f"Container {container.id} is already being removed or dead, skipping")
                        continue
                except Exception as e:
                    logger.error(f"❌ Failed to kill and remove container {container.id}: {e}")
                    logger.debug(traceback.format_exc())
                    raise e

        except Exception as e:
            logger.error(f"Failed to kill containers with label {labels}: {e}")
            logger.debug(traceback.format_exc())
            raise e

    def setup_redis_and_network(
        self,
        redis_container_name='redis',
        redis_image='redis:latest',
        network_name='my-shared-network'
    ):
        """
        Sets up a Redis container and Docker network for inter-container communication.
        
        Args:
            redis_container_name (str): Name for the Redis container. Defaults to 'redis'.
            redis_image (str): Redis Docker image to use. Defaults to 'redis:latest'.
            network_name (str): Name for the Docker network. Defaults to 'my-shared-network'.
            
        Returns:
            tuple: (redis_container, network) The created/retrieved Redis container and network objects.
            
        This method:
        1. Creates or retrieves a Docker network
        2. Creates or retrieves a Redis container
        3. Ensures the Redis container is running
        4. Connects the Redis container to the network if not already connected
        """
        try:
            # Step 1: Ensure network exists
            try:
                network = self.docker_client.networks.get(network_name)
                logger.info(f"Network '{network_name}' already exists.")
            except docker.errors.NotFound:
                network = self.docker_client.networks.create(network_name, driver="bridge")
                logger.info(f"Network '{network_name}' created.")

            # Step 2: Check if Redis container exists
            try:
                redis_container = self.docker_client.containers.get(redis_container_name)
                logger.info(f"Redis container '{redis_container_name}' already exists.")
                
                # Start it if it's not running
                if redis_container.status != 'running':
                    redis_container.start()
                    logger.info(f"Redis container '{redis_container_name}' started.")
            except docker.errors.NotFound:
                # Create Redis container if not found
                redis_container = self.docker_client.containers.run(
                    redis_image,
                    name=redis_container_name,
                    network=network_name,
                    detach=True,
                    restart_policy={"Name": "always"},
                )
                logger.info(f"Redis container '{redis_container_name}' created and started.")

            # Step 3: Attach Redis to the network if it's not connected
            network.reload()
            connected_containers = [c.id for c in network.containers]
            if redis_container.id not in connected_containers:
                network.connect(redis_container)
                logger.info(f"Redis container '{redis_container_name}' connected to network '{network_name}'.")

            return redis_container, network

        except Exception as e:
            logger.error(f"Failed to setup Redis and network: {e}")
            raise

    def check_if_docker_container_is_running(self, labels: dict):
        """
        Checks if a Docker container with the specified label is running.
        Args:
            labels (dict): The labels to filter containers by.
        """
        try:
            # List all containers with the specified label
            containers = self.docker_client.containers.list(all=True, filters={"label": [f"{k}={v}" for k, v in labels.items()]})

            # Check the state of the container
            for container in containers:
                if container.attrs["State"]["Status"] == "running":
                    return True

            return False

        except Exception as e:
            logger.error(f"Failed to check if Docker container is running: {e}")
            logger.debug(traceback.format_exc())
            return False
        
    def get_container_exit_time(self, container_id: str) -> datetime | None:
        """
        Get the exit time of a Docker container.
        Args:
            container_id (str): The ID of the container.
        Returns:
            datetime: The exit time of the container.
        """
        try:
            container = self.docker_client.containers.get(container_id)
            # Step 1: Extract and parse FinishedAt from Docker
            finished_at_str = container.attrs["State"]["FinishedAt"]

            # Strip 'Z' and any fractional seconds
            if '.' in finished_at_str:
                finished_at_str = finished_at_str.split('.')[0]
            elif 'Z' in finished_at_str:
                finished_at_str = finished_at_str.rstrip('Z')

            # Parse the timestamp (up to seconds only)
            dt = datetime.strptime(finished_at_str, "%Y-%m-%dT%H:%M:%S")
            return dt.replace(tzinfo=timezone.utc)
        except Exception as e:
            logger.error(f"Failed to get container exit time: {e}")
            logger.debug(traceback.format_exc())
            return None
        
    def container_is_crashed(self, labels: dict) -> tuple[str, datetime]:
        """
        Checks if a Docker container with the specified label is crashed.
        Args:
            labels (dict): The labels to filter containers by.
        Returns:
            tuple: (container_id, exit_time) The container id and the exit time of the container.
        """
        try:
            # List the container and check if it exited
            containers = self.docker_client.containers.list(all=True, filters={"label": [f"{k}={v}" for k, v in labels.items()]})
            for container in containers:
                if container.attrs["State"]["Status"] in ["exited", "dead"]:
                    exit_time = self.get_container_exit_time(container.id)
                    container.remove()         # Remove the container
                    return container.id, exit_time
            return None, None
        except Exception as e:
            logger.error(f"Failed to check if Docker container is crashed: {e}")
            logger.debug(traceback.format_exc())
            return None, False