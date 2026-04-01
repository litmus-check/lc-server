from flask import jsonify, request, Blueprint, Response
from security.auth import token_required
from log_config.logger import logger
from service.service_suite import *
import traceback
import os
import re
from service.service_credits import check_if_user_has_enough_credits
from utils.utils_constants import ALLOWED_BROWSERS, DEFAULT_BROWSER
from access_control.operation_constants import *

api_suite = Blueprint('api_suite', __name__, url_prefix='/api/v1')

# Route to get all suites with pagination
@api_suite.route('/suites', methods=['GET'])
@token_required(SUITE_GET_ALL)
def get_all_suites(current_user):
    logger.info("Get all suites API called")
    try:
        # Extract pagination parameters from query string
        # Default: page=1, limit=10 items per page
        page = request.args.get('page', 1)
        limit = request.args.get('limit', 10)
        query_filter = request.args.get('query')  # Single query parameter for both name and id
        
        # Call service layer implementation
        response, status_code = get_all_suites_implementation(current_user, page, limit)
        return jsonify(response), status_code
    except Exception as e:
        logger.error(f"Error in get_all_suites: {str(e)}")
        logger.debug(traceback.print_exc())
        return jsonify({"error": "Internal server error"}), 500

# Route to get a specific suite by ID
@api_suite.route('/suite/<string:suite_id>', methods=['GET'])
@token_required(SUITE_GET)
def get_suite(current_user, suite_id):
    logger.info("Get suite API called")
    try:
        # Extract pagination and filter parameters from query string
        page_raw = request.args.get('page')  # None means no pagination
        limit_raw = request.args.get('limit', '10')
        query_filter = request.args.get('query')  # Single query parameter for both name and custom_test_id
        status_filter = request.args.get('status')
        last_run_filter = request.args.get('last_run')

        # Validate pagination parameters (only if page is provided)
        page = None
        try:
            if page_raw is not None:
                page = int(page_raw)
            limit = int(limit_raw)
        except ValueError:
            return jsonify({"error": "page and limit must be integers"}), 400

        if page is not None and (page <= 0 or limit <= 0):
            return jsonify({"error": "page and limit must be positive integers"}), 400

        response, status_code = get_suite_by_id_implementation(
            current_user,
            suite_id,
            page,
            limit,
            query_filter,
            status_filter,
            last_run_filter,
        )
        return jsonify(response), status_code
    except Exception as e:
        logger.error(f"Error in get_suite: {str(e)}")
        logger.debug(traceback.print_exc())
        return jsonify({"error": "Internal server error"}), 500

# Route to create a new suite
@api_suite.route('/suite', methods=['POST'])
@token_required(SUITE_CREATE)
def create_suite(current_user):
    logger.info("Create suite API called")
    try:
        # Extract JSON data from request body
        data = request.get_json()
        # get mode from data
        mode = data.get('mode')
        if mode == 'blank':
            response, status_code = create_suite_implementation(current_user, data)
        else:
            return jsonify({"error": "Invalid mode"}), 400
        return jsonify(response), status_code
    except Exception as e:
        logger.error(f"Error in create_suite: {str(e)}")
        logger.debug(traceback.print_exc())
        return jsonify({"error": "Internal server error"}), 500

# Route to update an existing suite
@api_suite.route('/suite/<string:suite_id>', methods=['PATCH'])
@token_required(SUITE_UPDATE)
def update_suite(current_user, suite_id):
    logger.info("Update suite API called")
    try:
        # Extract JSON data from request body
        data = request.get_json()
        response, status_code = update_suite_implementation(current_user, suite_id, data)
        return jsonify(response), status_code
    except Exception as e:
        logger.error(f"Error in update_suite: {str(e)}")
        logger.debug(traceback.print_exc())
        return jsonify({"error": "Internal server error"}), 500

# Route to delete a suite
@api_suite.route('/suite/<string:suite_id>', methods=['DELETE'])
@token_required(SUITE_DELETE)
def delete_suite(current_user, suite_id):
    logger.info("Delete suite API called")
    try:
        response, status_code = delete_suite_implementation(current_user, suite_id)
        return jsonify(response), status_code
    except Exception as e:
        logger.error(f"Error in delete_suite: {str(e)}")
        logger.debug(traceback.print_exc())
        return jsonify({"error": "Internal server error"}), 500

# Route to run all tests in a suite
@api_suite.route('/suite/<string:suite_id>/run', methods=['POST'])
@token_required(SUITE_RUN)
def run_suite(current_user, suite_id):
    logger.info(f"Run suite API called for suite_id: {suite_id}")
    try:
        browser = request.args.get('browser', default=DEFAULT_BROWSER)
        if browser not in ALLOWED_BROWSERS:
            response = {
                "error": f"Invalid browser type. Allowed browsers are: {', '.join(ALLOWED_BROWSERS)}"
            }
            return jsonify(response), 400
        
        # Extract the request data
        try:
            request_data = request.get_json()
        except:
            response = {
                "error": "Invalid request format. Please ensure request is well-formed JSON"
            }
            return jsonify(response), 400
        
        response, status_code = run_suite_implementation(current_user, suite_id, browser, request_data)
        return jsonify(response), status_code
    except Exception as e:
        logger.error(f"Error in run_suite: {str(e)}")
        logger.debug(traceback.print_exc())
        return jsonify({"error": "Internal server error"}), 500
    
@api_suite.route('/suite/<string:suite_id>/runs', methods=['GET'])
@token_required(SUITERUN_GET_BY_SUITE)
def get_suite_runs(current_user, suite_id):
    logger.info(f"Get suite runs API called for suite_id: {suite_id}")
    try:
        page_num = request.args.get('page', default=1, type=int)
        limit = request.args.get('limit', default=10, type=int)
        response, status_code = get_suite_runs_implementation(current_user, suite_id, page_num, limit)
        return jsonify(response), status_code
    except Exception as e:
        logger.error(f"Error in get_suite_runs: {str(e)}")
        logger.debug(traceback.print_exc())
        return jsonify({"error": "Internal server error"}), 500
    
@api_suite.route('/suite/<string:suite_id>/run/<string:suite_run_id>', methods=['GET'])
@token_required(SUITERUN_GET)
def get_suite_run_by_id(current_user, suite_id, suite_run_id):
    logger.info(f"Get suite run by ID API called for suite_run_id: {suite_run_id}")
    try:
        page_num = request.args.get('page', default=1, type=int)
        limit = request.args.get('limit', default=10, type=int)
        response, status_code = get_suite_run_by_id_implementation(current_user, suite_id, suite_run_id, page_num, limit)
        return jsonify(response), status_code
    except Exception as e:
        logger.error(f"Error in get_suite_run_by_id: {str(e)}")
        logger.debug(traceback.print_exc())
        return jsonify({"error": "Internal server error"}), 500

# Route to upload file to a suite
@api_suite.route('/suite/<string:suite_id>/file', methods=['POST'])
@token_required(SUITE_FILE_CREATE)
def upload_suite_file(current_user, suite_id):
    logger.info(f"Upload suite file API called for suite_id: {suite_id}")
    try:
        # Check if file is present in request
        if 'file' not in request.files:
            return jsonify({"error": "No file provided"}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({"error": "No file provided"}), 400
        
        # Get type from form data or query parameters
        file_type = request.args.get('type')
        
        response, status_code = upload_suite_file_implementation(current_user, suite_id, file, file_type)
        return jsonify(response), status_code
    except Exception as e:
        logger.error(f"Error in upload_suite_file: {str(e)}")
        logger.debug(traceback.print_exc())
        return jsonify({"error": "Internal server error"}), 500

# Route to get all files for a suite
@api_suite.route('/suite/<string:suite_id>/files', methods=['GET'])
@token_required(SUITE_FILE_GET_BY_SUITE)
def get_suite_files(current_user, suite_id):
    logger.info(f"Get suite files API called for suite_id: {suite_id}")
    try:
        # Get type filter from query parameters
        file_type = request.args.get('type')
        
        response, status_code = get_suite_files_implementation(current_user, suite_id, file_type)
        return jsonify(response), status_code
    except Exception as e:
        logger.error(f"Error in get_suite_files: {str(e)}")
        logger.debug(traceback.print_exc())
        return jsonify({"error": "Internal server error"}), 500

# Delete file from a suite
@api_suite.route('/suite/<string:suite_id>/file/<string:file_id>', methods=['DELETE'])
@token_required(SUITE_FILE_DELETE)
def delete_suite_file(current_user, suite_id, file_id):
    logger.info(f"Delete suite file API called for suite_id: {suite_id} and file_id: {file_id}")
    try:
        response, status_code = delete_suite_file_implementation(current_user, suite_id, file_id)
        return jsonify(response), status_code
    except Exception as e:
        logger.error(f"Error in delete_suite_file: {str(e)}")
        logger.debug(traceback.print_exc())
        return jsonify({"error": "Internal server error"}), 500

# Update file from a suite
@api_suite.route('/suite/<string:suite_id>/file/<string:file_id>', methods=['PUT'])
@token_required(SUITE_FILE_UPDATE)
def update_suite_file(current_user, suite_id, file_id):
    logger.info(f"Update suite file API called for suite_id: {suite_id} and file_id: {file_id}")
    try:
        # Check if file is present in request
        if 'file' not in request.files:
            return jsonify({"error": "No file provided"}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({"error": "No file provided"}), 400

        # Get type from form data or query parameters
        file_type = request.args.get('type')

        response, status_code = update_suite_file_implementation(current_user, suite_id, file_id, file, file_type)
        return jsonify(response), status_code
    except Exception as e:
        logger.error(f"Error in update_suite_file: {str(e)}")
        logger.debug(traceback.print_exc())
        return jsonify({"error": "Internal server error"}), 500

# Get file from a suite
@api_suite.route('/suite/<string:suite_id>/file/<string:file_id>', methods=['GET'])
@token_required(SUITE_FILE_GET)
def get_suite_file(current_user, suite_id, file_id):
    logger.info(f"Get suite file API called for suite_id: {suite_id} and file_id: {file_id}")
    try:
        response, status_code = get_suite_file_implementation(current_user, suite_id, file_id)
        return jsonify(response), status_code
    except Exception as e:
        logger.error(f"Error in get_suite_file: {str(e)}")
        logger.debug(traceback.print_exc())
        return jsonify({"error": "Internal server error"}), 500

# Download file from a suite
@api_suite.route('/suite/<string:suite_id>/file/<string:file_id>/download', methods=['GET'])
@token_required(SUITE_FILE_DOWNLOAD)
def download_suite_file(current_user, suite_id, file_id):
    logger.info(f"Download suite file API called for suite_id: {suite_id} and file_id: {file_id}")
    try:
        response, status_code = download_suite_file_implementation(current_user, suite_id, file_id)
        return jsonify(response), status_code
    except Exception as e:
        logger.error(f"Error in download_suite_file: {str(e)}")
        logger.debug(traceback.print_exc())
        return jsonify({"error": "Internal server error"}), 500

# Get all tags in a suite
@api_suite.route('/suite/<string:suite_id>/tags', methods=['GET'])
@token_required(SUITE_GET_TAGS)
def get_suite_tags(current_user, suite_id):
    logger.info(f"Get suite tags API called for suite_id: {suite_id}")
    try:
        response, status_code = get_suite_tags_implementation(current_user, suite_id)
        return jsonify(response), status_code
    except Exception as e:
        logger.error(f"Error in get_suite_tags: {str(e)}")
        logger.debug(traceback.print_exc())
        return jsonify({"error": "Internal server error"}), 500
# Get healing suggestions for a suite
@api_suite.route('/suite/<string:suite_id>/run/<string:suite_run_id>/healing_suggestions', methods=['GET'])
@token_required(HEALING_SUGGESTION_GET_BY_SUITERUN)
def get_healing_suggestions(current_user, suite_id, suite_run_id):
    logger.info(f"Get healing suggestions API called for suite_id: {suite_id}, suite_run_id: {suite_run_id}")
    try:
        response, status_code = get_healing_suggestions_by_suite_implementation(current_user, suite_id, suite_run_id)
        return jsonify(response), status_code
    except Exception as e:
        logger.error(f"Error in get_healing_suggestions: {str(e)}")
        logger.debug(traceback.print_exc())
        return jsonify({"error": "Internal server error"}), 500

# Update healing suggestion status
@api_suite.route('/suite/<string:suite_id>/healing_suggestions/<string:healing_suggestion_id>', methods=['PUT'])
@token_required(HEALING_SUGGESTION_UPDATE)
def update_healing_suggestion(current_user, suite_id, healing_suggestion_id):
    logger.info(f"Update healing suggestion API called for suite_id: {suite_id}, healing_suggestion_id: {healing_suggestion_id}")
    try:
        # Extract JSON data from request body
        data = request.get_json()
        response, status_code = update_healing_suggestion_implementation(current_user, suite_id, healing_suggestion_id, data)
        return jsonify(response), status_code
    except Exception as e:
        logger.error(f"Error in update_healing_suggestion: {str(e)}")
        logger.debug(traceback.print_exc())
        return jsonify({"error": "Internal server error"}), 500