from flask import jsonify, request, Blueprint
from security.auth import token_required
from log_config.logger import logger
from service.service_environment import *
import traceback
from access_control.operation_constants import *

api_environment = Blueprint('api_environment', __name__, url_prefix='/api/v1')

# Route to create a new environment
@api_environment.route('/environment', methods=['POST'])
@token_required(ENVIRONMENT_CREATE)
def create_environment(current_user):
    logger.info("Create environment API called")
    try:
        # Extract JSON data from request body
        try:
            data = request.get_json()
        except Exception as e:
            logger.error(f"Invalid request data: {str(e)}")
            return jsonify({'error': 'Invalid request data. Please ensure request is well-formed JSON'}), 400
        
        if not data:
            return jsonify({"error": "Request body is required"}), 400
        
        response, status_code = create_environment_implementation(current_user, data)
        return jsonify(response), status_code
    except Exception as e:
        logger.error(f"Error in create_environment: {str(e)}")
        logger.debug(traceback.print_exc())
        return jsonify({"error": "Internal server error"}), 500

# Route to get a specific environment by ID
@api_environment.route('/environment/<string:environment_id>', methods=['GET'])
@token_required(ENVIRONMENT_GET)
def get_environment(current_user, environment_id):
    logger.info(f"Get environment API called for environment_id: {environment_id}")
    try:
        response, status_code = get_environment_by_id_implementation(current_user, environment_id)
        return jsonify(response), status_code
    except Exception as e:
        logger.error(f"Error in get_environment: {str(e)}")
        logger.debug(traceback.print_exc())
        return jsonify({"error": "Internal server error"}), 500

# Route to get all environments for a specific suite
@api_environment.route('/environment/suite/<string:suite_id>', methods=['GET'])
@token_required(ENVIRONMENT_GET_BY_SUITE)
def get_environments_by_suite(current_user, suite_id):
    logger.info(f"Get environments by suite API called for suite_id: {suite_id}")
    try:
        response, status_code = get_environments_by_suite_implementation(current_user, suite_id)
        return jsonify(response), status_code
    except Exception as e:
        logger.error(f"Error in get_environments_by_suite: {str(e)}")
        logger.debug(traceback.print_exc())
        return jsonify({"error": "Internal server error"}), 500

# Route to update an existing environment
@api_environment.route('/environment/<string:environment_id>', methods=['PUT'])
@token_required(ENVIRONMENT_UPDATE)
def update_environment(current_user, environment_id):
    logger.info(f"Update environment API called for environment_id: {environment_id}")
    try:
        # Extract JSON data from request body
        try:
            data = request.get_json()
        except Exception as e:
            logger.error(f"Invalid request data: {str(e)}")
            return jsonify({'error': 'Invalid request data. Please ensure request is well-formed JSON'}), 400
        
        if not data:
            return jsonify({"error": "Request body is required"}), 400
        
        response, status_code = update_environment_implementation(current_user, environment_id, data)
        return jsonify(response), status_code
    except Exception as e:
        logger.error(f"Error in update_environment: {str(e)}")
        logger.debug(traceback.print_exc())
        return jsonify({"error": "Internal server error"}), 500

# Route to delete an environment
@api_environment.route('/environment/<string:environment_id>', methods=['DELETE'])
@token_required(ENVIRONMENT_DELETE)
def delete_environment(current_user, environment_id):
    logger.info(f"Delete environment API called for environment_id: {environment_id}")
    try:
        response, status_code = delete_environment_implementation(current_user, environment_id)
        return jsonify(response), status_code
    except Exception as e:
        logger.error(f"Error in delete_environment: {str(e)}")
        logger.debug(traceback.print_exc())
        return jsonify({"error": "Internal server error"}), 500
