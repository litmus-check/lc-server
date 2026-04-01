from flask import jsonify, request, Blueprint
from security.auth import token_required
from log_config.logger import logger
from service.service_notif_config import *
import traceback
from access_control.operation_constants import *

api_notification = Blueprint('api_notification', __name__, url_prefix='/api/v1')

# Route to get recipients for a suite
@api_notification.route('/suite/<string:suite_id>/recipients', methods=['GET'])
@token_required(NOTIFICATION_RECIPIENTS_GET_BY_SUITE)
def get_recipients(current_user, suite_id):
    logger.info(f"Get recipients API called for suite_id: {suite_id}")
    try:
        response, status_code = get_recipients_implementation(current_user, suite_id)
        return jsonify(response), status_code
    except Exception as e:
        logger.error(f"Error in get_recipients: {str(e)}")
        logger.debug(traceback.print_exc())
        return jsonify({"error": "Internal server error"}), 500

# Route to create recipients for a suite
@api_notification.route('/suite/<string:suite_id>/recipients', methods=['POST'])
@token_required(NOTIFICATION_RECIPIENTS_CREATE)
def create_recipients(current_user, suite_id):
    logger.info(f"Create recipients API called for suite_id: {suite_id}")
    try:
        # Extract JSON data from request body
        data = request.get_json()
        if not data:
            return jsonify({"error": "Request body is required"}), 400
        
        response, status_code = create_recipients_implementation(current_user, suite_id, data)
        return jsonify(response), status_code
    except Exception as e:
        logger.error(f"Error in create_recipients: {str(e)}")
        logger.debug(traceback.print_exc())
        return jsonify({"error": "Internal server error"}), 500

# Route to update recipients for a suite
@api_notification.route('/suite/<string:suite_id>/recipients', methods=['PUT'])
@token_required(NOTIFICATION_RECIPIENTS_UPDATE)
def update_recipients(current_user, suite_id):
    logger.info(f"Update recipients API called for suite_id: {suite_id}")
    try:
        # Extract JSON data from request body
        data = request.get_json()
        if not data:
            return jsonify({"error": "Request body is required"}), 400
        
        response, status_code = update_recipients_implementation(current_user, suite_id, data)
        return jsonify(response), status_code
    except Exception as e:
        logger.error(f"Error in update_recipients: {str(e)}")
        logger.debug(traceback.print_exc())
        return jsonify({"error": "Internal server error"}), 500
