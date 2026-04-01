from flask import jsonify, request, Blueprint
from security.auth import token_required
from log_config.logger import logger
from service.service_org_queue_config import update_org_rate_limit_implementation, get_org_rate_limit_implementation
import traceback
from access_control.operation_constants import ORG_RATE_LIMIT_GET, ORG_RATE_LIMIT_UPDATE
from access_control.roles import ADMIN

api_org_queue_config = Blueprint('api_org_queue_config', __name__, url_prefix='/api/v1')

@api_org_queue_config.route('/org/<string:org_id>/rate_limit', methods=['PUT'])
@token_required(ORG_RATE_LIMIT_UPDATE)
def update_org_rate_limit(current_user, org_id):
    logger.info(f"Update org rate limit API called for org_id: {org_id}")
    try:
        # Check if user is admin
        user_role = current_user.get('role')
        if user_role != ADMIN:
            logger.warning(f"Non-admin user attempted to update rate limit. User role: {user_role}")
            return jsonify({"error": "Only admin users can update rate limits"}), 403
        try:
            data = request.get_json()
        except Exception as e:
            logger.error(f"Invalid request data: {str(e)}")
            return jsonify({'error': 'Invalid request data. Please ensure request is well-formed JSON'}), 400

        if not data:
            return jsonify({"error": "Request body is required"}), 400

        new_rate_limit = data.get('rate_limit')
        if new_rate_limit is None:
            return jsonify({"error": "rate_limit is required"}), 400

        response, status_code = update_org_rate_limit_implementation(org_id, new_rate_limit)
        return jsonify(response), status_code
    except Exception as e:
        logger.error(f"Error in update_org_rate_limit: {str(e)}")
        logger.debug(traceback.print_exc())
        return jsonify({"error": "Internal server error"}), 500


@api_org_queue_config.route('/org/<string:org_id>/rate_limit', methods=['GET'])
@token_required(ORG_RATE_LIMIT_GET)
def get_org_rate_limit(current_user, org_id):
    logger.info(f"Get org rate limit API called for org_id: {org_id}")
    try:
        response, status_code = get_org_rate_limit_implementation(current_user, org_id)
        return jsonify(response), status_code
    except Exception as e:
        logger.error(f"Error in get_org_rate_limit: {str(e)}")
        logger.debug(traceback.print_exc())
        return jsonify({"error": "Internal server error"}), 500


