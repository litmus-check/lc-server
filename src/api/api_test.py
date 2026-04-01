from security.auth import *
from service.service_test import *
from service.service_compose import *
from log_config.logger import logger
from flask import Blueprint, request, jsonify, Response
from service.service_credits import check_if_user_has_enough_credits
from access_control.operation_constants import *


api_test = Blueprint('api_test',__name__, url_prefix='/api/v1')

@api_test.route('/test/<string:id>/run', methods=['POST'])
@token_required(TEST_RUN)
def test_run(current_user, id):
    logger.info("Test run API called")
    try:
        # Extract the request data
        try:
            request_data = request.get_json()
        except:
            response = {
                "error": "Invalid request format. Please ensure request is well-formed JSON"
            }
            return jsonify(response), 400

        browser_env = request.args.get('browser', LITMUS_CLOUD_ENV)
        if browser_env not in ALLOWED_BROWSER_ENVS:
            response = {
                "error": f"Invalid browser type. Allowed browsers are: {', '.join(ALLOWED_BROWSER_ENVS)}"
            }
            return jsonify(response), 400
        
        response, status_code = run_test_implementation(current_user, id, browser_env, run_mode=SCRIPT_MODE, request_data=request_data)
        return jsonify(response), status_code
    except Exception as e:
        logger.error(f"Error in run_test: {str(e)}")
        response = {
            "error": "Internal server error"
        }
        return jsonify(response), 500
    
# Run test in ai mode explicitly
@api_test.route('/test/<string:id>/run/ai', methods=['POST'])
@token_required(TEST_RUN_AI)
def test_run_ai(current_user, id):
    logger.info("Test run AI API called")
    try:
        browser = request.args.get('browser', DEFAULT_BROWSER)
        if browser not in ALLOWED_BROWSERS:
            response = {
                "error": f"Invalid browser type. Allowed browsers are: {', '.join(ALLOWED_BROWSERS)}"
            }
            return jsonify(response), 400
        response, status_code = run_test_implementation(current_user, id, browser, run_mode=AI_MODE)
        return jsonify(response), status_code
    except Exception as e:
        logger.error(f"Error in run_test_ai: {str(e)}")
        response = {
            "error": "Internal server error"
        }
        return jsonify(response), 500
    
# Create test API
@api_test.route('/test', methods=['POST'])
@token_required(TEST_CREATE)
def create_test(current_user):
    logger.info("Create test API called")
    try:
        try:
            request_data = request.get_json()
        except:
            response = {
                "error": "Invalid request format. Please ensure request is well-formed JSON"
            }
            return jsonify(response), 400
        
        response, status_code = create_test_implementation(current_user, request_data)
        return jsonify(response), status_code
    except Exception as e:
        logger.error(f"Error in create_test: {str(e)}")
        response = {
            "error": "Internal server error"
        }
        return jsonify(response), 500

# Update test API
@api_test.route('/test/<string:id>', methods=['PUT'])
@token_required(TEST_UPDATE)
def update_test(current_user, id):
    logger.info("Update test API called")
    try:
        try:
            request_data = request.get_json()
        except:
            response = {
                "error": "Invalid request format. Please ensure request is well-formed JSON"
            }
            return jsonify(response), 400
        
        response, status_code = update_test_implementation(current_user, request_data, id)
        return jsonify(response), status_code
    except Exception as e:
        logger.error(f"Error in update_test: {str(e)}")
        response = {
            "error": "Internal server error"
        }
        return jsonify(response), 500
    
# Delete test API
@api_test.route('/test/<string:id>', methods=['DELETE'])
@token_required(TEST_DELETE)
def delete_test(current_user, id):
    logger.info("Delete test API called")
    try:
        response, status_code = delete_test_implementation(current_user, id)
        return jsonify(response), status_code
    except Exception as e:
        logger.error(f"Error in delete_test: {str(e)}")
        response = {
            "error": "Internal server error"
        }
        return jsonify(response), 500
    
# Get test API
@api_test.route('/test/<string:id>', methods=['GET'])
@token_required(TEST_GET)
def get_test(current_user, id):
    logger.info("Get test API called")
    try:
        response, status_code = get_test_by_id_implementation(current_user, id)
        return jsonify(response), status_code
    except Exception as e:
        logger.error(f"Error in get_test: {str(e)}")
        response = {
            "error": "Internal server error"
        }
        return jsonify(response), 500
    
# Get all tests API
@api_test.route('/tests', methods=['GET'])
@token_required(TEST_GET_ALL)
def get_all_tests(current_user):
    logger.info("Get all tests API called")
    try:
        page_num = request.args.get('page', 1)
        limit = request.args.get('limit', 10)
        response, status_code = get_all_tests_implementation(current_user, page_num, limit)
        return jsonify(response), status_code
    except Exception as e:
        logger.error(f"Error in get_all_tests: {str(e)}")
        response = {
            "error": "Internal server error"
        }
        return jsonify(response), 500

@api_test.route('/live/<string:testrun_id>', methods=['GET'])
@token_required(TESTRUN_GET_LIVE_URLS)
def get_live_stream_urls(current_user, testrun_id):
    """
    Get Browserbase debug URLs for a specific test run.
    """
    try:
       
        # Get the live stream url from Redis
        live_stream_url = get_browserbase_urls(f"{testrun_id}_live_stream")
        if not live_stream_url:
            return jsonify({"error": "Live stream URL not available for this session"}), 404
            
        # return the live stream url
        return jsonify({ "live_stream_url": live_stream_url}), 200
    except Exception as e:
        logger.error(f"Error getting live stream URLs: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500

# Get test instructions as script file API
@api_test.route('/test/<string:id>/script', methods=['GET'])
@token_required(TEST_GET_SCRIPT)
def get_test_script(current_user, id):
    logger.info("Get test script API called")
    try:
        response, status_code = get_playwright_script_implementation(current_user, id)
        if status_code != 200:
            return jsonify(response), status_code
        
        # Extract script content and test name from response
        script_content = response.get('script_content')
        test_name = response.get('test_name', f'test_{id}')
        
        # Check if script_content is valid
        if not script_content:
            logger.error("Script content is empty or None")
            return jsonify({"error": "Script content is empty"}), 500
        
        # Clean the test name to be a valid filename
        import re
        clean_test_name = re.sub(r'[^\w\-_\.]', '_', test_name)
        
        # Return the script file
        logger.info(f"Test name: {test_name}, Clean name: {clean_test_name}")
        logger.info(f"Status code: {status_code}")
        return Response(
            script_content,
            status=status_code,
            mimetype='text/plain',
            headers={
                'Content-Disposition': f'attachment; filename={clean_test_name}.test.js'
            }
        )

    except Exception as e:
        logger.error(f"Error in get_test_script: {str(e)}")
        response = {
            "error": "Internal server error"
        }
        return jsonify(response), 500

# Create test from compose session
@api_test.route('/test/compose', methods=['POST'])
@token_required(TEST_CREATE_FROM_COMPOSE)
def create_test_from_compose_session(current_user):
    logger.info("Create test from compose session API called")
    try:
        try:
            request_data = request.get_json()
        except:
            response = {
                "error": "Invalid request format. Please ensure request is well-formed JSON"
            }
            return jsonify(response), 400

        response, status_code = create_test_from_compose_session_implementation(current_user, request_data)

        # Check if kill session is true
        if request.args.get('kill_compose_session', 'false').lower() == "true":
            compose_id = request.args.get('compose_id')
            if not compose_id:
                response = {
                    "error": "Compose ID is required to kill the session"
                }
                return jsonify(response), 400
            kill_session_response, kill_session_status_code = close_compose_session_implementation(current_user, compose_id)
           
        return jsonify(response), status_code
    except Exception as e:
        logger.error(f"Error in create_test_from_compose_session: {str(e)}")
        response = {
            "error": "Internal server error"
        }
        return jsonify(response), 500

# Update test from compose session
@api_test.route('/test/<string:test_id>/compose', methods=['PUT'])
@token_required(TEST_UPDATE_FROM_COMPOSE)
def update_test_from_compose_session(current_user, test_id):
    logger.info("Update test from compose session API called")
    try:
        try:
            request_data = request.get_json()
        except:
            response = {
                "error": "Invalid request format. Please ensure request is well-formed JSON"
            }
            return jsonify(response), 400
        response, status_code = update_test_from_compose_session_implementation(current_user, test_id, request_data)

        # Check if kill session is true
        if request.args.get('kill_compose_session', 'false').lower() == "true":
            compose_id = request.args.get('compose_id')
            if not compose_id:
                response = {
                    "error": "Compose ID is required to kill the session"
                }
                return jsonify(response), 400
            kill_session_response, kill_session_status_code = close_compose_session_implementation(current_user, compose_id)

        return jsonify(response), status_code
    except Exception as e:
        logger.error(f"Error in update_test_from_compose_session: {str(e)}")
        response = {
            "error": "Internal server error"
        }
        return jsonify(response), 500

