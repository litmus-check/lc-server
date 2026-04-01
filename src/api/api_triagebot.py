from flask import jsonify, request, Blueprint
from security.auth import token_required
from log_config.logger import logger
from service.service_triage_cli_agent import triage_cli_agent_implementation
import traceback
from access_control.operation_constants import *
from models.CliActivity import CliActivity
from database import db
from access_control.roles import ADMIN

api_triagebot = Blueprint('api_triagebot', __name__, url_prefix='/api/v1')

@api_triagebot.route('/pw/triage', methods=['POST'])
@token_required(PLAYWRIGHT_TRIAGE)
def triage(current_user):
    logger.info("Triage API called")
    try:
        logger.info(f"Triage request from {current_user.get('org_id')}")
        
        # Increment CLI activity triage calls (wrapped in try-catch to ignore failures)
        try:
            org_id = current_user.get('org_id')
            user_identity = current_user.get('email') or current_user.get('user_id')
            if org_id and user_identity:
                cli_activity = CliActivity.query.filter_by(org_id=org_id, apikey_name=user_identity).first()
                if cli_activity:
                    cli_activity.triage_calls += 1
                else:
                    cli_activity = CliActivity(org_id=org_id, apikey_name=user_identity, triage_calls=1)
                    db.session.add(cli_activity)
                db.session.commit()
        except Exception as e:
            logger.warning(f"Failed to increment CLI activity triage calls: {str(e)}")
            db.session.rollback()
        
        try:
            request_data = request.get_json()
        except Exception as e:
            logger.error(f"Invalid triage request: {str(e)} sent by {current_user.get('org_id')}")
            return jsonify({'error': 'Invalid request data. Please ensure request is well-formed JSON'}), 400
        
        if not request_data:
            logger.error(f"Invalid triage request: Request body is required sent by {current_user.get('org_id')}")
            return jsonify({"error": "Request body is required"}), 400
        

        # TODO: Add a check to see if the request is coming from a valid source
        response, status_code = triage_cli_agent_implementation(current_user, request_data)
        return jsonify(response), status_code
    except Exception as e:
        logger.error(f"Error in triage: {str(e)}")
        logger.debug(traceback.format_exc())
        return jsonify({"error": "Unable to complete triaging"}), 500


@api_triagebot.route('/pw/triage/activity', methods=['GET'])
@token_required(TRIAGE_GET_ACTIVITY)
def get_cli_activity(current_user):
    """Admin API to get all CLI activity entries"""
    logger.info("Get CLI activity API called")
    try:
        # Check if user is admin
        user_role = current_user.get('role')
        if user_role != ADMIN:
            logger.warning(f"Non-admin user attempted to access CLI activity. User role: {user_role}")
            return jsonify({"error": "Only admin users can access CLI activity"}), 403
        
        cli_activities = CliActivity.query.all()
        return jsonify({
            'data': [activity.serialize() for activity in cli_activities],
            'count': len(cli_activities)
        }), 200
    except Exception as e:
        logger.error(f"Error in get_cli_activity: {str(e)}")
        logger.debug(traceback.format_exc())
        return jsonify({"error": "Internal server error"}), 500

