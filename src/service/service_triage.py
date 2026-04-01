import uuid
import traceback
from log_config.logger import logger
from service.service_queue import enqueue_run_request
from utils.utils_constants import TRIAGE_MODE, QUEUED_STATUS, SUITE_COMPLETED_STATUS
from utils.utils_test import update_test_result_status
from service.service_redis import add_log_to_redis, set_compose_session_in_redis
from service.service_credits import check_if_user_has_enough_credits, check_if_user_has_enough_ai_credits
from service.service_test import update_suite_run_status

def add_test_to_queue_with_triage_mode(queue_obj):
    """
    Add a test to the triage queue.
    """
    try:
        suite_obj = queue_obj.get('suite_obj', None)
        suite_id = suite_obj.get('suite_id', None)
        from app import app
        with app.app_context():

            # Check if the user has enough browser minutes and AI credits
            browser_response, browser_minutes_status_code = check_if_user_has_enough_credits(suite_id=suite_id)
            ai_response, ai_credits_status_code = check_if_user_has_enough_ai_credits(suite_id=suite_id)
        
        # Add credits exhausted message to triage result in suite run
        if browser_minutes_status_code != 200 or ai_credits_status_code != 200:
            reasoning = ""
            if browser_minutes_status_code != 200:
                reasoning += browser_response.get('error', 'Your organization has no browser minutes left.')
            elif ai_credits_status_code != 200:
                reasoning += ai_response.get('error', 'Your organization has no AI credits left.')

            test_obj = queue_obj.get('test_obj', None)
            # Create a triage result object
            result_object = {
                "test_name": test_obj.get('name', None),
                "row_number": queue_obj.get('row_number', None),
                "test_id": queue_obj.get('test_id', None),
                "category": "Error",
                "reasoning": reasoning,
                "error_instruction": None
            }


            update_suite_run_status(queue_obj["suite_run_id"], status=None, triage_result=result_object)
            return
        # Change the mode to triage
        queue_obj["run_mode"] = TRIAGE_MODE
        queue_obj["testrun_id"] = str(uuid.uuid4())
        logger.info(f"Test {queue_obj['test_id']} added to triage queue with mode {TRIAGE_MODE} and testrun_id {queue_obj['testrun_id']}")

        first_run_failure_data = queue_obj.get("failure_data", None)
        queue_obj.pop("failure_data", None)

        # Add log to redis
        add_log_to_redis(queue_obj["testrun_id"], {"info": f"Test run queued with triage mode"})

        # Enqueue the test run request
        enqueue_run_request(queue_obj)

        # Get req values from queue_obj
        suite_run_id = queue_obj.get("suite_run_id", None)
        row_number = queue_obj.get("row_number", None)
        environment_variables = queue_obj.get("global_variables_dict", {}).get("environment_variables", {})
        config = queue_obj.get("config", {})

        # update test result status to queued
        update_test_result_status(queue_obj["test_id"], queue_obj["testrun_id"], QUEUED_STATUS, mode=TRIAGE_MODE, suite_run_id=suite_run_id, data_row_index=row_number, environment_variables=environment_variables, config=config)

        # Store failure data in Redis for triage mode to access
        if first_run_failure_data:
            try:
                # Create a session object with the failure data
                session_data = {
                    "test_result": {
                        "failure_data": first_run_failure_data
                    }
                }
                set_compose_session_in_redis(queue_obj["testrun_id"], session_data)
                logger.info(f"Stored failure data in Redis for triage run {queue_obj['testrun_id']}: instruction_id={first_run_failure_data.get('instruction', {}).get('id', 'unknown')}, has_image={bool(first_run_failure_data.get('image', None))}")
            except Exception as e:
                logger.error(f"Failed to store failure data in Redis for triage run {queue_obj['testrun_id']}: {str(e)}")
                logger.debug(traceback.format_exc())

        logger.info(f"Triage Test {queue_obj['test_id']} added to triage queue {queue_obj}")

    except Exception as e:
        logger.error(f"Error adding test to triage queue: {str(e)}")
        logger.debug(traceback.format_exc())
        raise e