from flask import Blueprint, request, jsonify
from models.Test import Test
from database import db
from security.auth import token_required
from log_config.logger import logger
from service.service_compose import *
from service.service_credits import check_if_user_has_enough_credits
from access_control.operation_constants import *

api_compose = Blueprint('api_compose', __name__, url_prefix='/api/v1')

@api_compose.route('/compose', methods=['POST'])
@token_required(COMPOSE_CREATE)
def create_compose_session(current_user):
    logger.info("Create compose session API called")
    try:
        # Get environment query parameter, default to 'browserbase' if not provided
        environment = request.args.get('environment', 'browserbase')

        # Extract the request data
        try:
            request_data = request.get_json()
        except Exception as e:
            logger.error(f"Invalid request data: {str(e)}")
            return jsonify({'error': 'Invalid request data'}), 400

        # Create a new compose session
        response, status_code = create_compose_session_implemenation(current_user, environment, request_data)
        return jsonify(response), status_code
    except Exception as e:
        logger.error(f"Error in create_compose_session: {str(e)}")
        return jsonify({'error': str(e)}), 500

@api_compose.route('/compose/<compose_id>/run', methods=['POST'])
@token_required(COMPOSE_RUN)
def run_instructions_one_by_one(current_user, compose_id):
    logger.info("Run instructions one by one API called")
    try:
        try:
            request_data = request.get_json()
            environment = request.args.get('environment', 'browserbase')
        except Exception as e:
            logger.error(f"Invalid request data: {str(e)}")
            return jsonify({'error': 'Invalid request data'}), 400
        
        response, status_code = run_instructions_one_by_one_implementation(current_user, compose_id, request_data, environment)
        return jsonify(response), status_code
    except Exception as e:
        logger.error(f"Error running compose: {str(e)}")
        logger.debug(traceback.format_exc())
        return jsonify({'error': str(e)}), 500
    
@api_compose.route('/compose/<compose_id>', methods=['GET'])
@token_required(COMPOSE_GET)
def get_compose_status(current_user, compose_id):
    logger.info("Get compose status API called")
    instruction_id = request.args.get('id')
    if instruction_id is None:
        return jsonify({'error': 'Instruction ID is required'}), 400
    if instruction_id == 'all':
        response = get_compose_session_from_redis(compose_id)
        return jsonify(response), 200
    response, status_code = get_compose_status_implementation(compose_id, instruction_id)
    return jsonify(response), status_code

# Close compose session
@api_compose.route('/compose/<compose_id>', methods=['DELETE'])
@token_required(COMPOSE_CLOSE)
def close_compose_session(current_user, compose_id):
    logger.info("Close compose session API called")
    response, status_code = close_compose_session_implementation(current_user, compose_id)
    return jsonify(response), status_code

# Send live URLs
@api_compose.route('/compose/<compose_id>/live_urls', methods=['GET'])
@token_required(COMPOSE_GET_LIVE_URLS)
def send_live_urls(current_user, compose_id):
    logger.info("Send live URLs API called")
    response, status_code = send_live_urls_implementation(current_user, compose_id)
    return jsonify(response), status_code
