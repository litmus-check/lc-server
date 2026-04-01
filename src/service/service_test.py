import csv
import os
import re
import uuid
import json
import copy
import threading
import traceback
from flask import jsonify
from utils.utils_constants import *
from database import db
from service.service_activity_log import *
from utils.utils_slack import send_message_to_slack
from service.service_queue import enqueue_run_request
from utils.utils_suite import get_suite_data
from utils.utils_test import *
from models.Test import Test
from models.TestResult import TestResult
from log_config.logger import logger
from sqlalchemy.orm import joinedload
from browserbase import RateLimitError
from service.service_file_upload import *
from utils.utils_instruction_validations import validate_instructions
from datetime import datetime, timezone
from utils.utils_pom import *
from service.service_test_segment import *
from service.service_suite import get_suite_file_implementation
from utils.utils_test_data import *
from utils.utils_playwright_config import get_config_from_request, format_config_string
from service.service_environment import *
from utils.utils_tags import *
from access_control.roles import ADMIN
from service.service_credits import check_if_user_has_enough_credits
from utils.util_blob import upload_json_blob

from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv("app.env"))

def validate_description_word_limit(description):
    """
    Validate description word limit (200 words max).
    
    Args:
        description (str): The description text to validate
        
    Returns:
        tuple: (error_message, status_code) or (None, 200) if validation passes
    """
    if description is None:
        return None, 200
    
    # Count words by splitting on whitespace
    word_count = len(description.split())
    if word_count > 200:
        return f"Description exceeds 200 word limit. Current word count: {word_count}", 400
    
    return None, 200

def validate_test_data_file(request_data):
    """
    Validate test data file for create and update test operations.
    
    Args:
        request_data (dict): The request data containing file information
        
    Returns:
        tuple: (error_message, status_code) or (None, 200) if validation passes
    """
    if request_data.get("has_test_data", False):
        file_id = request_data.get("file_id")
        if not file_id:
            return "File id is required to create a test with test data", 400
        file_obj = File.query.filter_by(file_id=file_id).first()
        if not file_obj:
            return "File with id " + file_id + " not found", 404
        file_url = file_obj.file_url
        if not file_url:
            return "File not found", 404
        
        file_name = file_obj.file_name
        # Check the extension and accept only csv
        if not file_name.endswith('.csv'):
            return "Only csv files are supported", 400
    
    return None, 200

def run_test_implementation(current_user, id, browser, run_mode, request_data=None):
    logger.info("Running test implementation called")
    try:
        # Fetch test object
        test_obj = return_test_obj(current_user, id)
        if not test_obj:
            return {
                "error": f"Test with id {id} not found or user does not have access to it"
            }, 404

        # Check AI credits for test instructions
        test_obj_dict = test_obj.serialize()
        instructions = test_obj_dict.get('instructions', [])
        if instructions:
            # Parse instructions if they're JSON string
            if isinstance(instructions, str):
                instructions = json.loads(instructions)
            
            error_response, status_code = check_ai_credits_for_test(current_user, instructions)
            if status_code != 200:
                return error_response, status_code
        # Check if the org that owns the test has enough credits
        logger.info(f"Checking if Organization for test {id} has enough credits")
        credits_check_resp, status_code = check_if_user_has_enough_credits(suite_id=test_obj.suite_id)
        if status_code != 200:
            return credits_check_resp, status_code

        # Check if the test has test data. Create testruns for each row in the test data
        if test_obj.has_test_data:
            response, status_code = handle_test_data(current_user, browser, run_mode, request_data, test_obj)
            return response, status_code

        response, status_code = handle_non_test_data(current_user, browser, run_mode, request_data, test_obj)
        return response, status_code

    except Exception as e:
        logger.error("Unable to run test, " + str(e))
        logger.debug(traceback.format_exc())
        raise e

def create_test_implementation(current_user, request_data):
    logger.info("Creating agent implementation called")
    try:
        logger.info(f" Current user: {current_user}")
        # check if suite_id is valid
        if current_user['role'] == ADMIN:
            suite_obj = Suite.query.filter_by(suite_id=request_data.get('suite_id')).first()
        else:
            suite_obj = Suite.query.filter_by(suite_id=request_data.get('suite_id'), org_id=current_user['org_id']).first()
        if not suite_obj:
            return {
                "error": f"Suite with id {request_data.get('suite_id')} not found or user does not have access to it"
            }, 404
        
        # Validate test data file if present
        error_message, status_code = validate_test_data_file(request_data)
        if status_code != 200:
            return {"message": error_message}, status_code
        
        # Validate description word limit if present
        description = request_data.get('description')
        error_message, status_code = validate_description_word_limit(description)
        if status_code != 200:
            return {"error": error_message}, status_code
        
        instructions = request_data.get('instructions')
        if not instructions or not isinstance(instructions, list) or len(instructions) == 0:
            test_status = TEST_STATUS_BLANK
        else:
            test_status = TEST_STATUS_DRAFT

        if instructions:
            # Add IDs to instructions while preserving their structure
            for idx, instruction in enumerate(instructions):
                instruction['id'] = idx

            # Validate instructions if provided, validate actions, args and type
            is_valid, error = validate_instructions(current_user, instructions)
            if not is_valid:
                return {
                    "error": error
                }, 400

        # Validate custom_test_id uniqueness within suite if provided
        custom_test_id = request_data.get('custom_test_id')
        suite_id = request_data.get('suite_id')
        if custom_test_id and suite_id:
            existing = Test.query.filter_by(
                custom_test_id=custom_test_id,
                suite_id=suite_id
            ).first()
            if existing:
                return {
                    "error": f"Test with custom_test_id '{custom_test_id}' already exists in this suite"
                }, 400

        test_obj = Test(
            id=str(uuid.uuid4()),
            name=request_data.get('name'),
            description=request_data.get('description'),
            goal=request_data.get('goal'),
            suite_id=request_data.get('suite_id'),
            instructions=json.dumps(instructions),
            status=test_status,
            custom_test_id=custom_test_id,
        )

        db.session.add(test_obj)
        db.session.commit()

        # Send message to slack
        send_message_to_slack(
            message="Test Created With Instructions",
            obj=test_obj.serialize(),
            type='test',
            send_to_integration=False,
            Test_Status=test_obj.status,
        )

        request_data['id'] = test_obj.id
        request_data['status'] = test_obj.status
        return request_data, 200
        
    except Exception as e:
        logger.error("Unable to create test: " + str(e))
        logger.debug(traceback.format_exc())
        raise e

def update_test_implementation(current_user, request_data, test_id):
    logger.info("Updating test implementation called")
    try:
        test_obj = return_test_obj(current_user, test_id)
        if not test_obj:
            return {
                "error": f"Test with id {test_id} not found or user does not have access to it"
            }, 404

        # Validate test data file if present
        error_message, status_code = validate_test_data_file(request_data)
        if status_code != 200:
            return {"message": error_message}, status_code

        # Validate description word limit if present
        description = request_data.get('description')
        error_message, status_code = validate_description_word_limit(description)
        if status_code != 200:
            return {"error": error_message}, status_code

        if 'playwright_instructions' not in request_data:
            # Serialize the test object
            test_obj_dict = test_obj.serialize()
            playwright_instructions = json.loads(test_obj_dict.get('playwright_instructions')) if test_obj_dict.get('playwright_instructions') else None
        else:
            playwright_instructions = request_data.get('playwright_instructions')
        
            
        instructions = request_data.get('instructions', None)

        if instructions and not isinstance(instructions, list):
            return {
                "error": "Instructions should be list of strings"
            }, 400
        
        if instructions:

            # Validate instructions if provided, validate actions, args and type
            is_valid, error = validate_instructions(current_user, instructions)
            if not is_valid:
                return {
                    "error": error
                }, 400
            
            # Update instructions in db
            test_obj.instructions = json.dumps(instructions)
        

        if playwright_instructions:
            if not isinstance(playwright_instructions, dict):
                return {
                    "error": "Playwright_instructions should be a JSON object"
                }, 400

            if instructions is None:
                instructions = test_obj.instructions

            # Here instructions are natural language instructions - instructions are str when fetched from db and list when fetched from request
            instructions_list = json.loads(instructions) if isinstance(instructions, str) else instructions
            valid = validate_playwright_instructions_against_instructions(playwright_instructions, instructions_list)
            if not valid:
                return {
                    "error": "Invalid playwright instructions, cannot update test"
                }, 400
            
        # Update test object only if the field is provided
        if request_data.get('suite_id'):
            test_obj.suite_id = request_data.get('suite_id')
        if request_data.get('name'):
            test_obj.name = request_data.get('name')
        if request_data.get('description') is not None:
            test_obj.description = request_data.get('description')
        if request_data.get('goal'):
            test_obj.goal = request_data.get('goal')
        if request_data.get('status'):
            if request_data.get('status') == TEST_STATUS_DRAFT:
                test_obj.status = TEST_STATUS_DRAFT
            elif request_data.get('status') == TEST_STATUS_READY:
                test_obj.status = TEST_STATUS_READY
            else:
                return {
                    "error": "Invalid status"
                }, 400

        # Update custom_test_id if provided, enforcing uniqueness within suite
        if 'custom_test_id' in request_data:
            new_custom_test_id = request_data.get('custom_test_id')
            if new_custom_test_id:
                # Check uniqueness within the same suite
                existing = Test.query.filter(
                    Test.custom_test_id == new_custom_test_id,
                    Test.suite_id == test_obj.suite_id,
                    Test.id != test_obj.id
                ).first()
                if existing:
                    return {
                        "error": f"Test with custom_test_id '{new_custom_test_id}' already exists in this suite"
                    }, 400
                test_obj.custom_test_id = new_custom_test_id
            else:
                # Allow clearing the custom_test_id by sending null/empty
                test_obj.custom_test_id = None

        if 'has_test_data' in request_data:
            test_obj.has_test_data = request_data.get('has_test_data')
            if 'file_id' in request_data:
                test_obj.file_id = request_data.get('file_id')

        # Validate and update tags if provided
        if 'tags' in request_data:
            tags = request_data.get('tags')
            error_message, status_code = validate_tags(tags)
            if status_code != 200:
                return {"error": error_message}, status_code
            
            test_obj.tags = json.dumps(tags)

            # Update suite tags by adding new tags to the master set
            current_suite_id = test_obj.suite_id
            if current_suite_id:
                from utils.utils_tags import update_suite_tags_with_new_tags
                update_suite_tags_with_new_tags(current_suite_id, tags)

        test_obj.modified_at = db.func.now()
        
        # Update playwright instructions in db
        test_obj.playwright_instructions = json.dumps(playwright_instructions) if playwright_instructions else None
        
        db.session.commit()

        request_data['id'] = test_obj.id

        # Send message to slack
        send_message_to_slack(
            message="Test Updated",
            obj=test_obj.serialize(),
            type='test',
            send_to_integration=False
        )

        return test_obj.serialize(), 200
        
    except Exception as e:
        logger.error("Unable to update test, " + str(e))
        logger.debug(traceback.format_exc())
        raise e
    
def delete_test_implementation(current_user, test_id):
    logger.info("Deleting test implementation called")
    try:
        # Fetch test object and get instructions
        test_obj = return_test_obj(current_user, test_id)
        if not test_obj:
            return {
                "error": f"Test with id {test_id} not found or user does not have access to it"
            }, 404
        
        db.session.delete(test_obj)
        db.session.commit()

        # Send message to slack
        send_message_to_slack(
            message="Test Deleted",
            obj=test_obj.serialize(),
            type='test',
            send_to_integration=False,
            no_url=True # This is a test deletion, no URL to send
        )

        return {"message": "Test deleted successfully"}, 200
        
    except Exception as e:
        logger.error("Unable to delete test, " + str(e))
        logger.debug(traceback.format_exc())
        raise e
    
def get_test_by_id_implementation(current_user, test_id):
    logger.info(f"Getting test implementation called for test_id: {test_id}")
    try:
        # Fetch test object and get instructions
        test_obj = return_test_obj(current_user, test_id)
        if not test_obj:
            return {
                "error": f"Test with id {test_id} not found or user does not have access to it"
            }, 404
        
        response = test_obj.serialize()
        response['suite_name'] = test_obj.suite.name

        # Parse playwright instructions without modifying the database object
        playwright_instructions = None
        if test_obj.playwright_instructions:
            try:
                playwright_instructions = json.loads(response.get('playwright_instructions'))
            except:
                playwright_instructions = None

        # Pop playwright instructions from response
        response.pop('playwright_instructions', None)

        # Check if the test has file_upload action. If yes, add file_name to the args
        for instruction in response['instructions']:
            if 'type' in instruction and instruction['type'] == TEST_SEGMENT:
                # Get test segment from db
                source_test_id = [arg['value'] for arg in instruction['args'] if arg['key'] == 'source_test_id'][0]
                source_test_obj = return_test_obj(current_user, source_test_id)
                test_name = "not_available"
                if source_test_obj and source_test_obj.suite_id == test_obj.suite_id:
                    test_name = source_test_obj.name

                # Check if test_name is already present in the args. If yes, then update the value.
                test_name_present = False
                for arg in instruction['args']:
                    if arg['key'] == 'test_name':
                        arg['value'] = test_name
                        test_name_present = True
                        break
                
                if not test_name_present:
                    # Append test_name to the arg
                    instruction['args'].append({
                        "key": "test_name",
                        "value": test_name
                    })

                # Check if the segment_name is already present in the args. If yes, then update the value. Check if segment_id is present in the args.
                segment_arg = [arg['value'] for arg in instruction['args'] if arg['key'] == 'segment_id']
                if segment_arg:
                    segment_id = segment_arg[0]
                    segment_name = "not_available"
                    segment_obj = return_test_segment_obj(current_user, segment_id)
                    if segment_obj and segment_obj.suite_id == test_obj.suite_id:
                        segment_name = segment_obj.segment_name

                    # Check if segment_name is already present in the args. If yes, then update the value.
                    segment_name_present = False
                    for arg in instruction['args']:
                        if arg['key'] == 'segment_name':
                            arg['value'] = segment_name
                            segment_name_present = True
                            break
                    
                    if not segment_name_present:
                        # Append segment_name to the arg
                        instruction['args'].append({
                            "key": "segment_name",
                            "value": segment_name
                        })
                

            if 'action' in instruction and instruction['action'] == AI_FILE_UPLOAD:
                # Get file object from db
                file_id = [arg['value'] for arg in instruction['args'] if arg['key'] == 'file_id'][0]  # Get file_id from the args
                suite_id = test_obj.suite_id
                file_obj, status_code = get_suite_file_implementation(current_user, suite_id, file_id)
                file_name = "not_available"
                if status_code == 200:
                    file_name = file_obj.get('file_name')
                
                # Check if file_name is already present in the args. If yes, then update the value.
                file_name_present = False
                for arg in instruction['args']:
                    if arg['key'] == 'file_name':
                        arg['value'] = file_name
                        file_name_present = True
                        break
                
                if not file_name_present:
                    # Append file_name to the arg
                    instruction['args'].append({
                        "key": "file_name",
                        "value": file_name
                    })

        # Combine instructions and playwright instructions
        response['instructions'] = combine_ins_playwright_ins(response['instructions'], playwright_instructions)
        return response, 200
        
    except Exception as e:
        logger.error("Unable to get test, " + str(e))
        logger.debug(traceback.format_exc())
        raise e
    
def get_all_tests_implementation(current_user, page, per_page):
    logger.info("Getting all tests implementation called")
    try:
        if current_user['role'] == ADMIN:
            tests = Test.query.paginate(page=int(page), per_page=int(per_page), error_out=False)
        else:
            tests = (
                Test.query
                .join(Suite, Test.suite_id == Suite.suite_id)
                .filter(Suite.org_id == current_user.get('org_id'))
                .paginate(page=int(page), per_page=int(per_page), error_out=False)
            )

        response = {}

        response["tests"] = []
        for test in tests.items:
            # remove playwright instructions from test object
            test = test.serialize()
            test.pop('playwright_instructions', None)
            response['tests'].append(test)
            
        response['metadata'] = {
            "total_records": tests.total,
            "page_number": tests.page,
            "page_size": tests.per_page,
            "total_pages": tests.pages
        }
        return response, 200
        
    except Exception as e:
        logger.error("Unable to get tests, " + str(e))
        logger.debug(traceback.format_exc())
        raise e
    

def add_playwright_ins_in_db(test_id, playwright_instructions):
    logger.info(f"Starting to add playwright instructions for test {test_id}")
    try:
        from app import app
        logger.info("Creating app context")
        with app.app_context():
            logger.info(f"Querying for test {test_id}")
            test_obj = Test.query.filter_by(id=test_id).first()
            if not test_obj:
                logger.error(f"Test with id {test_id} not found, unable to add playwright instructions")
                return False
            
            logger.info(f"Found test object, attempting to save playwright instructions")
            test_obj.playwright_instructions = json.dumps(playwright_instructions)
            logger.info("Committing to database")
            db.session.commit()
            logger.info("Playwright instructions added successfully")
            return True
        
    except Exception as e:
        logger.error(f"Unable to add playwright instructions: {str(e)}")
        logger.debug(traceback.format_exc())
        # Try to rollback any failed transaction
        try:
            db.session.rollback()
            logger.info("Rolled back failed transaction")
        except Exception as rollback_error:
            logger.error(f"Failed to rollback transaction: {str(rollback_error)}")
        return False
    
def return_test_obj(current_user: dict, test_id: str) -> Test | None:
    try:
        # Add lazy loading for suite
        test_obj = Test.query.filter_by(id=test_id).options(joinedload(Test.suite)).first()
        if current_user['role'] != ADMIN and test_obj.suite.org_id != current_user['org_id']:
            return None
        return test_obj
    except Exception as e:
        logger.error("Unable to return role based test, " + str(e))
        logger.debug(traceback.format_exc())
        return None
    
def run_test_implementation_helper(queue_test_obj: dict, rate_limit_lock: threading.Lock):
    try:
        test_id = queue_test_obj['test_id']
        testrun_id = queue_test_obj['testrun_id']
        test_obj = queue_test_obj['test_obj']
        suite_run_id = queue_test_obj.get('suite_run_id', None)
        suite_obj = queue_test_obj.get('suite_obj', None)
        browser = queue_test_obj.get('browser', DEFAULT_BROWSER)
        run_mode = queue_test_obj.get('run_mode')
        current_user = queue_test_obj.get('current_user', None)
        trigger = queue_test_obj.get('trigger', MANUAL_TRIGGER)        # This is key is added only in suite run queue object. For test run, it is not added as default is manual
        config = queue_test_obj.get('config', DEFAULT_PLAYWRIGHT_CONFIG)
        global_variables_dict = queue_test_obj.get('global_variables_dict', None)
        environment_name = queue_test_obj.get('environment_name', None)

        # Create config string to send to slack
        config_string = format_config_string(config)

        # If browser is browserbase then we need to get the cdp url
        session = None
        if browser == REMOTE_BROWSER_BASE:
            try:
                session = get_browserbase_session(timeout=BROWSERBASE_SESSION_TIMEOUT, config=config)
            except RateLimitError as e:
                logger.error("Unable to get browserbase session, " + str(e))
                logger.debug(traceback.format_exc())
                logger.info("Rate limit error, adding test to queue")
                enqueue_run_request(queue_test_obj)                          # Enqueue the test run request to run again after rate limit is over
                raise e
            except Exception as e:
                logger.error("Unable to get browserbase session, " + str(e))
                logger.debug(traceback.format_exc())
                raise e

        # Check if the test run is part of suite run
        if suite_run_id:
            with rate_limit_lock:
                # Check if this is the first test in the suite run
                all_tests_completed, test_count, suite_run_obj = check_number_of_tests_ran(suite_run_id)
                if test_count == 0 and suite_run_obj and suite_run_obj.status == QUEUED_STATUS:
                    # Update suite run status to running in db
                    update_suite_run_status(suite_run_id, RUNNING_STATUS, environment_variables=global_variables_dict.get('environment_variables', {}), environment_name=environment_name)

                    # Get tag_filter from suite_run_obj and flatten it
                    tag_filter = json.loads(suite_run_obj.tag_filter) if suite_run_obj.tag_filter else {}
                    tag_filter_kwargs = {}
                    if tag_filter:
                        tag_filter_kwargs['Tag Filter Condition'] = tag_filter.get('condition', '')
                        tag_filter_kwargs['Tag Filter Tags'] = json.dumps(tag_filter.get('tags', []))

                    # Send message to slack
                    send_message_to_slack(
                        message="Suite Execution Started",
                        obj=suite_obj,
                        type='suite',
                        send_to_integration=True,
                        Suite_Run_ID = suite_run_id,
                        Environment = environment_name,
                        Config = config_string,
                        **tag_filter_kwargs
                    )

        instructions = test_obj.get('instructions')

        playwright_instructions = None
        # Check if instructions are valid
        if test_obj.get('playwright_instructions'):
            try:
                playwright_instructions = json.loads(test_obj.get('playwright_instructions'))
            except:
                logger.error(f"Playwright instructions are not valid: {str(e)}")
                logger.debug(traceback.format_exc())
                playwright_instructions = None

        try:
            # Decide backend: Docker (default) vs AKS (uat/prod)
            environment = os.getenv("ENVIRONMENT", DEFAULT_ENV)

            # Convert playwright instructions to string if it's a dict
            if isinstance(playwright_instructions, dict):
                playwright_instructions = json.dumps(playwright_instructions)

            # Convert instructions to string if it's a list
            if isinstance(instructions, list):
                instructions = json.dumps(instructions)

            # Create activity log and append the activity log id to the queue_test_obj
            activity_log_id = str(uuid.uuid4())
            # Create new user where org_id is from suite.
            # Note: Rely on test_id if suite_obj is not available.
            new_user = {
                "user_id": current_user.get("user_id"),
                "org_id": suite_obj.get('org_id', None) if suite_obj else get_org_for_test(test_id)
            }
            create_activity_log(new_user, activity_log_id, testrun_id, run_mode, browser, trigger)
            queue_test_obj['activity_log_id'] = activity_log_id

            # Get blob_url if present (for large queue objects)
            blob_url = queue_test_obj.get('blob_url', None)
            
            if environment != DEFAULT_ENV:
                from utils.utils_aks import AksManager
                aks_manager = AksManager()
                # Use AKS in uat/prod
                pod = aks_manager.create_pod(
                    playwright_instructions=playwright_instructions,
                    instructions=instructions,
                    mode=run_mode,
                    run_id=testrun_id,
                    browser=browser,
                    browserbase_session_id=(session.id if session else None),
                    cdp_url=(session.connect_url if session else None),
                    config=(config if not session else None),
                    variables_dict=global_variables_dict,
                    blob_url=blob_url,
                    labels={'queue_obj': json.dumps(queue_test_obj, default=str)}
                )
                logger.info(f"Started AKS pod {pod.metadata.name} for test run {testrun_id}")
            else:
                from utils.utils_docker import DockerManager
                docker_manager = DockerManager()
                # Default to Docker locally and other non-uat/prod envs
                container = docker_manager.spin_up_docker_container(
                    playwright_instructions=playwright_instructions,
                    instructions=instructions,
                    mode=run_mode,
                    run_id = testrun_id,
                    browser=browser,
                    browserbase_session_id=session.id if session else None,
                    cdp_url=session.connect_url if session else None,
                    config=json.dumps(config) if not session else None,    # If browser is browserbase, then config is not needed
                    variables_dict=global_variables_dict,
                    blob_url=blob_url,
                    labels = {'queue_obj': json.dumps(queue_test_obj, default=str)}
                )
                logger.info(f"Started Docker container {container.id} for test run {testrun_id}")

            # Update test status to running in db
            update_test_result_status(test_id, testrun_id, RUNNING_STATUS)

            # Send message to slack only if the test has not been retried in the container and script mode
            if queue_test_obj.get("container_retries", 0) == 0 and queue_test_obj.get("test_run_retries", 0) == 0:
                # Send message to slack
                send_message_to_slack(
                    message="Test Execution Start" if run_mode != TRIAGE_MODE else "Triage Agent Analysis Started",
                    obj=test_obj,
                    type='test',
                    send_to_integration=False,
                    Test_Run_ID = testrun_id,
                    Environment = environment_name,
                    Config = config_string
                )
            
        except Exception as e:
            if not 'retry_count' in queue_test_obj:
                # Add the queue object to the queue with retry count=1
                queue_test_obj['retry_count'] = 1
                enqueue_run_request(queue_test_obj)
                add_log_to_redis(testrun_id, {"error": "Unable to spin up test execution backend, retrying", 'timestamp': datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",})

                # Increase the rate_limit
                from service.service_runner import TestRunner
                test_runner = TestRunner()
                test_runner.increase_rate_limit(org_id=get_org_id_for_entity(test_id=test_id, suite_obj=suite_obj))
                logger.info(f"Increased rate limit for org {get_org_id_for_entity(test_id=test_id, suite_obj=suite_obj)}")
            else:
                # Raise exception as container is already in retry
                raise Exception("Unable to spin up test execution backend")

    except Exception as e:
        logger.error("Unable to run test, " + str(e))

        result = {
            "output": str(e),     # Update the error message in db.
            "gif_url": None,
            "trace_url": None
        }

        # Add log to Redis
        add_log_to_redis(testrun_id, {"error": str(e),  "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"})

        # Update the testrun status to failed in db
        update_test_result_status(test_id, testrun_id, FAILED_STATUS, result=result)


        # Check if the suite_run is not None, if not node then update suite run status
        if suite_run_id:
            from utils.utils_test import handle_suite_run_completion
            handle_suite_run_completion(suite_run_id, queue_test_obj, ERROR_STATUS, "Unable to spin up test execution backend", test_id, test_obj, environment_name, config_string, config)

        logger.debug(traceback.format_exc())
        raise e
    
        
def check_number_of_tests_ran(suite_run_id: str) -> tuple[bool, int, SuiteRun]:
    # Check if the number of tests executed is equal to the number of tests in the suite
    """
    Check the number of tests that were run for a given suite.

    Args:
        suite_run_id (str): The ID of the test suite run.

    Returns:
        tuple:
            - bool: Indicates whether all the tests in suite ran.
            - int: The number of tests that were run(success + failure).
            - SuiteRun: The SuiteRun object if all tests ran, else None.
    """
    try:
        from app import app
        with app.app_context():
            suite_run_obj = SuiteRun.query.filter_by(suite_run_id=suite_run_id).first()
            if not suite_run_obj:
                return False, 0, None
            
            success_count = suite_run_obj.success_count
            failure_count = suite_run_obj.failure_count
            skipped_count = suite_run_obj.skipped_count
            total_tests = suite_run_obj.total_tests

            if total_tests != (success_count + failure_count + skipped_count):
                # Returing success + failure count as total tests ran(Not including skipped_count as they are not counted in the test run)
                return False, success_count + failure_count, suite_run_obj
        
        return True, total_tests, suite_run_obj
    except Exception as e:
        logger.info("Unable to check number of tests ran, " + str(e))
        logger.debug(traceback.format_exc())
        return False, 0, None
    
def get_failed_test_name_in_suite_run(suite_run_id: str) -> list[str]:
    """
    Get the name of the failed test in a suite run.

    Args:
        suite_run_id (str): The ID of the suite run.

    Returns:
        list[str]: A list of names of the failed tests in the suite run.
    """
    try:
        from app import app
        with app.app_context():
            failed_tests = TestResult.query.options(
                    joinedload(TestResult.test)
                ).filter(
                    TestResult.suite_run_id == suite_run_id,
                    TestResult.status.in_([FAILED_STATUS, ERROR_STATUS])
                ).all()
            
            logger.info(f"Failed tests in suite run {suite_run_id}: {failed_tests}")
            
            if failed_tests:
                failed_test_names = [test.test.name for test in failed_tests]
                return failed_test_names
            return None
    except Exception as e:
        logger.info("Unable to get failed test name in suite, " + str(e))
        logger.debug(traceback.format_exc())
        return None

def get_org_for_test(test_id: str) -> str:
    """
    Get the organization for a given test.
    """
    try:
        from app import app
        with app.app_context():
            test_obj = Test.query.options(joinedload(Test.suite)).filter_by(id=test_id).first()
            if not test_obj:
                return None
            return test_obj.suite.org_id
    except Exception as e:
        logger.info("Unable to get org for test, " + str(e))
        logger.debug(traceback.format_exc())
        return None

def get_org_for_suite(suite_id: str) -> str:
    """
    Get the organization for a given suite.
    """
    try:
        from app import app
        with app.app_context():
            suite_obj = Suite.query.filter_by(suite_id=suite_id).first()
            if not suite_obj:
                return None
            return suite_obj.org_id
    except Exception as e:
        logger.info("Unable to get org for suite, " + str(e))
        logger.debug(traceback.format_exc())
        return None

def get_playwright_script_implementation(current_user: dict, test_id: str):
    try:
        test_obj = return_test_obj(current_user, test_id)
        if not test_obj:
            return {
                "error": f"Test with id {test_id} not found or user does not have access to it"
            }, 404
        
        # Check if playwright instructions exist
        if not test_obj.playwright_instructions:
            response = {
                "error": f"Test with id {test_id} does not have any Playwright instructions"
            }
            return response, 404
        
        # get instructions from test object
        instructions = json.loads(test_obj.instructions)

        # Serialize the test object
        test_obj_dict = test_obj.serialize()
        
        try:
            playwright_instructions = json.loads(test_obj_dict.get('playwright_instructions'))
        except:
            response = {
                "error": "Invalid Playwright instructions format"
            }
            return response, 500

        # Check if the test has any test segment instruction
        response, status_code = replace_test_segment_instruction(current_user, instructions, playwright_instructions, test_obj_dict.get("suite_id"))
        if status_code != 200:     # Test segment validation failed
            return response, status_code
        
        instructions = response.get('instructions')
        playwright_instructions = response.get('playwright_instructions')
        
        # Convert playwright instructions to script format
        script_content = convert_playwright_instructions_to_script(playwright_instructions, instructions)
        
        # Ensure test name is not None or empty, then sanitize for file naming
        test_name = test_obj.name if test_obj.name and test_obj.name.strip() else f"test_{test_obj.id}"
        test_name = re.sub(r"\s+", "_", test_name.strip().lower()) # Replace spaces with underscores
        test_name = re.sub(r"\.+", "", test_name)    # Remove multiple dots
        test_name = re.sub(r"[^a-z0-9_]", "_", test_name) # Replace any other characters with underscores
        
        return {
            "script_content": script_content,
            "test_name": test_name
        }, 200
        
    except Exception as e:
        logger.error("Unable to get playwright script, " + str(e))
        logger.debug(traceback.format_exc())
        raise e

def convert_playwright_instructions_to_script(playwright_instructions: dict, instructions: list) -> str:
    """
    Convert playwright instructions dictionary to executable nodeJS script format.
    Args:
        playwright_instructions (dict): Dictionary containing playwright instructions
    Returns:
        str: Formatted nodeJS script content
    """
    try:
        # Validate the instructions first
        is_valid, script = validate_playwright_instructions_helper(instruction_dictionary=playwright_instructions, instructions=instructions)

        if not is_valid:
            raise Exception("Invalid playwright instructions")

        return script

    except Exception as e:
        logger.error("Unable to convert playwright instructions to script, " + str(e))
        logger.debug(traceback.format_exc())
        raise e

def combine_ins_playwright_ins(instructions: list, playwright_instructions: dict) -> list:
    """
    Combine instructions and playwright instructions.
    """
    try:
        # Add IDs to instructions while preserving their structure
        for instruction in instructions:
            if 'id' not in instruction:
                logger.error(f"Instruction id is not present for instruction: {instruction}")

            id = str(instruction['id'])
            if id in playwright_instructions:
                instruction['playwright_actions'] = playwright_instructions[id]
            else:
                instruction['playwright_actions'] = []
            
        return instructions
    except Exception as e:
        logger.error("Unable to combine instructions and playwright instructions, " + str(e))
        logger.debug(traceback.format_exc())
        raise e

def run_test_helper(current_user: dict, test_obj_dict: dict, browser: str, run_mode: str, config: dict, data_driven_variables_dict: dict = None, trigger: str=MANUAL_TRIGGER, suite_run_id: str=None, suite_obj: dict=None, row_number: int=None, environment_variables: dict=None, environment_name: str=None):
    """
    Helper function to run a test.
    Args:
        current_user (dict): The current user.
        test_obj_dict (dict): The test object.
        browser (str): The browser to use.
        run_mode (str): The run mode.
        config (dict): The config.
        data_driven_variables_dict (dict): The data driven variables dictionary.
        trigger (str): The trigger for the test run.
        suite_run_id (str): The suite run id.
        suite_obj (dict): The suite object.
        row_number (int): The row number of the test data. This is only added in test data run.
        environment_variables (dict): The environment variables.
    Returns:
        tuple:
            - dict: The response.
            - int: The status code.
    """
    try:
        
        
        # Check if the playwright instructions are empty
        playwright_instructions = test_obj_dict.get('playwright_instructions') if test_obj_dict.get('playwright_instructions') else None
        instructions = test_obj_dict.get('instructions') if test_obj_dict.get('instructions') else None

        logger.info(f"Instructions: {instructions} type: {type(instructions)} type of each instruction: {type(instructions[0])}")
        # logger.info(f"Playwright instructions: {playwright_instructions} type: {type(playwright_instructions)} type of each playwright instruction: {type(playwright_instructions[0])}")
        
        if run_mode == SCRIPT_MODE and (not playwright_instructions or len(playwright_instructions) == 0 or not validate_if_playwright_instructions_exist(playwright_instructions, instructions)):
            return {
                "error": f"Playwright instructions are empty or one of the instruction is missing playwright instructions"
            }, 404

        # Check if the test has any ai_file_upload action. If yes, then update the instructions to include the file url
        for idx, instruction in enumerate(instructions):
            response, status_code = replace_file_upload_instruction(current_user, instruction)
            if status_code != 200:
                return response, status_code
            
            instructions[idx] = response

        # Create a new testrun log 
        testrun_id = str(uuid.uuid4())

        # Update the instructions in the test object
        test_obj_dict['instructions'] = json.dumps(instructions)
        test_obj_dict['playwright_instructions'] = json.dumps(playwright_instructions)

        # Create global variables dict
        global_variables_dict = {}
        global_variables_dict['data_driven_variables'] = data_driven_variables_dict
        global_variables_dict['environment_variables'] = environment_variables

        # Determine environment_name for Slack messages based on request data
        # Case 1: If env_name comes in request, use it
        # Case 2: If no env_name in request but env_variables_dict is not empty, use 'Custom ENV variables'
        # Case 3: Do not send env name in any other case
        if environment_name:
            # Case 1: environment_name was passed in (from request_data.get('environment_name'))
            pass  # Use the passed environment_name
        elif environment_variables and len(environment_variables) > 0:
            # Case 2: No env_name in request but env_variables_dict is not empty
            environment_name = 'Custom env variables'
        else:
            # Case 3: Do not send env name in any other case
            environment_name = 'NA'

        # Add test object to the queue
        queue_obj = {
            "test_id": test_obj_dict.get('id'),
            "test_obj": test_obj_dict,
            "testrun_id": testrun_id,
            "browser": browser,
            "run_mode": run_mode,
            "container_retries": 0,                  # This is the number of times the test has been retried in the container.
            "test_run_retries": 0,                   # This is the number of times the test has been retried in the script mode.
            "current_user": current_user,
            "config": config,
            "global_variables_dict": global_variables_dict,
            "trigger": trigger,
            "environment_name": environment_name,
        }

        # Add suite run id and suite object to the queue object if it is a suite run
        if suite_run_id:
            queue_obj['suite_run_id'] = suite_run_id
            queue_obj['suite_obj'] = suite_obj

        # Add row number to the queue object if it is a test data run
        if row_number:
            queue_obj['row_number'] = row_number

        # Update test run status to 'queued' and run_mode, config in db
        update_test_result_status(test_obj_dict.get('id'), testrun_id, QUEUED_STATUS, run_mode, config=config, suite_run_id=suite_run_id, data_row_index=row_number, environment_variables=environment_variables, environment_name=environment_name)

        # Start the test runner, if it is not already running
        from service.service_runner import TestRunner
        try:
            if not TestRunner.is_thread_running(TEST_RUNNER_THREAD_NAME):
                test_runner = TestRunner()  # Start test runner thread
        except Exception as e:
            logger.error("Unable to start test runner, " + str(e))
            logger.debug(traceback.format_exc())

        # Start the container cleanup thread, if it is not already running
        from utils.container_cleanup_thread import start_cleanup_thread
        try:
            start_cleanup_thread()
        except Exception as e:
            logger.error("Unable to start container cleanup thread, " + str(e))
            logger.debug(traceback.format_exc())

        # Add test run id to the global logs dictionary (before enqueue so it's in Redis when worker picks up)
        add_log_to_redis(testrun_id, {"info": f"Test run queued", "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"})

        # Enqueue the test run request
        try:
            enqueue_run_request(queue_obj)
        except Exception as e:
            error_message = str(e).lower()
            # Check if error is related to message size
            is_size_error = (
                'message too large' in error_message or
                'message size' in error_message or
                'too large' in error_message or
                'size limit' in error_message or
                ('exceeds' in error_message and 'size' in error_message)
            )
            
            if is_size_error:
                try:
                    handle_large_queue_obj(queue_obj)
                except Exception as handle_error:
                    logger.error(f"Error handling large queue object: {str(handle_error)}")
                    logger.debug(traceback.format_exc())
                    # Update test status to error in db
                    update_test_result_status(test_obj_dict.get('id'), testrun_id, ERROR_STATUS)
                    return {
                        "error": "Unable to enqueue test run request (size error handling failed)"
                    }, 500
            else:
                logger.error("Unable to enqueue test run request, " + str(e))
                # Update test status to error in db
                update_test_result_status(test_obj_dict.get('id'), testrun_id, ERROR_STATUS)
                return {
                    "error": "Unable to enqueue test run request"
                }, 500

        return {"testrun_id": testrun_id}, 200

    except Exception as e:
        logger.error("Unable to run test, " + str(e))
        logger.debug(traceback.format_exc())
        raise e

def handle_large_queue_obj(queue_obj: dict):
    """
    Handle large queue objects that exceed Azure queue size limits.
    This function:
    1. Uploads the queue_obj to Azure blob storage in 'large_queue_objs' folder
    2. Stores the blob URL in queue_obj
    3. Removes test_obj and suite_obj from queue_obj to reduce size
    4. Pushes the modified queue_obj to the queue again
    
    Args:
        queue_obj: The queue object that is too large for Azure queue
    """
    try:
        logger.info("Handling large queue object - uploading to blob storage")
        
        # Generate a unique filename for the blob
        testrun_id = queue_obj.get('testrun_id')
        blob_filename = f"{testrun_id}.json"
        
        # Upload queue_obj to blob storage in 'large_queue_objs' folder
        blob_url = upload_json_blob(queue_obj, 'large_queue_objs', blob_filename)
        logger.info(f"Uploaded large queue object to blob storage: {blob_url}")
        
        # Store the blob URL in queue_obj
        queue_obj['blob_url'] = blob_url
        
        # Remove instructions and playwright_instructions from queue_obj to reduce size
        queue_obj['test_obj']['instructions'] = "[]"
        queue_obj['test_obj']['playwright_instructions'] = "{}"
        
        logger.info("Removed instructions and playwright_instructions from queue_obj")
        
        # Push the modified queue_obj to the queue again
        enqueue_run_request(queue_obj)
        logger.info("Successfully requeued modified queue object")
        
    except Exception as e:
        logger.error(f"Error handling large queue object: {str(e)}")
        logger.debug(traceback.format_exc())
        raise e

def handle_test_data(current_user: dict, browser: str, run_mode: str, request_data: dict, test_obj: Test, trigger: str=MANUAL_TRIGGER, suite_run_id: str=None, suite_obj: dict=None):
    """
    Handle test data.
    1. Get the file URL from the file object
    2. Download the file
    3. Call run_test_helper for each row in the csv file.
    4. run_test_helper will add the tests to queue
    Args:
        current_user (dict): The current user.
        browser (str): The browser to use.
        run_mode (str): The run mode.
        request_data (dict): The request data.
        test_obj (Test): The test object.
        trigger (str): The trigger for the test run.
        suite_run_id (str): The suite run id.
        suite_obj (dict): The suite object.
    Returns:
        tuple:
            - dict: The response.
            - int: The status code.
    """
    try:
        # Extract the playwright config from the request data
        config, status_code = get_config_from_request(request_data, test_obj.suite)
        if status_code != 200:
            return config, status_code

        local_file_path = None
        file_id = test_obj.file_id
        if not file_id:
            logger.info(f"Test {test_obj.id} does not have any test data")
            return {
                "error": "Test does not have any test data. Upload a CSV file to run the test"
            }, 404
        
        # Get the file object
        file_obj = test_obj.file
        if not file_obj:
            logger.info(f"Test {test_obj.id} does not have any test data")
            return {
                "error": "Test does not have any test data. Upload a CSV file to run the test"
            }, 404

        # Check if the file type is data
        if file_obj.type != FILE_TYPE_DATA:
            logger.info(f"Test {test_obj.id} does not have any test data")
            return {
                "error": "Only data type files are allowed to run test data."
            }, 404

        # Check the file extension
        if file_obj.file_name.split('.')[-1] != 'csv':
            logger.info(f"Test {test_obj.id} does not have any test data")
            return {
                "error": "Only CSV files are allowed to run test data."
            }, 404

        # Serialize the test object
        test_obj_dict = test_obj.serialize()
        
        # Get the playwright instructions
        playwright_instructions = json.loads(test_obj_dict.get('playwright_instructions'))
        instructions = test_obj_dict.get('instructions')

        logger.info(f"Suite id for test data: {test_obj_dict.get('suite_id')}")

        # Check if any of the instruction is a test segment. 
        # Replace the test segment instruction with the test segment instructions, playwright instructions
        # Return the updated instructions and playwright instructions
        response, status_code = replace_test_segment_instruction(current_user, instructions, playwright_instructions, test_obj_dict.get("suite_id"))
        if status_code != 200:     # Test segment validation failed
            return response, status_code
        
        test_obj_dict['instructions'] = response.get('instructions')
        test_obj_dict['playwright_instructions'] = response.get('playwright_instructions')

        # Get the variables mentioned in the playwright instructions
        required_data_driven_variables = get_variables_from_instructions(test_obj_dict['playwright_instructions'])
        logger.info(f"Required data driven variables: {required_data_driven_variables}")

        # Validate environment and return the environment object
        env_result, status_code = validate_environment_and_return_environment_dict(current_user, request_data, test_obj_dict)
        if status_code != 200:
            return env_result, status_code

        # Extract environment variables and name from validation result
        env_variables_dict = env_result.get('variables', {})
        environment_name_from_validation = env_result.get('environment_name')

        # log environment variables
        logger.info(f"Environment variables that will be used in the test: {env_variables_dict}")

        # Download the file
        file_url = file_obj.file_url
        local_file_path = f"{file_obj.file_name}"
        fetch_blob(file_url, local_file_path)

        # Append testrun_ids in response
        queued_test_run_ids = []

        # Get headers from the csv file
        with open(local_file_path, 'r') as csv_file:
            csv_reader = csv.DictReader(csv_file)
            headers = csv_reader.fieldnames

            # Validate the column names and variables in the playwright instructions
            # error_message, status_code = validate_column_names_and_variables(headers, required_data_driven_variables)
            # if status_code != 200:
            #     logger.info(f"Error in validate_column_names_and_variables: {error_message} {headers} {required_data_driven_variables}")
            #     return {
            #         "error": error_message
            #     }, status_code
            
            # Get the test data
            for row_number, row in enumerate(csv_reader):
                # Create dict of variables and their values to add as docker args
                variables_dict = {}
                for variable in required_data_driven_variables:
                    if variable in row:
                        variables_dict[variable] = row[variable]

                # Create new dict for the test object
                new_test_obj_dict = copy.deepcopy(test_obj_dict)

                logger.info(f"Generated variables dict for row {row_number}: {variables_dict}")
                # Run the test
                response, status_code = run_test_helper(current_user, new_test_obj_dict, browser, run_mode, config, variables_dict, trigger, suite_run_id, suite_obj, row_number+1, env_variables_dict, environment_name=environment_name_from_validation)
                if status_code != 200:
                    logger.info(f"Error in running test for row {row_number}: {response}")
                    return response, status_code

                queued_test_run_ids.append(response.get('testrun_id'))

        return {"message":"All test queued", "testrun_ids": queued_test_run_ids, "config": config}, 200
    except Exception as e:
        logger.error("Unable to handle parameterized test data, " + str(e))
        logger.debug(traceback.format_exc())
        return {"error": "Unable to run the test. Unknown error."}, 500
    finally:
        # Delete the local file if it exists
        if local_file_path and os.path.exists(local_file_path):
            os.remove(local_file_path)

def handle_non_test_data(current_user: dict, browser: str, run_mode: str, request_data: dict, test_obj: Test, trigger: str=MANUAL_TRIGGER, suite_run_id: str=None, suite_obj: dict=None) -> tuple[dict, int]:
    """
    Handle non test data.
    1. Non test data is the test data that does not have any csv file.
    2. Check if there are any variables references in the playwright instructions.
    3. If there are variables references, return an error.
    4. If there are no variables references, call run_test_helper.
    5. run_test_helper will add the test to queue.
    Args:
        current_user (dict): The current user.
        browser (str): The browser to use.
        run_mode (str): The run mode.
        request_data (dict): The request data.
        test_obj (Test): The test object.
        trigger (str): The trigger for the test run.
        suite_run_id (str): The suite run id.
        suite_obj (dict): The suite object.
    Returns:
        tuple:
            - dict: The response.
            - int: The status code.
    """
    try:
        # Extract the playwright config from the request data
        config, status_code = get_config_from_request(request_data, test_obj.suite)
        if status_code != 200:
            return config, status_code

        # Serialize the test object
        test_obj_dict = test_obj.serialize()

        # Get the playwright instructions
        playwright_instructions = json.loads(test_obj_dict.get('playwright_instructions'))
        instructions = test_obj_dict.get('instructions')

        logger.info(f"Suite id for non test data: {test_obj_dict.get('suite_id')}")

        # Check if any of the instruction is a test segment. 
        # Replace the test segment instruction with the test segment instructions, playwright instructions
        # Return the updated instructions and playwright instructions
        response, status_code = replace_test_segment_instruction(current_user, instructions, playwright_instructions, test_obj_dict.get("suite_id"))
        if status_code != 200:     # Test segment validation failed
            return response, status_code
        
        # Updated playwright instructions and instructions, after replacing the test segment instruction
        test_obj_dict['instructions'] = response.get('instructions')
        test_obj_dict['playwright_instructions'] = response.get('playwright_instructions')

        # Validate environment and return the environment object
        env_result, status_code = validate_environment_and_return_environment_dict(current_user, request_data, test_obj_dict)
        if status_code != 200:
            return env_result, status_code

        # Extract environment variables and name from validation result
        env_variables_dict = env_result.get('variables', {})
        environment_name_from_validation = env_result.get('environment_name')

        # log variables dict
        logger.info(f" ENV Variables dict: {env_variables_dict}")

        # Get the required variables from the playwright instructions
        playwright_instructions = test_obj_dict.get('playwright_instructions')
        required_variables = get_variables_from_instructions(playwright_instructions)

        # If there are variables references, return an error
        if len(required_variables) > 0:
            logger.info(f"Variables references are not allowed in non test data: {required_variables}")
            # return {
            #     "error": "Variables references are not allowed in non test data"
            # }, 400
        
        # Run the test
        response, status_code = run_test_helper(current_user, test_obj_dict, browser, run_mode, config, None, trigger, suite_run_id, suite_obj, environment_variables=env_variables_dict, environment_name=environment_name_from_validation)
        if status_code != 200:
            logger.info(f"Error in handle_non_test_data: {response} {status_code}")
            return response, status_code

        # Send same response for test data and non test data
        return {"message": "Test run queued", "testrun_ids": [response.get('testrun_id')], "config": config}, status_code
    except Exception as e:
        logger.error("Unable to handle non test data, " + str(e))
        logger.debug(traceback.format_exc())
        return {"error": "Unable to run the test. Unknown error."}, 500

def validate_environment_and_return_environment_dict(current_user: dict, request_data: dict, test_obj_dict: dict) -> tuple[dict, int]:
    """
    Validate environment and return environment variables dictionary
    1. Validate environment access
    2. Get available environment and required environment variables
    3. Validate if the required environment variables are present in the environment
    4. Merge environment variables from request with database variables
    5. Return environment variables dictionary which are required
    Args:
        current_user: dict
        request_data: dict
        test_obj_dict: dict
    Returns:
        tuple:
            - dict: The environment variables dictionary.
            - int: The status code.
    """
    try:
        # Validate environment_id if provided
        environment_id = request_data.get('environment_id')
        environment_name = request_data.get('environment_name')

        environment_obj = {}
        required_env_vars = {}
        if environment_id or environment_name:
            
            # Validate environment access
            environment, error_msg, status_code = validate_environment_access_implementation(current_user, environment_id, environment_name, test_obj_dict.get('suite_id'))
            if status_code != 200:
                return {"error": error_msg}, status_code

            environment_obj = environment.serialize()
            environment_id = environment.environment_id

        # Get environment variables from request if provided
        request_env_vars = request_data.get('environment_variables', {})
        logger.info(f"Environment variables from request: {list(request_env_vars.keys()) if request_env_vars else 'None'}")

        # Merge database environment variables with request environment variables
        # Request variables take precedence over database variables
        db_env_vars = environment_obj.get('variables', {})
        merged_env_vars = {**db_env_vars, **request_env_vars}
        
        # get available environment variable keys as list (from merged variables)
        available_env_vars = list(merged_env_vars.keys())
            
        # Extract required variables  from playwright instructions
        playwright_instructions = test_obj_dict.get('playwright_instructions')
        required_env_vars = get_environment_variables_from_instruction(playwright_instructions=playwright_instructions)
        logger.info(f"Available environment variables: {available_env_vars}")
        logger.info(f"Required environment variables: {required_env_vars}")
        
        # Validate environment variables
        error_msg, status_code = validate_environment_variables_implementation(available_env_vars, required_env_vars)
        if status_code != 200:
            return {"error": error_msg}, status_code

        # Create a new dictionary of env variables that are required
        env_variables_dict = {}
        for var in required_env_vars:
            env_variables_dict[var] = merged_env_vars.get(var)

        # Return both environment variables and environment name
        result = {
            'variables': env_variables_dict,
            'environment_name': environment_obj.get('environment_name') if environment_obj else None
        }
        return result, 200
    except Exception as e:
        logger.error("Unable to validate environment, " + str(e))
        logger.debug(traceback.format_exc())
        return {"error": "Internal server error"}, 500

def get_tests_based_on_tag_filter(suite_id: str, tag_filter: dict) -> list[Test]:
    """
    Get tests based on tag filter according to the following logic:
    - If tag_filter is None or empty → return all tests
    - If tag_filter is provided but tags is empty and condition is contains_any → return no tests
    - If tag_filter is provided but tags is empty and condition is does_not_contain_any → return all tests
    - If tag_filter is provided but tags is not empty and condition is in allowed values → return filtered tests
    
    Args:
        suite_id: UUID of the suite
        tag_filter: Dict with 'condition' and 'tags' keys, or None/empty dict to return all tests
    Returns:
        list[Test]: List of filtered tests
    """
    try:
        # Start with base query for all tests in the suite
        test_query = Test.query.filter_by(suite_id=suite_id)
        
        # If tag_filter is None, empty dict, return all tests
        if not tag_filter or not isinstance(tag_filter, dict) or len(tag_filter) == 0:
            return test_query.all()
        
        # Apply tag filter using the utility function
        from utils.utils_tags import apply_tag_filter_to_test_query
        filtered_query = apply_tag_filter_to_test_query(test_query, tag_filter)
        
        return filtered_query.all()
    except Exception as e:
        logger.error("Unable to get tests based on tag filter, " + str(e))
        logger.debug(traceback.format_exc())
        return []
