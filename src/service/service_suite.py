from models.Suite import Suite
from models.SuiteRun import SuiteRun
from models.File import File
from models.Schedule import Schedule
from models.Environment import Environment
from models.HealingSuggestion import HealingSuggestion
from models.Test import Test
from service.service_testrun import get_testrun_result_by_suite_run_id
from database import db
from datetime import datetime
import uuid
from utils.utils_test import run_all_tests
from utils.encryption import decrypt_string, encrypt_string
import threading
from log_config.logger import logger
import traceback
from security.authenticate import is_user_authenticated
from utils.utils_slack import send_message_to_slack
from sqlalchemy import func, or_
from models.Test import Test
from utils.utils_constants import *
from utils.utils_playwright_config import get_config_from_request
import json
from utils.util_blob import upload_blob, delete_blob, STORAGE_ACCOUNT_KEY
from azure.storage.blob import BlobClient
from werkzeug.utils import secure_filename
import tempfile
import os
import re
from access_control.roles import ADMIN
from service.service_credits import check_if_user_has_enough_credits
from utils.utils_suite import validate_csv_headers_for_typescript
from utils.utils_tags import *
from utils.utils_email import validate_override_emails

def get_all_suites_implementation(current_user, page_num, limit):
    """
    Retrieve all suites with pagination
    Args:
        current_user: Dictionary containing user information including role and org_id
        page_num: Current page number
        limit: Number of items per page
    Returns:
        Tuple of (response_dict, status_code)
    """
    try:
        # Convert string parameters to integers
        page = int(page_num)
        per_page = int(limit)
        
        # Create a subquery to count tests for each suite
        test_count = db.session.query(
            Test.suite_id,
            func.count(Test.id).label('test_count')
        ).group_by(Test.suite_id).subquery()
        
        # Create a subquery to count environments for each suite
        env_count = db.session.query(
            Environment.suite_id,
            func.count(Environment.environment_id).label('env_count')
        ).group_by(Environment.suite_id).subquery()
        
        # Create a subquery to count schedules for each suite
        schedule_count = db.session.query(
            Schedule.suite_id,
            func.count(Schedule.id).label('schedule_count')
        ).group_by(Schedule.suite_id).subquery()
        
        # Create base query
        base_query = db.session.query(
            Suite,
            func.coalesce(test_count.c.test_count, 0).label('test_count'),
            func.coalesce(env_count.c.env_count, 0).label('env_count'),
            func.coalesce(schedule_count.c.schedule_count, 0).label('schedule_count')
        ).outerjoin(
            test_count,
            Suite.suite_id == test_count.c.suite_id
        ).outerjoin(
            env_count,
            Suite.suite_id == env_count.c.suite_id
        ).outerjoin(
            schedule_count,
            Suite.suite_id == schedule_count.c.suite_id
        )
        
        # Apply organization filter if not admin
        if current_user.get('role') != ADMIN:
            base_query = base_query.filter(Suite.org_id == current_user['org_id'])
            
        # Apply ordering and pagination
        suites = base_query.order_by(
            Suite.modified_at.desc()
        ).paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        # Format response with pagination details
        response = {
            'items': [{
                'suite_id': suite.suite_id,
                'name': suite.name,
                'description': suite.description,
                'created_at': suite.created_at,
                'modified_at': suite.modified_at,
                # 'sign_in_url': suite.sign_in_url,
                # 'username': decrypt_string(suite.username) if suite.username != '' else "",
                # 'password': decrypt_string(suite.password) if suite.password != '' else "",
                'total_tests': test_count,  # Use coalesced count (0 if NULL)
                'total_envs': env_count,  # Use coalesced count (0 if NULL)
                'total_schedules': schedule_count  # Use coalesced count (0 if NULL)
            } for suite, test_count, env_count, schedule_count in suites.items],
            'metadata': {
                'page_number': suites.page,
                'total_pages': suites.pages,
                'total_records': suites.total,
                'page_size': len(suites.items)
            }
        }
        return response, 200
    except Exception as e:
        logger.error(f"Error in get_all_suites_implementation: {str(e)}")
        logger.debug(traceback.print_exc())
        return {"error": str(e)}, 400

def get_suite_by_id_implementation(
    current_user,
    suite_id,
    page_num,
    limit,
    query_filter=None,
    status_filter=None,
    last_run_filter=None,
):
    """
    Retrieve a specific suite by ID
    Args:
        suite_id: UUID of the suite
        page_num: Page number for pagination
        limit: Items per page
        query_filter: Optional query string to filter by custom_test_id or name (OR logic)
        status_filter: Optional status filter (ready, draft)
        last_run_filter: Optional last_run filter (failed, success, error)
    Returns:
        Tuple of (response_dict, status_code)
    """
    try:
        suite = return_suite_obj(current_user, suite_id)
        if not suite:
            return {"error": "Suite not found or user does not have access to it"}, 404

        # Convert pagination params to integers (page_num may be None for no pagination)
        page = int(page_num) if page_num is not None else None
        per_page = int(limit) if limit is not None else None

        # Base query for tests in this suite
        tests_query = Test.query.filter_by(suite_id=suite_id)

        # Helper to build a "starts with" pattern where '_' is treated literally
        def build_contains_pattern(raw: str) -> str:
            # Escape _
            escaped = raw.replace("_", "\\_")
            return f"%{escaped}%"  # prefix match only

        # Apply query filter (matches custom_test_id OR name) if provided
        if query_filter:
            pattern = build_contains_pattern(query_filter)
            # OR logic: match custom_test_id OR name
            tests_query = tests_query.filter(
                or_(
                    Test.custom_test_id.ilike(pattern, escape="\\"),
                    Test.name.ilike(pattern, escape="\\")
                )
            )

        # Apply status filter (ready, draft)
        if status_filter:
            # Only allow specific statuses; ignore invalid values
            allowed_statuses = {TEST_STATUS_READY, TEST_STATUS_DRAFT}
            if status_filter not in allowed_statuses:
                return {"error": "Invalid status filter. Allowed values are: ready, draft"}, 400
            tests_query = tests_query.filter(Test.status == status_filter)

        # Apply last_run filter (failed, success, error)
        if last_run_filter:
            allowed_last_run_statuses = {FAILED_STATUS, SUCCESS_STATUS, ERROR_STATUS, "null"}
            if last_run_filter not in allowed_last_run_statuses:
                return {"error": "Invalid last_run filter. Allowed values are: failed, success, error, None"}, 400

            if last_run_filter == "null":
                tests_query = tests_query.filter(Test.last_run_status.is_(None))
            else:
                tests_query = tests_query.filter(Test.last_run_status == last_run_filter)

        # Apply ordering and pagination (or return all if page is None)
        suite_data = decrypt_suite_data(suite).serialize()

        if page is None:
            # No pagination: return all matching tests
            tests = tests_query.order_by(Test.modified_at.desc()).all()
            suite_data['tests'] = [test.serialize() for test in tests]

            total = len(tests)
            suite_data['total_tests'] = total
            suite_data['metadata'] = {
                "page_number": 1,
                "page_size": total,
                "total_pages": 1,
                "total_records": total,
            }
        else:
            # Paginated response
            tests_page = tests_query.order_by(Test.modified_at.desc()).paginate(
                page=page, per_page=per_page, error_out=False
            )

            # Serialize suite and override tests with paginated/filtered results
            suite_data['tests'] = [test.serialize() for test in tests_page.items]

            # Override total tests with the total number of tests in the suite
            suite_data['total_tests'] = tests_page.total

            # Add metadata for the tests pagination
            suite_data['metadata'] = {
                "page_number": tests_page.page,
                "page_size": tests_page.per_page,
                "total_pages": tests_page.pages,
                "total_records": tests_page.total,
            }

        return suite_data, 200
    except Exception as e:
        logger.error(f"Error in get_suite_by_id_implementation: {str(e)}")
        logger.debug(traceback.print_exc())
        return {"error": str(e)}, 400

def create_suite_implementation(current_user, data):
    """
    Create a new suite
    Args:
        data: Dictionary containing suite details (name, description, config)
    Returns:
        Tuple of (response_dict, status_code)
    """
    try:
        # Validate required fields
        if not data.get('name'):
            return {"error": "Name is required"}, 400
        
        # Validate and process Playwright configuration
        config, status_code = get_config_from_request(data)
        if status_code != 200:
            return config, status_code
        
        # Create new suite instance
        new_suite = Suite(
            suite_id=str(uuid.uuid4()),  # Generate new UUID
            name=data['name'],
            description=data.get('description', ''),
            sign_in_url=data.get('sign_in_url', ''),
            username=encrypt_string(data.get('username', '')),
            password=encrypt_string(data.get('password', '')),
            config=json.dumps(config),
            org_id=current_user['org_id']  # Assuming org_id is part of the current user context
        )
        
        # Save to database
        db.session.add(new_suite)
        db.session.commit()

        # Send message to slack
        send_message_to_slack(
            message="Test Suite Created",
            obj=new_suite.serialize(),
            type='suite',
            send_to_integration=False  # Send message to integration webhook
        )
        return decrypt_suite_data(new_suite).serialize(), 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error in create_suite_implementation: {str(e)}")
        logger.debug(traceback.print_exc())
        return {"error": str(e)}, 400

def update_suite_implementation(current_user, suite_id, data):
    """
    Update an existing suite
    Args:
        suite_id: UUID of the suite to update
        data: Dictionary containing fields to update
    Returns:
        Tuple of (response_dict, status_code)
    """
    try:
        suite = return_suite_obj(current_user, suite_id)
        if not suite:
            return {"error": "Suite not found or user does not have access to it"}, 404
        
        # Validate and process Playwright configuration if provided
        config, status_code = get_config_from_request(data, suite)
        if status_code != 200:
            return config, status_code
        suite.config = json.dumps(config)
            
        # Update only provided fields
        if 'name' in data:
            suite.name = data['name']
        if 'description' in data:
            suite.description = data['description']
        if 'sign_in_url' in data:
            suite.sign_in_url = data['sign_in_url']
        if 'username' in data:
            suite.username = encrypt_string(data['username'])
        if 'password' in data:
            suite.password = encrypt_string(data['password'])
        if 'heal_test' in data:
            suite.heal_test = bool(data['heal_test'])
        if 'triage' in data:
            suite.triage = bool(data['triage'])
        # Save changes
        db.session.commit()

        # Send message to slack
        send_message_to_slack(
            message="Test Suite Updated",
            obj=suite.serialize(),
            type='suite',
            send_to_integration=False  # Send message to integration webhook
        )
        return decrypt_suite_data(suite).serialize(), 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error in update_suite_implementation: {str(e)}")
        logger.debug(traceback.print_exc())
        return {"error": str(e)}, 400

def delete_suite_implementation(current_user, suite_id):
    """
    Delete a suite
    Args:
        suite_id: UUID of the suite to delete
    Returns:
        Tuple of (response_dict, status_code)
    """
    try:
        suite = return_suite_obj(current_user, suite_id)
        if not suite:
            return {"error": "Suite not found or user does not have access to it"}, 404
        
        # Check for dependencies before deletion
        has_files = File.query.filter_by(suite_id=suite_id).first() is not None
        has_schedules = Schedule.query.filter_by(suite_id=suite_id).first() is not None
        
        # If there are dependencies, return error message
        if has_files or has_schedules:
            return {
                "error": "Cannot delete suite. Please delete all associated Files and Schedules before deleting the suite."
            }, 400
            
        # Delete from database
        db.session.delete(suite)
        db.session.commit()

        # Send message to slack
        send_message_to_slack(
            message="Test Suite Deleted",
            obj=suite.serialize(),
            type='suite',
            send_to_integration=False, # Send message to integration webhook
            no_url=True                # Skip Test Suite link in message
        )
        return {"message": "Suite deleted successfully"}, 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error in delete_suite_implementation: {str(e)}")
        logger.debug(traceback.print_exc())
        return {"error": str(e)}, 400

def run_suite_implementation(current_user, suite_id, browser, request_data={}, trigger=MANUAL_TRIGGER):
    """
    Run all tests in a suite sequentially in a single thread
    Args:
        suite_id: UUID of the suite to run
        browser: Browser to run the tests on
        request_data: Request data from the user
        trigger: Trigger of the activity (e.g., 'manual', 'scheduled')
    Returns:
        Tuple of (response_dict, status_code)
    """
    try:
        suite = return_suite_obj(current_user, suite_id)
        if not suite:
            return {"error": "Suite not found or user does not have access to it"}, 404

        # Check if the org that owns the suite has enough credits
        logger.info(f"Checking if Organization {suite.org_id} has enough credits")
        credits_check_resp, status_code = check_if_user_has_enough_credits(suite_id=suite_id)
        if status_code != 200:
            return credits_check_resp, status_code

        # Validate tag_filter if provided
        tag_filter = request_data.get('tag_filter', None)
        error_message, status_code = validate_tag_filter(tag_filter)
        if status_code != 200:
            return {"error": error_message}, status_code

        # get the tests based on the tag_filter
        from service.service_test import get_tests_based_on_tag_filter
        tests = get_tests_based_on_tag_filter(suite_id, tag_filter)
            
        # Check if there are any tests to run
        if not tests:
            if tag_filter:
                return {"error": "No tests found matching the tag filter criteria"}, 400
            else:
                return {"error": "No tests found in the suite"}, 400
        
        # Validate emails if provided in request_data
        if 'emails' in request_data:
            emails = request_data.get('emails')
            is_valid, error_message = validate_override_emails(emails)
            if not is_valid:
                return {"error": error_message}, 400
        
        # Validate and process Playwright configuration if provided
        config, status_code = get_config_from_request(request_data, suite)
        if status_code != 200:
            return config, status_code
        
        # Generate a unique run ID for this suite execution
        suite_run_id = str(uuid.uuid4())

        # Create a new suite run record
        new_suite_run = SuiteRun(
            suite_run_id=suite_run_id,
            suite_id=suite_id,
            start_date=db.func.now(),
            status=QUEUED_STATUS,
            total_tests=len(tests),
            config=json.dumps(config),
            tag_filter=json.dumps(tag_filter) if tag_filter else None
        )

        db.session.add(new_suite_run)
        db.session.commit()

        # This funtion will add the tests to the queue
        run_all_tests(current_user, suite, suite_run_id, browser, trigger, request_data=request_data, tests=tests)
                
        response = {
            'suite_id': suite_id,
            'suite_run_id': suite_run_id,
            'config': config,
            'tag_filter': tag_filter if tag_filter else {},
            'message': f'Suite runs queued successfully',
            'status': QUEUED_STATUS,
        }
        
        return response, 200  # 202 Accepted indicates the request was accepted for processing
        
    except Exception as e:
        logger.error(f"Error in run_suite_implementation: {str(e)}")
        logger.debug(traceback.print_exc())
        raise e
    
def get_suite_runs_implementation(current_user, suite_id, page_num, limit):
    """
    Get all runs for a specific suite
    Args:
        suite_id: UUID of the suite
    Returns:
        Tuple of (response_dict, status_code)
    """
    try:
        suite = return_suite_obj(current_user, suite_id)
        if not suite:
            return {"error": "Suite not found or user does not have access to it"}, 404
        
        # Get all runs for the suite
        runs = SuiteRun.query.filter_by(suite_id=suite_id).order_by(SuiteRun.start_date.desc()).paginate(page=page_num, per_page=limit)
        
        # Create custom serialization without error_messages
        suite_runs_data = []
        for run in runs.items:
            run_data = run.serialize()
            # Remove error_messages from the serialized data
            run_data.pop('error_messages', None)
            suite_runs_data.append(run_data)
        
        response = {
            'suite_id': suite_id,
            'suite_runs': suite_runs_data,
            'metadata': {
                'page_number': runs.page,
                'total_pages': runs.pages,
                'total_records': runs.total,
                'page_size': len(runs.items)
            }
        }

        return response, 200
       
    except Exception as e:
        logger.error(f"Error in get_suite_runs_implementation: {str(e)}")
        logger.debug(traceback.print_exc())
        return {"error": str(e)}, 400
    
def get_suite_run_by_id_implementation(current_user, suite_id, suite_run_id, page_num, limit):
    """
    Get a specific suite run by ID
    Args:
        suite_run_id: UUID of the suite run
    Returns:
        Tuple of (response_dict, status_code)
    """
    try:
        # Find suite run by UUID
        if current_user.get('role') != ADMIN and not is_user_authenticated(current_user, suite_id=suite_id):
            return {"error": "Suite run not found or user does not have access to it"}, 404

        suite_run = SuiteRun.query.filter_by(suite_run_id=suite_run_id, suite_id=suite_id).first()
        if not suite_run:
            return {"error": "Suite run not found"}, 404
        
        # Get test run results for the suite run
        test_run_results = get_testrun_result_by_suite_run_id(suite_run_id, page_num, limit)

        # Add test name in the response
        new_test_run_results = []
        triage_test_run_results = []
        for test_result in test_run_results.items:
            new_test_result = test_result.serialize()
            # Don't add heal mode tests
            if new_test_result.get('mode') == HEAL_MODE:
                continue

            # Remove config from the test result as we are sending suite run config in the response
            new_test_result.pop('config', None)
            new_test_result.pop('environment_variables', None)        # Remove environment_variables from the test result
            new_test_result.pop('environment_name', None)            # Remove environment_name from the test result
            # Donot Add test result if status is error
            if new_test_result['status'] == ERROR_STATUS:
                continue
            new_test_result['test_name'] = test_result.test.name if test_result.test else None
            # Separate triage mode results
            if new_test_result.get('mode') == TRIAGE_MODE:
                triage_test_run_results.append(new_test_result)
            else:
                new_test_run_results.append(new_test_result)
        
        # Parse triage specific data from suite run
        triage_result = json.loads(suite_run.triage_result) if suite_run.triage_result else []

        response = {
            'suite_run_id': suite_run_id,
            'testruns': new_test_run_results,
            'triage_testruns': triage_test_run_results,
            'success_count': suite_run.success_count,
            'failure_count': suite_run.failure_count,
            'skipped_count': suite_run.skipped_count,
            'error_count': suite_run.error_count,
            'total_tests': suite_run.total_tests,
            'status': suite_run.status,
            'config': json.loads(suite_run.config) if suite_run.config else None,
            'errors': json.loads(suite_run.error_messages) if suite_run.error_messages else {},
            'triage_count': suite_run.triage_count,
            'triage_result': triage_result,
            'environment_variables': json.loads(suite_run.environment_variables) if suite_run.environment_variables else {},
            'environment_name': suite_run.environment_name,
            'tag_filter': json.loads(suite_run.tag_filter) if suite_run.tag_filter else {},
            'metadata': {
                'page_number': test_run_results.page,
                'total_pages': test_run_results.pages,
                'total_records': test_run_results.total,
                'page_size': len(test_run_results.items)
            }
        }

        return response, 200
    
    except Exception as e:
        logger.error(f"Error in get_suite_run_by_id_implementation: {str(e)}")
        logger.debug(traceback.print_exc())
        return {"error": str(e)}, 400
    
def decrypt_suite_data(suite):
    """
    Decrypt the suite data
    """
    if suite.username and suite.username != '':
        suite.username = decrypt_string(suite.username)
    if suite.password and suite.password != '':
        suite.password = decrypt_string(suite.password)
    return suite
    
def return_suite_obj(current_user, suite_id):
    """
    Return a suite object if it exists and the user has access to it
    Args:
        current_user: Dictionary containing user information including role and org_id
        suite_id: UUID of the suite
    Returns:
        Suite object or None
    """
    try:
        suite = Suite.query.filter_by(suite_id=suite_id).first()
        if not suite:
            return None
        if current_user.get('role') != ADMIN and suite.org_id != current_user['org_id']:
            return None
        return suite
    except Exception as e:
        logger.error(f"Error in return_suite_obj: {str(e)}")
        logger.debug(traceback.print_exc())
        return None

def get_suite_tags_implementation(current_user, suite_id):
    """
    Get all tags for a suite (lightweight endpoint)
    Args:
        current_user: Dictionary containing user information including role and org_id
        suite_id: UUID of the suite
    Returns:
        Tuple of (response_dict, status_code)
    """
    try:
        suite = return_suite_obj(current_user, suite_id)
        if not suite:
            return {"error": "Suite not found or user does not have access to it"}, 404
        
        # Parse master_tags from JSON string or return empty list
        master_tags = []
        if suite.master_tags:
            try:
                master_tags = json.loads(suite.master_tags) if isinstance(suite.master_tags, str) else suite.master_tags
                if not isinstance(master_tags, list):
                    master_tags = []
            except (json.JSONDecodeError, TypeError):
                master_tags = []
        
        return {"master_tags": master_tags}, 200
    except Exception as e:
        logger.error(f"Error in get_suite_tags_implementation: {str(e)}")
        logger.debug(traceback.print_exc())
        return {"error": "Internal server error"}, 500

def upload_suite_file_implementation(current_user, suite_id, file, file_type=None) -> tuple[dict, int]:
    """
    Upload a file to a suite and store it in Azure blob storage
    Args:
        current_user: Dictionary containing user information including role and org_id
        suite_id: UUID of the suite
        file: File object from request
        file_type: Type of file ('data' or 'upload')
    Returns:
        Tuple of (response_dict, status_code)
    """
    try:
        # Check if suite exists and user has access
        suite = return_suite_obj(current_user, suite_id)
        if not suite:
            return {"error": "Suite not found or user does not have access to it"}, 404
        
        # Validate file type if provided
        if file_type and file_type not in ALLOWED_FILE_TYPES:
            return {"error": f"Invalid file type. Must be one of: {', '.join(ALLOWED_FILE_TYPES)}"}, 400
        
        # Secure the filename
        filename = secure_filename(file.filename)
        if not filename:
            return {"error": "Invalid filename"}, 400
        
        # Validate file extension for data type
        if file_type == FILE_TYPE_DATA:
            file_extension = os.path.splitext(filename)[1].lower()
            if file_extension != '.csv':
                return {"error": "Data type files must be CSV format"}, 400

        # Create temporary file to upload to blob storage
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(filename)[1]) as temp_file:
            file.save(temp_file.name)
            temp_file_path = temp_file.name

        # Validate CSV headers for data type files
        if file_type == FILE_TYPE_DATA:
            error_response, status_code = validate_csv_headers_for_typescript(temp_file_path)
            if error_response:
                try:
                    os.unlink(temp_file_path)
                except Exception:
                    pass
                return error_response, status_code

        file_id = str(uuid.uuid4())
        
        try:
            # Upload to blob storage in file_uploads folder
            folder_name = f"{suite_id}/{file_id}"
            blob_url = upload_blob(temp_file_path, folder_name, filename)
            
            # Create file record in database
            file_record = File(
                file_id=file_id,
                file_name=filename,
                file_url=blob_url,
                type=file_type,
                suite_id=suite_id,
                user_id=current_user['user_id']
            )
            
            db.session.add(file_record)
            db.session.commit()
            
            response = {
                "file_id": file_record.file_id,
                "file_name": file_record.file_name,
                "file_url": file_record.file_url,
                "type": file_record.type
            }
            
            return response, 201
            
        finally:
            # Clean up temporary file
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)
                
    except Exception as e:
        logger.error(f"Error in upload_suite_file_implementation: {str(e)}")
        logger.debug(traceback.print_exc())
        return {"error": str(e)}, 400

def get_suite_files_implementation(current_user, suite_id, file_type=None):
    """
    Get all files for a suite
    Args:
        current_user: Dictionary containing user information including role and org_id
        suite_id: UUID of the suite
        file_type: Optional filter by file type ('data' or 'upload')
    Returns:
        Tuple of (response_dict, status_code)
    """
    try:
        # Check if suite exists and user has access
        suite = return_suite_obj(current_user, suite_id)
        if not suite:
            return {"error": "Suite not found or user does not have access to it"}, 404
        
        # Build query for files
        if file_type:
            query = File.query.filter_by(suite_id=suite_id, type=file_type)
        else:
            query = File.query.filter_by(suite_id=suite_id)
        
        files = query.all()
        
        response = {
            "files": [
                {
                    "file_id": file.file_id,
                    "file_name": file.file_name,
                    "file_url": file.file_url,
                    "type": file.type
                }
                for file in files
            ]
        }
        
        return response, 200
        
    except Exception as e:
        logger.error(f"Error in get_suite_files_implementation: {str(e)}")
        logger.debug(traceback.print_exc())
        return {"error": str(e)}, 400

def delete_suite_file_implementation(current_user, suite_id, file_id):
    """
    Delete a file from a suite
    Args:
        current_user: Dictionary containing user information including role and org_id
        suite_id: UUID of the suite
        file_id: UUID of the file
    Returns:
        Tuple of (response_dict, status_code)
    """
    try:
        # Check if suite exists and user has access
        suite = return_suite_obj(current_user, suite_id)
        if not suite:
            return {"error": "Suite not found or user does not have access to it"}, 404
        
        # Get file by ID
        file = File.query.filter_by(file_id=file_id, suite_id=suite_id).first()

        if not file:
            return {"error": "File not found"}, 404
        
        # Delete file from blob storage
        delete_blob(file.file_url)
        
        # Delete file from database
        db.session.delete(file)
        db.session.commit()

        return {"message": "File deleted successfully"}, 200
    except Exception as e:
        logger.error(f"Error in delete_suite_file_implementation: {str(e)}")
        logger.debug(traceback.print_exc())
        return {"error": str(e)}, 400

def update_suite_file_implementation(current_user, suite_id, file_id, file, file_type=None):
    """
    Update a file in a suite
    Args:
        current_user: Dictionary containing user information including role and org_id
        suite_id: UUID of the suite
        file_id: UUID of the file
        file: File object from request
        file_type: Optional new type for the file ('data' or 'upload')

    Returns:
        Tuple of (response_dict, status_code)
    """
    try:
        suite = return_suite_obj(current_user, suite_id)
        if not suite:
            return {"error": "Suite not found or user does not have access to it"}, 404
        
        file_obj = File.query.filter_by(file_id=file_id).first()
        if not file_obj:
            return {"error": "File not found"}, 404

        # Validate file type if provided
        if file_type and file_type not in ALLOWED_FILE_TYPES:
            return {"error": f"Invalid file type. Must be one of: {', '.join(ALLOWED_FILE_TYPES)}"}, 400

        # Determine if this is a data type file (either new type or existing file type)
        is_data_file = file_type == FILE_TYPE_DATA or (file_type is None and file_obj.type == FILE_TYPE_DATA)
        
        # Validate file extension for data type
        if is_data_file:
            file_extension = os.path.splitext(file.filename)[1].lower()
            if file_extension != '.csv':
                return {"error": "Data type files must be CSV format"}, 400

        # Create temporary file to upload to blob storage
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as temp_file:
            file.save(temp_file.name)
            temp_file_path = temp_file.name

        # Validate CSV headers for data type files
        if is_data_file:
            error_response, status_code = validate_csv_headers_for_typescript(temp_file_path)
            if error_response:
                try:
                    os.unlink(temp_file_path)
                except Exception:
                    pass
                return error_response, status_code

        try:
            # First upload the new file to azure blob storage
            new_file_name = secure_filename(file.filename)
            folder_name = f"{suite_id}/{file_id}"
            new_file_url = upload_blob(temp_file_path, folder_name, new_file_name)
            
            # Delete the old blob from azure blob storage
            if file_obj.file_name != new_file_name:
                delete_blob(file_obj.file_url)
            
            # Update the file_url, file_name, and type in the database
            file_obj.file_url = new_file_url
            file_obj.file_name = new_file_name
            if file_type:
                file_obj.type = file_type
            db.session.commit()

            response = {
                "file_id": file_obj.file_id,
                "file_name": file_obj.file_name,
                "file_url": file_obj.file_url,
                "type": file_obj.type
            }

            return response, 200

        finally:
            # Clean up temporary file
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)

    except Exception as e:
        logger.error(f"Error in update_suite_file_implementation: {str(e)}")
        logger.debug(traceback.print_exc())
        return {"error": str(e)}, 400

def get_suite_file_implementation(current_user, suite_id, file_id):
    """
    Get a file by ID
    Args:
        current_user: Dictionary containing user information including role and org_id
        file_id: UUID of the file
    Returns:
        Tuple of (response_dict, status_code)
    """
    try:
        # Check if file exists and user has access
        suite = return_suite_obj(current_user, suite_id)
        if not suite:
            return {"error": "Suite not found or user does not have access to it"}, 404
        
        file = File.query.filter_by(file_id=file_id, suite_id=suite_id).first()
        if not file:
            return {"error": "File not found"}, 404
        
        return file.serialize(), 200
    except Exception as e:
        logger.error(f"Error in get_suite_file_implementation: {str(e)}")
        logger.debug(traceback.print_exc())
        return {"error": str(e)}, 400

def download_suite_file_implementation(current_user, suite_id, file_id):
    """
    Download a file by ID
    Args:
        current_user: Dictionary containing user information including role and org_id
        suite_id: UUID of the suite
        file_id: UUID of the file
    Returns:
        Tuple of (response_dict, status_code) where response_dict contains file_content, filename, mimetype on success
    """
    try:
        # Check if file exists and user has access
        suite = return_suite_obj(current_user, suite_id)
        if not suite:
            return {"error": "Suite not found or user does not have access to it"}, 404
        
        file = File.query.filter_by(file_id=file_id, suite_id=suite_id).first()
        if not file:
            return {"error": "File not found"}, 404
        
        # Download file content from blob storage
        try:
            blob_client = BlobClient.from_blob_url(file.file_url, credential=STORAGE_ACCOUNT_KEY)
            blob_data = blob_client.download_blob()
            file_content = blob_data.readall()
        except Exception as e:
            logger.error(f"Error downloading file from blob storage: {str(e)}")
            logger.debug(traceback.print_exc())
            return {"error": f"Failed to download file from storage: {str(e)}"}, 500
        
        # Ensure file_content is bytes
        if not isinstance(file_content, bytes):
            file_content = bytes(file_content)
        
        # Clean the filename but preserve the extension
        base_name, ext = os.path.splitext(file.file_name) if '.' in file.file_name else (file.file_name, '')
        clean_base = re.sub(r'[^\w\-_.]', '_', base_name)
        clean_filename = clean_base + ext if ext else clean_base
        
        # Determine mimetype based on file extension
        import mimetypes
        import base64
        mimetype, _ = mimetypes.guess_type(file.file_name)
        if not mimetype:
            mimetype = 'application/octet-stream'
        
        # Encode file content as base64 for JSON serialization
        file_content_base64 = base64.b64encode(file_content).decode('utf-8')
        
        return {
            "file_content": file_content_base64,
            "filename": clean_filename,
            "mimetype": mimetype
        }, 200
    except Exception as e:
        logger.error(f"Error in download_suite_file_implementation: {str(e)}")
        logger.debug(traceback.print_exc())
        return {"error": str(e)}, 400

def get_healing_suggestions_by_suite_implementation(current_user, suite_id, suite_run_id):
    """
    Get all healing suggestions for a suite
    Args:
        current_user: Dictionary containing user information including role and org_id
        suite_id: UUID of the suite
        suite_run_id: UUID of the suite run
    Returns:
        Tuple of (response_dict, status_code)
    """
    try:
        from service.service_test import combine_ins_playwright_ins, return_test_obj
        # Check if suite exists and user has access
        suite = return_suite_obj(current_user, suite_id)
        if not suite:
            return {"error": "Suite not found or user does not have access to it"}, 404
        
        # Get all healing suggestions for the suite
        healing_suggestions = HealingSuggestion.query.filter_by(suite_id=suite_id, suite_run_id=suite_run_id).all()
        
        # Format response according to the specified format
        formatted_suggestions = []
        for suggestion in healing_suggestions:
            serialized = suggestion.serialize()

            # combine instructions and playwright instructions
            instructions = (serialized.get('suggested_test') or {}).get('instructions')
            playwright_instructions = (serialized.get('suggested_test') or {}).get('playwright_actions')
            if instructions and playwright_instructions:
                combined_instructions = combine_ins_playwright_ins(instructions, playwright_instructions)
                serialized['suggested_test']['instructions'] = combined_instructions
                # pop playwright instructions
                serialized['suggested_test'].pop('playwright_actions', None)


            # Combine updated test and playwright instructions
            instructions = (serialized.get('updated_test') or {}).get('instructions')
            playwright_instructions = (serialized.get('updated_test') or {}).get('playwright_actions')
            if instructions and playwright_instructions:
                combined_instructions = combine_ins_playwright_ins(instructions, playwright_instructions)
                serialized['updated_test']['instructions'] = combined_instructions
                serialized['updated_test'].pop('playwright_actions', None)

            # Get current test instructions and playwright instructions
            test_obj = return_test_obj(current_user, serialized.get('test_id'))
            if test_obj:
                current_test = test_obj.serialize()
                instructions = (current_test.get('instructions') or [])
                playwright_instructions = json.loads(current_test.get('playwright_instructions')) if current_test.get('playwright_instructions') else None
                if instructions and playwright_instructions:
                    combined_instructions = combine_ins_playwright_ins(instructions, playwright_instructions)
                    current_test['instructions'] = combined_instructions    
                serialized['current_test'] = current_test

            formatted_suggestion = {
                "id": serialized.get('id'),
                "test_id": serialized.get('test_id'),
                "suggested_test": serialized.get('suggested_test'),
                "updated_test": serialized.get('updated_test'),
                "reasoning": serialized.get('reasoning'),
                "triage_result": serialized.get('triage_result'),
                "failed_test_run_id": serialized.get('failed_test_run_id'),
                "current_test":serialized.get('current_test'),
                "status": serialized.get('status'),
            }
            formatted_suggestions.append(formatted_suggestion)
        
        response = {
            "healing_suggestions": formatted_suggestions
        }
        
        return response, 200
        
    except Exception as e:
        logger.error(f"Error in get_healing_suggestions_by_suite_implementation: {str(e)}")
        logger.debug(traceback.print_exc())
        return {"error": str(e)}, 400

def update_healing_suggestion_implementation(current_user, suite_id, healing_suggestion_id, data):
    """
    Update a healing suggestion status
    Args:
        current_user: Dictionary containing user information including role and org_id
        suite_id: UUID of the suite
        healing_suggestion_id: UUID of the healing suggestion
        data: Dictionary containing status ('accepted' or 'rejected')
    Returns:
        Tuple of (response_dict, status_code)
    """
    try:
        # Check if suite exists and user has access
        suite = return_suite_obj(current_user, suite_id)
        if not suite:
            return {"error": "Suite not found or user does not have access to it"}, 404
        
        # Get the healing suggestion
        healing_suggestion = HealingSuggestion.query.filter_by(
            id=healing_suggestion_id,
            suite_id=suite_id
        ).first()
        
        if not healing_suggestion:
            return {"error": "Healing suggestion not found"}, 404
        
        # Validate status
        status = data.get('status')
        if status not in ['accepted', 'rejected']:
            return {"error": "Status must be 'accepted' or 'rejected'"}, 400
        
        # Update status
        healing_suggestion.status = status

        # Check if the status is accepted
        if status == 'accepted':
            # get instructions from updated_test
            updated_test_from_req = data.get('updated_test')
            if not updated_test_from_req:
                return {"error": "Updated test is required"}, 400
            updated_test_from_req_instructions = updated_test_from_req.get('instructions')
            if not updated_test_from_req_instructions:
                return {"error": "Updated test instructions are required"}, 400

            from service.service_compose import update_test_from_compose_session_implementation
            response, status_code = update_test_from_compose_session_implementation(current_user, healing_suggestion.test_id, updated_test_from_req)
            if status_code != 200:
                return response, status_code

            healing_suggestion.updated_test = json.dumps(updated_test_from_req)
            db.session.commit()
        
        # Return updated healing suggestion
        return healing_suggestion.serialize(), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error in update_healing_suggestion_implementation: {str(e)}")
        logger.debug(traceback.print_exc())
        return {"error": str(e)}, 400