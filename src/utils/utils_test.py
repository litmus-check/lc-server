import ast
import asyncio
import traceback
import json
import re
from database import db
from sqlalchemy.orm import joinedload
from utils.utils_constants import *
from utils.util_blob import *
from utils.utils_playwright import *
from log_config.logger import logger
from datetime import datetime, timedelta
from langchain_openai import AzureChatOpenAI
from models.TestResult import TestResult
from dotenv import load_dotenv, find_dotenv
from models.Suite import Suite  
from models.SuiteRun import SuiteRun
from models.Test import Test
import uuid
import os
from service.service_redis import *
from service.service_browserbase import get_browserbase_session, get_session_debug_urls
from utils.instruction_formatter import format_instruction_for_display
from utils.action_constants import TEST_SEGMENT
from models.Credits import Credits
load_dotenv(find_dotenv("app.env"))

def count_ai_instructions_that_need_credits(instructions: list, current_user: dict = None) -> int:
    """
    Count AI instructions that will consume AI credits.
    An instruction needs AI credits if:
    - It's type "AI" and doesn't have playwright_actions
    - It has ai_use="always_ai"
    - It's a verification with prompt and doesn't have playwright_actions
    - It's a goal action and doesn't have playwright_actions
    
    For test segments, recursively count instructions from the segment.
    
    Args:
        instructions: List of instruction dictionaries
        current_user: Current user dict (optional, needed for expanding test segments)
    Returns:
        int: Count of AI instructions that will consume credits
    """
    count = 0
    for instruction in instructions:
        # Handle test segments by recursively counting their instructions
        if instruction.get("type") == TEST_SEGMENT and current_user:
            try:
                from service.service_test_segment import validate_test_segment_existence_helper
                test_obj, status_code = validate_test_segment_existence_helper(current_user, instruction)
                if status_code == 200 and test_obj:
                    segment_instructions = test_obj.get("instructions", [])
                    if isinstance(segment_instructions, str):
                        segment_instructions = json.loads(segment_instructions)
                    # Recursively count instructions in the test segment
                    count += count_ai_instructions_that_need_credits(segment_instructions, current_user)
                continue
            except Exception as e:
                logger.error(f"Error expanding test segment for credit counting: {e}")
                # Continue with other instructions if segment expansion fails
                continue
        
        has_playwright_scripts = (instruction.get("playwright_actions") and 
                                 len(instruction.get("playwright_actions", [])) > 0)
        
        # If instruction has playwright_actions, it won't consume AI credits
        if has_playwright_scripts:
            continue
            
        instruction_type = instruction.get("type")
        action = instruction.get("action")
        ai_use = instruction.get("ai_use")
        
        is_ai_instruction = (instruction_type == "AI")
        is_always_ai = (ai_use == "always_ai")
        is_verification_with_prompt = (action == "verify" and instruction.get("args") and 
                                      any(arg.get("key") == "prompt" and arg.get("value") for arg in instruction.get("args", [])))
        is_goal = (action == "goal")
        
        if is_ai_instruction or is_always_ai or is_verification_with_prompt or is_goal:
            count += 1
    
    return count

def check_ai_credits_for_test(current_user: dict, instructions: list) -> tuple[dict, int]:
    """
    Check if user has enough AI credits for the test instructions.
    
    Args:
        current_user: Current user dictionary
        instructions: List of instruction dictionaries
    Returns:
        tuple: (error_dict, status_code) if insufficient credits, (None, 200) if sufficient
    """
    try:
        ai_instruction_count = count_ai_instructions_that_need_credits(instructions, current_user)
        
        if ai_instruction_count == 0:
            return None, 200
        
        # Get available AI credits
        org_id = current_user.get("org_id")
        if not org_id:
            return {"error": "Org ID not found in user details"}, 400
        
        credits = Credits.query.filter_by(org_id=org_id).first()
        if not credits:
            return {"error": "Org not found in credits table"}, 400
        
        available_credits = credits.ai_credits
        
        if ai_instruction_count > available_credits:
            logger.info(f"Organization {org_id} has insufficient AI credits. Required: {ai_instruction_count}, Available: {available_credits}")
            return {
                "error": f"Insufficient AI credits"
            }, 403
        
        return None, 200
    except Exception as e:
        logger.error(f"Error checking AI credits for test: {e}")
        logger.debug(traceback.format_exc())
        return {"error": "Error checking AI credits"}, 500

# Initialize the model
llm = AzureChatOpenAI(
    model=os.getenv('AZURE_OPENAI_MODEL', "gpt-4o"),
    api_version='2024-10-21',
    azure_endpoint=os.getenv('AZURE_OPENAI_ENDPOINT', ''),
    api_key=os.getenv('AZURE_OPENAI_KEY', ''),
)
    
def run_test_in_script_mode(playwright_instructions, trace_path, instructions, browser, testrun_id=None):
    try:
        # Add log to redis
        add_log_to_redis(testrun_id, {"info": f"Running the test using playwright", "timestamp": datetime.now().strftime("%d-%m-%Y %H:%M:%S")})
        # Ensure we have an event loop
        # Try to get the current event loop
        try:
            loop = asyncio.get_event_loop()
            logger.info(f"[{testrun_id}] Using existing event loop")
        except RuntimeError:
            # If no event loop exists in this thread, create a new one
            logger.info(f"[{testrun_id}] Creating new event loop")
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        # Run test using playwright
        loop.run_until_complete(run_playwright_commands(playwright_instructions, trace_path, instructions, browser, testrun_id=testrun_id))
        return True
    except Exception as e:
        logger.error(f"[{testrun_id}] Error running playwright instructions: {str(e)}")
        logger.debug(traceback.format_exc())
        return False
        
def run_all_tests(current_user: dict, suite: Suite, suite_run_id: str, browser: str, trigger: str, request_data: dict=None, tests: list[Test]=None):
    from service.service_test import handle_test_data, handle_non_test_data
    logger.info(f"Running all tests for suite {suite.suite_id}")
    skipped_tests = 0
    error_tests = 0
    error_messages = {}

    suite_obj = suite.serialize()
    del suite_obj['tests']   # Remove tests from suite object. As these are not necessary in queue object
    
    # Extract emails from request_data if present and add to suite_obj
    # If emails key exists (even if empty list), treat it as an override
    if request_data and 'emails' in request_data:
        emails = request_data.get('emails')
        suite_obj['override_emails'] = emails
    
    try:
        total_tests = len(tests)
        logger.info(f"Total tests before running: {total_tests}")
        for test in tests:
            # Check if the test is in draft state
            if test.status == TEST_STATUS_DRAFT:
                skipped_tests += 1
                continue

            # Check AI credits for test instructions
            test_obj_dict = test.serialize()
            instructions = test_obj_dict.get('instructions', [])
            if instructions:
                # Parse instructions if they're JSON string
                if isinstance(instructions, str):
                    instructions = json.loads(instructions)
                
                error_response, status_code = check_ai_credits_for_test(current_user, instructions)
                if status_code != 200:
                    # Mark test as error due to insufficient credits
                    if test.id not in error_messages:
                        error_messages[test.id] = {}
                        error_messages[test.id]['test_name'] = test.name
                        error_messages[test.id]['errors'] = [error_response.get('error') or "Unknown error"]
                    else:
                        error_messages[test.id]['errors'].append(error_response.get('error') or "Unknown error")
                    error_tests += 1
                    logger.info(f"Insufficient AI credits for test {test.id} in suite {suite.suite_id}: {error_response.get('error')}")
                    continue

            # Check if the test has test data
            if test.has_test_data:
                # Handle test data
                response, status_code = handle_test_data(current_user, browser, SCRIPT_MODE, request_data, test, trigger, suite_run_id, suite_obj)

                if status_code == 200:
                    # Update suite_run total tests based on the the number of rows in each test
                    total_tests += compute_total_rows(test) - 1  # Subtract 1 because the we already have 1 test in the suite run
                    logger.info(f"Total tests after running: {total_tests}")

            else:
                # Handle non test data
                response, status_code = handle_non_test_data(current_user, browser, SCRIPT_MODE, request_data, test, trigger, suite_run_id, suite_obj)

            if status_code != 200:
                # Update the skipped test reasons
                if test.id not in error_messages:
                    error_messages[test.id] = {}
                    error_messages[test.id]['test_name'] = test.name
                    error_messages[test.id]['errors'] = [response.get('error') or response.get('message') or "Unknown error"]   # get the error or message from the response
                else:
                    error_messages[test.id]['errors'].append(response.get('error') or response.get('message') or "Unknown error")   # get the error or message from the response
                error_tests += 1
                logger.info(f"Error in running test {test.id} in suite {suite.suite_id}: {response.get('error') or response.get('message') or 'Unknown error'}")
                continue

            logger.info(f"Enqueued test run request for test {test.id} in suite {suite.suite_id}")

            # Add test run id to the global logs dictionary
            # add_log_to_redis(testrun_id, {"info": f"Test run queued", "timestamp": datetime.now().strftime("%d-%m-%Y %H:%M:%S")})

        # Check if the tests are skipped
        status = None
        if skipped_tests + error_tests == total_tests:
            status = SUITE_COMPLETED_STATUS

        # Update the suite run with total tests count
        logger.info(f"Total tests: {total_tests}, Skipped tests: {skipped_tests}, Error tests: {error_tests}")
        update_suite_run_status(suite_run_id, status=status, skipped_count=skipped_tests, error_messages=json.dumps(error_messages), total_tests=total_tests, error_count=error_tests)
                
    except Exception as e:
        logger.error(f"Error when queueing test requests for suite_id {suite.suite_id}: {str(e)}")
        # update_suite_run_status(suite_run_id, status=ERROR_STATUS)
        logger.debug(traceback.format_exc())
        raise e

def update_test_result_status(test_id, testrun_id, status, mode=None, result=None, retries=0, suite_run_id=None, config=None, data_row_index=None, environment_variables=None, environment_name=None):
    logger.info(f"[{testrun_id}] Updating test result status called")
    try:
        from app import app
        with app.app_context():
            test_result = TestResult.query.filter_by(testrun_id=testrun_id).first()
            if not test_result:  # If test result does not exist, create a new one
                test_result = TestResult(
                    testrun_id=testrun_id,
                    suite_run_id=suite_run_id,
                    test_id=test_id,
                    mode=mode,
                    config=json.dumps(config),
                    data_row_index=data_row_index,
                    environment_variables=json.dumps(environment_variables),
                    environment_name=environment_name
                )
                db.session.add(test_result)

            if status == RUNNING_STATUS:  # Set the start date when the test status is running
                test_result.start_date = db.func.now()
            if status == ERROR_STATUS or status == FAILED_STATUS or status == SUCCESS_STATUS:  # Set the end date when the test status is error, failed or success
                test_result.end_date = db.func.now()

            if result:  # Update the result if available, else just update the status
                test_result.output = result['output']
                test_result.gif_url = result['gif_url']
                test_result.end_date = db.func.now()
                test_result.trace_url = result['trace_url']
                test_result.retries = retries

                test_result.mode = mode if mode else test_result.mode

                # Add logs to test result
                logs = get_logs_from_redis(testrun_id)
                if logs:
                    test_result.logs = json.dumps(logs)

            test_result.status = status
            db.session.commit()
            logger.info(f"[{testrun_id}] Test result status updated")
    except Exception as e:
        logger.error(f"[{testrun_id}] Unable to update test status, " + str(e))
        logger.debug(traceback.format_exc())
        raise e
    
def update_suite_run_status(suite_run_id, status, success_count=None, failure_count=None, skipped_count=None, error_messages=None, config=None, total_tests=None, error_count=None, environment_variables=None, triage_status=None, triage_result=None, triage_count=None, environment_name=None) -> dict:
    logger.info("Updating suite run status called")
    try:
        from app import app
        with app.app_context():
            suite_run = SuiteRun.query.filter_by(suite_run_id=suite_run_id).first()
            if total_tests is not None:
                suite_run.total_tests = total_tests
            if status:
                suite_run.status = status
                if status == RUNNING_STATUS:  # Set the start date when the suite run status is running
                    suite_run.start_date = db.func.now()
                if status == SUITE_COMPLETED_STATUS:
                    suite_run.end_date = db.func.now()
            if success_count is not None:
                suite_run.success_count += success_count
            if failure_count is not None:
                suite_run.failure_count += failure_count
            if skipped_count is not None:
                suite_run.skipped_count += skipped_count
                if suite_run.skipped_count == suite_run.total_tests:  # If all tests are skipped, set the start, end and status
                    suite_run.end_date = db.func.now()
                    suite_run.status = SUITE_COMPLETED_STATUS
            if triage_count is not None:
                suite_run.triage_count += triage_count
                suite_run.triage_status = RUNNING_STATUS if suite_run.triage_count == 1 else suite_run.triage_status  # Set the triage status to running for the first time
            if error_messages is not None:
                suite_run.error_messages = error_messages
            if error_count is not None:
                suite_run.error_count += error_count
            if config:
                suite_run.config = json.dumps(config)
            if environment_variables is not None:
                suite_run.environment_variables = json.dumps(environment_variables)
            if triage_status is not None:
                suite_run.triage_status = triage_status
            if triage_result is not None:
                old_result = json.loads(suite_run.triage_result) if suite_run.triage_result else []
                old_result.append(triage_result)
                suite_run.triage_result = json.dumps(old_result)

                # Check the triage count equal to len of triage result
                suite_run.triage_status = SUITE_COMPLETED_STATUS if suite_run.triage_count == len(json.loads(suite_run.triage_result)) else suite_run.triage_status

            if environment_name is not None:
                suite_run.environment_name = environment_name

            db.session.commit()
            return suite_run.serialize()
    except Exception as e:
        logger.error("Unable to update suite run status, " + str(e))
        logger.debug(traceback.format_exc())
        raise e

def handle_suite_run_completion(suite_run_id, queue_obj, status, output, test_id, test_obj, environment_name, config_string, config):
    """
    Handle suite run completion logic including status updates, notifications, and triage handling.
    This function is shared between Docker and AKS implementations.
    
    Args:
        suite_run_id: The suite run ID
        queue_obj: Queue object containing suite and test information
        status: Test execution status (SUCCESS_STATUS, FAILED_STATUS, ERROR_STATUS)
        output: Test output message
        test_id: Test ID
        test_obj: Test object dictionary
        environment_name: Environment name
        config_string: Formatted config string
        config: Config dictionary
    """
    try:
        from service.service_test import check_number_of_tests_ran, get_failed_test_name_in_suite_run
        from service.service_redis import remove_from_current_runs
        from utils.utils_slack import send_message_to_slack, send_triage_findings_message
        
        suite_status = None
        # Check if all tests in suite have completed
        suite_obj = queue_obj.get('suite_obj', None)
        _, _, suite_run_obj = check_number_of_tests_ran(suite_run_id)

        # Increment the test count by 1 as the current test execution is not yet updated in db
        all_tests_completed = suite_run_obj.total_tests == suite_run_obj.success_count + suite_run_obj.failure_count + suite_run_obj.skipped_count + suite_run_obj.error_count + 1

        success_count, failure_count = None, None
        if status == SUCCESS_STATUS:
            success_count = 1
            suite_run_obj.success_count = suite_run_obj.success_count + 1   # Increment the success count by 1 as the current test execution is not yet updated in db
        elif status == FAILED_STATUS:
            failure_count = 1
            suite_run_obj.failure_count = suite_run_obj.failure_count + 1   # Increment the failure count by 1 as the current test execution is not yet updated in db

        # If the status is error, then increment the error count
        error_count = None
        error_messages = json.loads(suite_run_obj.error_messages) if suite_run_obj.error_messages else {}
        if status == ERROR_STATUS:
            error_count = 1
            suite_run_obj.error_count = suite_run_obj.error_count + 1   # Increment the error count by 1 as the current test execution is not yet updated in db
            if test_id not in error_messages:
                error_messages[test_id] = {}
                error_messages[test_id]['test_name'] = test_obj.get('name', None)
                error_messages[test_id]['errors'] = [output]
            else:
                error_messages[test_id]['errors'].append(output)
        
        if all_tests_completed:
            # Get failed test names if any
            failed_test_names = get_failed_test_name_in_suite_run(suite_run_id)

            # Remove the org id from the current runs
            remove_from_current_runs(suite_run_id)     
            
            # Get tag_filter from suite_run_obj and flatten it
            tag_filter = json.loads(suite_run_obj.tag_filter) if suite_run_obj.tag_filter else {}
            tag_filter_kwargs = {}
            if tag_filter:
                tag_filter_kwargs['Tag Filter Condition'] = tag_filter.get('condition', '')
                tag_filter_kwargs['Tag Filter Tags'] = json.dumps(tag_filter.get('tags', []))
            
            # Send slack message for suite completion
            send_message_to_slack(
                message="Suite Execution Completed",
                obj=suite_obj,
                type='suite',
                send_to_integration=True,
                Suite_Run_ID = suite_run_id,
                Environment = environment_name,
                Config = config_string,
                suite_completion_data={
                    "total_tests": suite_run_obj.total_tests,
                    "success_count": suite_run_obj.success_count,
                    "failure_count": suite_run_obj.failure_count,
                    "skipped_count": suite_run_obj.skipped_count,
                    "failed_tests": failed_test_names,
                    "error_count": suite_run_obj.error_count,
                    "error_messages": json.loads(suite_run_obj.error_messages) if suite_run_obj.error_messages else {}
                },
                **tag_filter_kwargs
            )
            
            # Send email notification for suite completion
            try:
                from utils.utils_email import suite_completion_email
                from models.Suite import Suite
                
                logger.info(f"Attempting to send email notification for suite completion: {suite_run_id}")
                
                # Extract override emails from suite_obj if present
                override_emails = suite_obj.get('override_emails') if suite_obj else None
                logger.info(f"Using override emails from request: {override_emails}")
                    
                test_results = {
                    'passed': suite_run_obj.success_count,
                    'failed': suite_run_obj.failure_count,
                    'errors': suite_run_obj.error_count
                }
                
                # Get report link using BASE_URL
                report_link = f"{os.getenv('BASE_URL')}/dashboard/suite/{suite_obj.get('suite_id')}/run/{suite_run_id}"
                logger.info(f"Using report URL: {report_link}")
                
                logger.info(f"Sending email with test_results: {test_results}")
                logger.info(f"Failed test names: {failed_test_names}")
                
                email_sent = suite_completion_email(
                    org_id=suite_obj.get('org_id'),
                    suite_id=suite_obj.get('suite_id'),
                    suite_name=suite_obj.get('name'),
                    test_results=test_results,
                    failed_test_names=failed_test_names,
                    report_link=report_link,
                    environment_name=environment_name,
                    config=config,
                    tag_filter=tag_filter,
                    override_emails=override_emails
                )
                
                if email_sent:
                    logger.info(f"Email notification sent successfully for suite {suite_obj.get('suite_id')}")
                else:
                    logger.warning(f"Email notification failed to send for suite {suite_obj.get('suite_id')}")
               
            except Exception as email_error:
                logger.error(f"Failed to send email notification: {str(email_error)}")
                logger.debug(traceback.format_exc())
            
            suite_status = SUITE_COMPLETED_STATUS    # Set the suite status to completed if all tests are completed

            # Send slack message if there are failed tests and triage agent will analyze them. Send only once.
            if suite_run_obj.triage_count > 0:
                send_message_to_slack(
                    message="🔍 Initializing Triage Agent to analyze the failed tests",
                    obj=suite_obj,
                    type='suite',
                    send_to_integration=True,
                    Suite_Run_ID = suite_run_id
                )


        update_suite_run_status(suite_run_id, suite_status, success_count=success_count, failure_count=failure_count, error_count=error_count, error_messages=json.dumps(error_messages) if error_messages else None)
    except Exception as e:
        logger.error(f"Failed to handle suite run completion: {str(e)}")
        logger.debug(traceback.format_exc())
        raise e
    
def update_test_status(test_id, last_run_status, last_run_mode, status=None):
    logger.info("Updating test status called")
    try:
        from app import app
        with app.app_context():
            test = Test.query.filter_by(id=test_id).first()
            test.last_run_status = last_run_status
            test.last_run_mode = last_run_mode
            test.last_run = db.func.now()
            if status is not None:
                test.status = status
            db.session.commit()
    except Exception as e:
        logger.error("Unable to update test status, " + str(e))
        logger.debug(traceback.format_exc())
        raise e


def validate_playwright_instructions_against_instructions(playwright_instructions: dict, instructions: list) -> bool:
    """
    Validate the playwright instructions to ensure they are not empty and contain valid commands.
    Args:
        playwright_instructions (dict): The playwright instructions to validate.
        instructions (list): Natural language instructions to validate.
    Returns:
        bool: True if the instructions are valid, False otherwise.
    """
    try:
        # if len(playwright_instructions) != len(instructions):
        #     return False
        
        # Check if the keys in playwright_instructions are numbers
        for key in playwright_instructions.keys():
            # check if the value is list of strings
            if not isinstance(playwright_instructions[key], list):
                logger.error(f"Value {playwright_instructions[key]} in playwright instructions is not a list")
                return False
        
        # Check if playwright instructions are valid JS code
        valid, _ = validate_playwright_instructions_helper(instruction_dictionary=playwright_instructions, instructions=instructions)

        return valid
    except Exception as e:
        logger.error("Unable to validate playwright instructions, " + str(e))
        logger.debug(traceback.format_exc())
        return False

def validate_playwright_instructions_helper(instruction_str: str=None, instruction_dictionary: dict=None, instructions: list=None) -> tuple[bool, str]:
    """
    Validate the Playwright JS instruction to ensure it is not empty and contains valid commands.
    Args:
        instruction_str (str): The Playwright JS instruction to validate.
        instruction_dictionary (dict): The instruction dictionary to validate.
        We need to validate either the instruction_str or the instruction_dictionary, not both.
    Returns:
        bool: True if the instruction is valid, False otherwise.
        str: The formatted instruction string if return_script is True, else None.
    """
    import subprocess
    import re
    import copy
    from utils.utils_constants import VARIABLE_REGEX_PATTERN, ENV_VARIABLE_REGEX_PATTERN

    logger.info(f"Validating Playwright JS instruction {instruction_str} {instruction_dictionary}")

    # Extract variables and create global variables
    global_variables = []
    variable_pattern = VARIABLE_REGEX_PATTERN
    env_variable_pattern = ENV_VARIABLE_REGEX_PATTERN
    
    logger.info(f"Extracting variables from instructions...")
    
    # Create deep copies to avoid modifying the original data
    if instruction_str:
        instruction_str_copy = instruction_str
        # Find all variables in instruction_str
        variables = re.findall(variable_pattern, instruction_str_copy)
        variables += re.findall(env_variable_pattern, instruction_str_copy)
        logger.info(f"Found variables in instruction_str: {variables}")
        for var in variables:
            if var not in global_variables:
                global_variables.append(var)
        # Replace variables with global variable names (without quotes)
        instruction_str_copy = re.sub(variable_pattern, r'\1', instruction_str_copy)   # Replace ${variable_name} with variable_name
        instruction_str_copy = re.sub(env_variable_pattern, r'\1', instruction_str_copy)   # Replace {{env.variable_name}} with variable_name
        logger.info(f"After replacement instruction_str: {instruction_str_copy}")
    elif instruction_dictionary:
        instruction_dictionary_copy = copy.deepcopy(instruction_dictionary)
        # Find all variables in instruction_dictionary
        for key, value in instruction_dictionary_copy.items():
            for ind, cmd in enumerate(value):
                variables = re.findall(variable_pattern, cmd)
                variables += re.findall(env_variable_pattern, cmd)
                logger.info(f"Found variables in cmd {ind}: {variables}")
                for var in variables:
                    if var not in global_variables:
                        global_variables.append(var)
                # Replace variables with global variable names (without quotes)
                instruction_dictionary_copy[key][ind] = re.sub(variable_pattern, r'\1', cmd)   # Replace ${variable_name} with variable_name
                instruction_dictionary_copy[key][ind] = re.sub(env_variable_pattern, r'\1', instruction_dictionary_copy[key][ind])   # Replace {{env.variable_name}} with variable_name
                logger.info(f"After replacement cmd {ind}: {instruction_dictionary_copy[key][ind]}")
    
    logger.info(f"Final global_variables: {global_variables}")

    try:
        js_script = (
            "const { test, expect } = require('@playwright/test');\n"
            "const assert = require('assert');\n\n"
        )
        
        # Add state object
        js_script += "const state = {\n"
        js_script += "};\n\n"
        
        # Add litmus_log function stub for validation (actual function is provided at runtime)
        js_script += "const litmus_log = async (value) => {};\n\n"
        
        # Add global variables if any were found
        if global_variables:
            logger.info(f"Found global variables: {global_variables}")
            js_script += "// Global variables\n"
            for var in global_variables:
                js_script += f"let {var} = '';\n"
            js_script += "\n"
        else:
            logger.info("No variables found in instructions")
        
        js_script += (
            "test('Generated Test', async ({ page, browserName }) => {\n"
        )

        lines = []
        if instruction_str:
            for line in instruction_str_copy.splitlines():
                js_script += f"  {line}\n"
        elif instruction_dictionary:
            ind=0
            for key, value in instruction_dictionary_copy.items():
                ind+=1
                # Find the corresponding instruction for step description
                instruction = None
                if instructions:
                    for inst in instructions:
                        if str(inst.get('id', '')) == key:
                            instruction = inst
                            break
                
                step_description = format_instruction_for_display(instruction) if instruction else f"Step {ind}"
                safe_description = step_description.replace("\\", "\\\\").replace("'", "\\'")
                js_script += f"  await test.step('{safe_description}', async () => {{\n"
                
                for cmd in value:
                    orig_line = cmd.strip()

                    # XPath regex replacement
                    xpath_match = re.search(r'page\.locator\([\'"]([^\'"]*)[\'"]\)', orig_line)
                    if xpath_match:
                        selector = xpath_match.group(1)
                        if selector.startswith('/html') or selector.startswith('//'):
                            orig_line = re.sub(
                                r'page\.locator\([\'"]([^\'"]*)[\'"]\)',
                                r'page.locator("xpath=\1")',
                                orig_line
                            )

                    # Fix variable references - replace quoted variables with unquoted variables
                    # This handles cases where variables are quoted like 'url' instead of url
                    for var in global_variables:
                        # Replace 'variable' with variable (remove quotes around variables)
                        orig_line = re.sub(rf"['\"]({var})['\"]", r'\1', orig_line)


                    js_script += f"    {orig_line};\n"
                
                js_script += f"  }});\n"
        else:
            logger.error("Either instruction_str or instruction_dictionary must be provided")
            return False, None

        js_script += (
            "});\n"
        )

        logger.info(f"JS script: {js_script}")

        # Validate JS syntax using acorn via Node.js (stdin)
        # Try parsing as module first (for import/export), fall back to script if that fails
        node_code = (
            "const acorn = require('acorn');\n"
            "let data = '';\n"
            "process.stdin.on('data', chunk => data += chunk);\n"
            "process.stdin.on('end', () => {\n"
            "  try {\n"
            "    try {\n"
            "      acorn.parse(data, { ecmaVersion: 'latest', sourceType: 'module' });\n"
            "    } catch (e) {\n"
            "      acorn.parse(data, { ecmaVersion: 'latest', sourceType: 'script' });\n"
            "    }\n"
            "    process.exit(0);\n"
            "  } catch (e) {\n"
            "    console.error(e.message);\n"
            "    process.exit(1);\n"
            "  }\n"
            "});\n"
        )
        result = subprocess.run(
            ['node', '-e', node_code],
            input=js_script,
            capture_output=True,
            text=True,
            encoding='utf-8'    # Accept emojis in the script
        )
        if result.returncode == 0:
            logger.info(f"Playwright JS instructions are valid JS code: {js_script}")
            return True, js_script
        else:
            logger.error(f"Playwright JS instructions are not valid JS code: {result.stderr} {js_script}")
            return False, None
    except Exception as e:
        logger.error("Unable to validate Playwright JS instructions, " + str(e))
        logger.debug(traceback.format_exc())
        return False, None

def get_browserbase_session_for_testrun(testrun_id: str) -> str:
    """
    Get the browserbase session id for a given testrun id.
    """
    try:
        session = get_browserbase_session()
        debug_urls = get_session_debug_urls(session.id)

        # Store the full screen url in Redis
        full_screen_url = debug_urls.pages[-1].debugger_fullscreen_url
        store_browserbase_urls(f"{testrun_id}_live_stream", full_screen_url)

        logger.info(f"[{testrun_id}] Browserbase session ID: {session.id}")
        logger.info(f"[{testrun_id}] Browserbase debug URLs: {debug_urls}")
            
        # Store debug URLs in Redis with a specific key for frontend access
        return session.connect_url, full_screen_url  # Set the cdp_url to the agent
    except Exception as e:
        logger.error(f"[{testrun_id}] Unable to get browserbase session, launching local browser" + str(e))
        logger.debug(traceback.format_exc())
        raise e
    
def get_test_data(test_id: str) -> dict:
    """
    Get the data for a given test.
    """
    try:
        from app import app
        with app.app_context():
            test_obj = Test.query.filter_by(id=test_id).options(joinedload(Test.suite)).first()
            if not test_obj:
                return None
            return test_obj
    except Exception as e:
        logger.info("Unable to get test data, " + str(e))


def validate_if_playwright_instructions_exist(playwright_instructions: dict, instructions: list) -> bool:
    """
    Validate if every instruction has playwright instructions mapped to instruction except run_script action.
    """
    try:
        from utils.action_constants import AI_ASSERT
        for ind, instruction in enumerate(instructions):
            instruction_id = str(instruction.get('id')) if instruction.get('id') else str(ind)
            # If instruction is marked always_ai or is ai_assert, skip playwright presence/emptiness checks
            if instruction.get('ai_use') == 'always_ai' or instruction.get('action') == AI_ASSERT:
                continue

            if instruction_id not in playwright_instructions or not isinstance(playwright_instructions[instruction_id], list):
                logger.info(f"instruction_id {instruction_id} not in playwright_instructions or not isinstance(playwright_instructions[instruction_id], list)")
                return False
            
            if instruction.get('action') != RUN_SCRIPT and len(playwright_instructions[instruction_id]) == 0:
                logger.info(f"instruction.get('action') != RUN_SCRIPT and len(playwright_instructions[instruction_id]) == 0: {instruction.get('action')}")
                return False
        return True
    except Exception as e:
        logger.error("Unable to validate playwright instructions, " + str(e))
        logger.debug(traceback.format_exc())
        return False

def add_script_to_playwright_instruction(instruction: dict, playwright_action: list) -> list:
    """
    Add the script to the playwright instructions if it is empty.
    Note: This function is called when the action is run_script and the script is empty in the instruction.
    Args:
        instruction (dict): The instruction to add the script to.
        playwright_action (list): The playwright actions to add the script to.
    Returns:
        list: The playwright actions with the script added.
    """
    try:
        if instruction.get("action") == RUN_SCRIPT:
            # Always overwrite the playwright action with the script from args
            logger.info(f"Script is empty for instruction {instruction}, adding it from args")
            # Add it from the args 
            for each_arg in instruction.get("args", []):
                if each_arg.get("key") == "script":
                    logger.info(f"[{instruction.get('id')}] Script found for instruction, adding it to playwright actions")
                    return [each_arg.get("value")]

        logger.info(f"[{instruction.get('id')}] Script is not empty for instruction, returning playwright actions as is")
        return playwright_action
    except Exception as e:
        logger.error("Unable to add script to playwright instruction, " + str(e))
        logger.debug(traceback.format_exc())
        return playwright_action

def compute_total_rows(test: Test) -> int:
    """
    Compute the total number of rows in a test file.
    """
    try:
        local_file_path = None
        # Get the file_id from the test
        file_id = test.file_id
        # Get the file from the file_id
        from models.File import File
        file = File.query.filter_by(file_id=file_id).first()
        
        file_url = file.file_url

        local_file_path = f"test_data_{file_id}.csv"

        # Download the file
        fetch_blob(file_url, local_file_path)

        # Return the number of rows in the file excluding the header
        with open(local_file_path, 'r') as file:
            import csv
            reader = csv.reader(file)
            next(reader)  # Skip header row
            rows = sum(1 for row in reader)
            logger.info(f"Total rows in test data: {rows}")
            return rows
    except Exception as e:
        logger.error("Unable to compute total rows in test, " + str(e))
        logger.debug(traceback.format_exc())
        raise e
    finally:
        # Delete the local file if it exists
        if local_file_path and os.path.exists(local_file_path):
            os.remove(local_file_path)