from security.auth import *
from service.service_test_plan import *
from log_config.logger import logger
from flask import Blueprint, request, jsonify
from access_control.operation_constants import *
from service.service_credits import check_if_user_has_enough_ai_credits

api_test_plan = Blueprint('api_test_plan', __name__, url_prefix='/api/v1')

@api_test_plan.route('/suite/<string:suite_id>/test_plan', methods=['POST'])
@token_required(TEST_PLAN_GENERATE)
def generate_test_plans(current_user, suite_id):
    """
    Generate test plans for a suite based on feature description
    
    Request body:
    {
        "plan_description": "string"
    }
    
    Response:
    {
        "tests": [
            {
                "name": "Test Name",
                "description": "Test Description"
            }
        ]
    }
    """
    logger.info(f"Generate test plans API called for suite: {suite_id}")
    try:
        try:
            request_data = request.get_json()
        except:
            response = {
                "error": "Invalid request format. Please ensure request is well-formed JSON"
            }
            return jsonify(response), 400

        # Check if the org that owns the suite has enough AI credits
        try:
            credits_check_resp, status_code = check_if_user_has_enough_ai_credits(suite_id=suite_id)
            if status_code != 200:
                return jsonify(credits_check_resp), status_code
        except Exception as e:
            logger.error(f"Error checking AI credits: {e}")
            return jsonify({"error": "Failed to check AI credits"}), 500
        
        
        # Add suite_id to request data
        request_data['suite_id'] = suite_id
        response, status_code = generate_test_suggestions_implementation(current_user, request_data)
        return jsonify(response), status_code
        
    except Exception as e:
        logger.error(f"Error in generate_test_plan: {str(e)}")
        response = {
            "error": f"Failed to generate test plan: {str(e)}"
        }
        return jsonify(response), 500

@api_test_plan.route('/suite/<string:suite_id>/bulk_tests', methods=['POST'])
@token_required(TEST_PLAN_CREATE_BULK_TESTS)
def create_bulk_tests(current_user, suite_id):
    """
    Create multiple tests in bulk for a suite
    
    Request body:
    {
        "tests": [
            {
                "name": "Test Name 1",
                "description": "Test description 1"
            },
            {
                "name": "Test Name 2", 
                "description": "Test description 2"
            }
        ]
    }
    
    Response:
    {
        "suite_id": "suite_id",
        "tests": [
            {
                "id": "uuid_1",
                "name": "Test Name 1",
                "description": "Test description 1"
            }
        ]
    }
    """
    logger.info(f"Create bulk tests API called for suite: {suite_id}")
    try:
        try:
            request_data = request.get_json()
        except:
            response = {
                "error": "Invalid request format. Please ensure request is well-formed JSON"
            }
            return jsonify(response), 400
        
        
        # Add suite_id to request data
        request_data['suite_id'] = suite_id
        
        response, status_code = create_bulk_tests_implementation(current_user, request_data)
        return jsonify(response), status_code
        
    except Exception as e:
        logger.error(f"Error in create_bulk_tests: {str(e)}")
        response = {
            "error": f"Failed to add tests to suite: {str(e)}"
        }
        return jsonify(response), 500
