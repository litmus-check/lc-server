from flask import jsonify, request, Blueprint
from security.auth import token_required
from log_config.logger import logger
from service.service_schedule import *
from models.Schedule import Schedule
from utils.utils_constants import *
import traceback
from access_control.operation_constants import *

api_schedule = Blueprint('api_schedule', __name__, url_prefix='/api/v1')

@api_schedule.route('/suite/<string:suite_id>/schedule', methods=['POST'])
@token_required(SCHEDULE_CREATE)
def create_schedule(current_user, suite_id):
    logger.info(f"Create schedule API called for suite_id: {suite_id}")
    try:
        # Extract JSON data from request body
        data = request.get_json()

        browser = request.args.get('browser', DEFAULT_BROWSER)
        if browser not in ALLOWED_BROWSERS:
            response = {
                "error": f"Invalid browser type. Allowed browsers are: {', '.join(ALLOWED_BROWSERS)}"
            }
        
        # Call service layer implementation
        #response, status_code = test_schedule_implementation()
        response, status_code = create_schedule_implementation(current_user, suite_id, browser, data)
        return jsonify(response), status_code
    except Exception as e:
        logger.error(f"Error in create_schedule: {str(e)}")
        logger.debug(traceback.print_exc())
        return jsonify({"error": "Internal server error"}), 500
    

@api_schedule.route('/suite/<string:suite_id>/schedule/<string:schedule_id>', methods=['PUT'])
@token_required(SCHEDULE_UPDATE)
def update_schedule(current_user, suite_id, schedule_id):
    logger.info(f"Update schedule API called for suite_id: {suite_id}, schedule_id: {schedule_id}")
    try:
        # Extract JSON data from request body
        data = request.get_json()

        browser = request.args.get('browser', DEFAULT_BROWSER)
        if browser not in ALLOWED_BROWSERS:
            response = {
                "error": f"Invalid browser type. Allowed browsers are: {', '.join(ALLOWED_BROWSERS)}"
            }
        
        # Call service layer implementation
        response, status_code = update_schedule_implementation(current_user, suite_id, schedule_id, browser, data)
        return jsonify(response), status_code
    except Exception as e:
        logger.error(f"Error in update_schedule: {str(e)}")
        logger.debug(traceback.print_exc())
        return jsonify({"error": "Internal server error"}), 500
    

@api_schedule.route('/suite/<string:suite_id>/schedule/<string:schedule_id>', methods=['DELETE'])
@token_required(SCHEDULE_DELETE)
def delete_schedule(current_user, suite_id, schedule_id):
    logger.info(f"Delete schedule API called for suite_id: {suite_id}, schedule_id: {schedule_id}")
    try:
        # Call service layer implementation
        response, status_code = delete_schedule_implementation(current_user, suite_id, schedule_id)
        return jsonify(response), status_code
    except Exception as e:
        logger.error(f"Error in delete_schedule: {str(e)}")
        logger.debug(traceback.print_exc())
        return jsonify({"error": "Internal server error"}), 500
    

@api_schedule.route('/suite/<string:suite_id>/schedules', methods=['GET'])
@token_required(SCHEDULE_GET_BY_SUITE)
def get_suite_schedules(current_user, suite_id):
    logger.info(f"Get suite schedules API called for suite_id: {suite_id}")
    try:
        # Verify suite exists and user has access
        suite = return_suite_obj(current_user, suite_id)
        if not suite:
            return jsonify({"error": "Suite not found or access denied"}), 404

        # Get all schedules for the suite
        schedules = Schedule.query.filter_by(suite_id=suite_id).all()
        
        # Convert schedules to response format
        response = {
            "schedules": [schedule.to_dict() for schedule in schedules]
        }
        
        return jsonify(response), 200
    except Exception as e:
        logger.error(f"Error in get_suite_schedules: {str(e)}")
        logger.debug(traceback.print_exc())
        return jsonify({"error": "Internal server error"}), 500




