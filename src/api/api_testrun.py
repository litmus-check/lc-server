from security.auth import *
from log_config.logger import logger
from service.service_testrun import *
from flask import Blueprint, request, jsonify
from access_control.operation_constants import *


api_testrun = Blueprint('api_testrun',__name__, url_prefix='/api/v1')

@api_testrun.route('/testruns', methods=['GET'])
@token_required(TESTRUN_GET_ALL)
def test_result(current_user):
    logger.info("Get test result API called")
    try:
        page_num = request.args.get('page', default=1, type=int)
        limit = request.args.get('limit', default=10, type=int)
        id = request.args.get('test_id', default=None, type=str)
        suite_run_id = request.args.get('suite_run_id', default=None, type=str)
        response, status_code = get_testrun_result(current_user, id, suite_run_id, page_num, limit)
        return jsonify(response), status_code
    except Exception as e:
        logger.error(f"Error in getting test results: {str(e)}")
        response = {
            "error": "Internal server error"
        }
        return jsonify(response), 500
    
@api_testrun.route('/testrun/<string:testrun_id>', methods=['GET'])
@token_required(TESTRUN_GET)
def get_test_result(current_user, testrun_id):
    logger.info("Create test log API called")
    try:

        response, status_code = get_testrun_result_by_runid(current_user, testrun_id)
        return jsonify(response), status_code
    except Exception as e:
        logger.error(f"Error in getting test result by runid: {str(e)}")
        response = {
            "error": "Internal server error"
        }
        return jsonify(response), 500




