import json
import uuid
import traceback
from flask import jsonify
from database import db
from models.Suite import Suite
from models.Test import Test
from utils.test_plan_generator import generate_test_plan
from service.service_test import validate_description_word_limit
from service.service_suite import return_suite_obj
from service.service_credits import update_credits
from log_config.logger import logger
from sqlalchemy.orm import joinedload
from utils.utils_constants import TEST_STATUS_DRAFT, AI_CREDIT_UNIT

def generate_test_suggestions_implementation(current_user, request_data):
    """
    Generate test suggestions for a suite based on feature description
    
    Args:
        request_data: Request data containing suite_id and feature_description
        
    Returns:
        tuple: (response_dict, status_code)
    """
    try:
        suite_obj = return_suite_obj(current_user, request_data.get('suite_id'))
        if not suite_obj:
            return {"error": "Suite not found or user does not have access to it"}, 404
        
        suite_id = suite_obj.suite_id
        feature_description = request_data.get('plan_description') or request_data.get('feature_description')
        
        if not feature_description:
            return {"error": "Plan description is required"}, 400
        
        # Get existing tests for the suite
        existing_tests = Test.query.filter_by(suite_id=suite_id).all()
        suite_data = {
            'suite_id': suite_id,
            'name': suite_obj.name,
            'description': suite_obj.description,
            'tests': [test.serialize() for test in existing_tests]
        }
        
        # Generate test suggestions using generator
        result = generate_test_plan(
            suite_data=suite_data,
            feature_description=feature_description
        )
        
        if 'error' in result:
            return result, 400
        
        # Reduce AI credit after successful LLM call
        try:
            org_id = suite_obj.org_id
            if org_id is None:
                # TODO: Return error when strict credit validation is enabled
                logger.error(f"Org ID is None for suite {suite_id}, skipping credit reduction")
            else:
                update_credits(org_id, ai_credits=AI_CREDIT_UNIT)
                logger.info(f"Reduced {AI_CREDIT_UNIT} AI credit(s) for org {org_id} after successful test plan generation")
        except Exception as credit_error:
            logger.error(f"Error reducing AI credits: {str(credit_error)}")
            logger.debug(traceback.format_exc())
            # Don't fail the request if credit reduction fails, but log the error
        
        # Format response to match contract
        response = {
            "tests": result.get('test_suggestions', [])
        }
        
        return response, 200
        
    except Exception as e:
        logger.error(f"Error generating test suggestions: {str(e)}")
        logger.debug(traceback.format_exc())
        return {"error": f"Failed to generate test suggestions: {str(e)}"}, 500

def create_bulk_tests_implementation(current_user, request_data):
    """
    Create multiple tests in bulk for a suite
    
    Args:
        request_data: Request data containing suite_id and tests array
        
    Returns:
        tuple: (response_dict, status_code)
    """
    try:
        suite_obj = return_suite_obj(current_user, request_data.get('suite_id'))
        if not suite_obj:
            return {"error": "Suite not found or user does not have access to it"}, 404
        
        suite_id = suite_obj.suite_id
        tests = request_data.get('tests', [])
        
        if not tests or not isinstance(tests, list):
            return {"error": "Tests array is required and must be a list"}, 400
        
        if len(tests) == 0:
            return {"error": "At least one test must be provided"}, 400
        
        
        # Create test objects
        created_tests = []
        for i, test_data in enumerate(tests):
            try:
                if not isinstance(test_data, dict):
                    logger.warning(f"Skipping invalid test data at index {i}: {test_data}")
                    continue
                
                test_name = test_data.get('name', f'Generated Test {i + 1}')
                test_description = test_data.get('description', '')
                
                logger.info(f"Creating test {i + 1}: {test_name}")
                
                # Validate description word limit
                error_message, status_code = validate_description_word_limit(test_description)
                if status_code != 200:
                    logger.warning(f"Test description exceeds word limit, truncating: {test_name}")
                    # Truncate description to 200 words
                    words = test_description.split()
                    if len(words) > 200:
                        test_description = ' '.join(words[:200]) + "..."
                
                # Create test object
                test_obj = Test(
                    id=str(uuid.uuid4()),
                    name=test_name,
                    description=test_description,
                    suite_id=suite_id,
                    instructions=json.dumps([]),  # Empty instructions for draft tests
                    status=TEST_STATUS_DRAFT
                )
                
                db.session.add(test_obj)
                created_tests.append({
                    'id': test_obj.id,
                    'name': test_obj.name,
                    'description': test_obj.description
                })
                
            except Exception as test_error:
                logger.error(f"Error creating test {i + 1}: {str(test_error)}")
                logger.debug(traceback.format_exc())
                continue
        
        if not created_tests:
            return {"error": "No valid tests were created"}, 400
        
        db.session.commit()
        
        return {
            "suite_id": suite_id,
            "tests": created_tests
        }, 200
        
    except Exception as e:
        logger.error(f"Error creating bulk tests: {str(e)}")
        logger.debug(traceback.format_exc())
        db.session.rollback()
        return {"error": "Internal server error"}, 500

