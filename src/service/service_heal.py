import uuid
import json
import traceback
from log_config.logger import logger
from service.service_queue import enqueue_run_request
from utils.utils_constants import HEAL_MODE, QUEUED_STATUS
from utils.utils_test import update_test_result_status
from service.service_redis import add_log_to_redis, set_compose_session_in_redis
from service.service_credits import check_if_user_has_enough_credits, check_if_user_has_enough_ai_credits, update_credits
from service.service_test import get_org_for_suite
from service.service_test_segment import check_if_the_test_has_segment

def add_test_to_queue_with_heal_mode(queue_obj, triage_result):
    """
    Add a test to the heal queue.
    
    Args:
        queue_obj: The queue object containing test information
        triage_result: The triage result object containing category, reasoning, etc.
    """
    try:
        suite_obj = queue_obj.get('suite_obj', None)
        suite_id = suite_obj.get('suite_id', None) if suite_obj else None
        
        # If suite_id is not in suite_obj, try to get it from test_obj
        if not suite_id:
            test_obj = queue_obj.get('test_obj', None)
            if test_obj:
                suite_id = test_obj.get('suite_id', None)
        
        from app import app
        with app.app_context():
            # Check if the user has enough browser minutes and AI credits
            browser_response, browser_minutes_status_code = check_if_user_has_enough_credits(suite_id=suite_id)
            ai_response, ai_credits_status_code = check_if_user_has_enough_ai_credits(suite_id=suite_id)
        
        # Add credits exhausted message to heal result
        if browser_minutes_status_code != 200 or ai_credits_status_code != 200:
            reasoning = ""
            if browser_minutes_status_code != 200:
                reasoning += browser_response.get('error', 'Your organization has no browser minutes left.')
            elif ai_credits_status_code != 200:
                reasoning += ai_response.get('error', 'Your organization has no AI credits left.')

            logger.warning(f"Credits exhausted for heal mode. Test {queue_obj.get('test_id')} will not be queued for healing.")
            logger.info(f"Browser minutes status: {browser_minutes_status_code}, AI credits status: {ai_credits_status_code}")
            return

        # TODO: Get blob_url if present (for large queue objects)
        # blob_url = queue_obj.get('blob_url', None)
        # if blob_url:
        #     logger.info(f"Blob URL found for test {queue_obj.get('test_id')}, downloading from blob storage: {blob_url}")
        #     try:
        #         from utils.util_blob import download_queue_obj_from_blob
        #         queue_obj = download_queue_obj_from_blob(blob_url)
        #     except Exception as e:
        #         logger.error(f"Error downloading queue object from blob storage: {str(e)}")
        #         logger.debug(traceback.format_exc())
        #         return
        
        # Check if the test is a segment (has segment_id in args) - before enqueueing
        instructions = json.loads(queue_obj.get('test_obj', {}).get('instructions', []))
        has_segment, status_code = check_if_the_test_has_segment(instructions)
        if status_code != 200:
            logger.warning(f"Test {queue_obj.get('test_id')} has a segment, will not be queued for healing.")
            return
        # Create a new queue_obj for healing
        heal_queue_obj = queue_obj.copy()
        
        # Update mode to heal
        heal_queue_obj['run_mode'] = HEAL_MODE
        
        # Generate new testrun_id for healing
        heal_queue_obj['testrun_id'] = str(uuid.uuid4())
        
        # Remove failure_data if present (not needed for healing)
        heal_queue_obj.pop('failure_data', None)
        
        # Reset retries for healing run
        heal_queue_obj['container_retries'] = 0
        heal_queue_obj['test_run_retries'] = 0
        
        # Store triage_result in Redis for heal mode to access
        if triage_result:
            try:
                # Create a session object with the triage_result
                session_data = {
                    "triage_result": triage_result,
                }
                set_compose_session_in_redis(heal_queue_obj['testrun_id'], session_data)
                logger.info(f"Stored triage_result in Redis for heal run {heal_queue_obj['testrun_id']}: sub_category={triage_result.get('sub_category', 'unknown')}")
            except Exception as e:
                logger.error(f"Failed to store triage_result in Redis for heal run {heal_queue_obj['testrun_id']}: {str(e)}")
                logger.debug(traceback.format_exc())

        # Add log to redis
        add_log_to_redis(heal_queue_obj['testrun_id'], {"info": f"Test run queued with healing mode"})
        
        # Enqueue the healing request
        enqueue_run_request(heal_queue_obj)
        logger.info(f"Test {queue_obj.get('test_id')} added to healing queue with mode {HEAL_MODE} and testrun_id {heal_queue_obj['testrun_id']}")
        
        # Get req values from queue_obj
        suite_run_id = queue_obj.get("suite_run_id", None)
        row_number = queue_obj.get("row_number", None)
        environment_variables = queue_obj.get("global_variables_dict", {}).get("environment_variables", {})
        config = queue_obj.get("config", {})
        
        # Update test result status to queued for healing
        update_test_result_status(
            queue_obj.get("test_id"),
            heal_queue_obj['testrun_id'],
            QUEUED_STATUS,
            mode=HEAL_MODE,
            suite_run_id=suite_run_id,
            data_row_index=row_number,
            environment_variables=environment_variables,
            config=config
        )
        
        logger.info(f"Heal Test {queue_obj.get('test_id')} added to heal queue with testrun_id {heal_queue_obj['testrun_id']}")

    except Exception as e:
        logger.error(f"Error adding test to heal queue: {str(e)}")
        logger.debug(traceback.format_exc())
        raise e

