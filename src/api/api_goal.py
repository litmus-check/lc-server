from flask import Blueprint, request, jsonify
from models.Test import Test
from database import db
from security.auth import token_required
from log_config.logger import logger
from service.service_compose import *
from service.service_goal import create_goal_implementation, get_goal_status, create_sign_in_flow_implementation, create_sign_up_flow_implementation, create_compose_session_and_sign_in_flow, create_compose_session_and_sign_up_flow
import traceback
from utils.utils_signin_agent import get_default_suite_and_test_name
from access_control.operation_constants import *
from service.service_credits import check_if_user_has_enough_ai_credits, check_if_user_has_enough_credits
from utils.utils_constants import DUMMY_SUITE_ID

api_goal = Blueprint('api_goal', __name__, url_prefix='/api/v1')

@api_goal.route('/compose/<compose_id>/goal', methods=['POST'])
@token_required(GOAL_CREATE)
def create_goal(current_user, compose_id):
    try:
        request_data = request.get_json()
        prompt = request_data.get('prompt')

        # check if the prompt is present
        if not prompt:
            return jsonify({'error': 'Prompt is required'}), 400

        # get suite_id from compose session in redis
        compose_session = get_compose_session_from_redis(compose_id)
        if not compose_session:
            return jsonify({'error': 'Compose session not found'}), 404
        suite_id = compose_session.get('suite_id')

        if not suite_id:
            return jsonify({'error': 'Suite ID not found in compose session'}), 404
        
        # check if the suite has enough ai and browser credits
        ai_resp, ai_status = check_if_user_has_enough_ai_credits(suite_id=suite_id)
        if ai_status != 200:
            return jsonify(ai_resp), ai_status
        
        browser_resp, browser_status = check_if_user_has_enough_credits(suite_id=suite_id)
        if browser_status != 200:
            return jsonify(browser_resp), browser_status
        

        goal_id = create_goal_implementation(compose_id, prompt)
        return jsonify({'message': 'Goal created successfully', 'goal_id': goal_id}), 200
    except Exception as e:
        logger.error(f"Error in create_goal: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500

@api_goal.route('/compose/<compose_id>/goal/<goal_id>', methods=['GET'])
@token_required(GOAL_GET)
def get_goal(current_user, compose_id, goal_id):
    try:
        goal_data = get_goal_status(compose_id, goal_id)
        if goal_data is None:
            return jsonify({'error': 'Goal not found'}), 404
        
        return jsonify(goal_data), 200
    except Exception as e:
        logger.error(f"Error in get_goal: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500
    
# add a POST api that creates a sign in flow. It should accept a url, username and password. and extract those into variables. It should then call a helper function inside service_goal
@api_goal.route('/compose/goal/sign-in', methods=['POST'])
@token_required(GOAL_CREATE_SIGN_IN_FLOW)
def create_sign_in_flow(current_user):
    try:
        request_data = request.get_json()
        url = request_data.get('url')
        username = request_data.get('username')
        password = request_data.get('password')
        suite_name = request_data.get('suite_name')
        test_name = request_data.get('test_name')

        # if suite name is none, strip scheme and special characters from url and use it as the suite name
        suite_name, test_name = get_default_suite_and_test_name(url, suite_name, test_name)

        if not url or not username or not password:
            return jsonify({'error': 'URL, username and password are required'}), 400
        
        # Use dummy suite_id if not provided
        if not request_data.get('suite_id'):
            request_data['suite_id'] = DUMMY_SUITE_ID
        
        agent_args = {
            "suite_name": suite_name,
            "test_name": test_name
        }

        # create a new compose session and sign in flow
        compose_session, status_code = create_compose_session_and_sign_in_flow(current_user, request_data, agent_args)
        if status_code != 200:
            return jsonify({'error': 'Failed to create compose session and sign in flow'}), status_code

        return jsonify({'compose_id': compose_session.get("compose_id"), 'live_url': compose_session.get("live_url")}), 200
    except Exception as e:
        logger.error(f"Error in create_sign_in_flow: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500
    
@api_goal.route('/compose/goal/sign-up', methods=['POST'])
@token_required(GOAL_CREATE_SIGN_UP_FLOW)
def create_sign_up_flow(current_user):
    try:
        request_data = request.get_json()
        url = request_data.get('url')
        username = request_data.get('username')
        password = request_data.get('password')
        suite_name = request_data.get('suite_name')
        test_name = request_data.get('test_name')

        suite_name, test_name = get_default_suite_and_test_name(url, suite_name, test_name)

        if not url or not username or not password:
            return jsonify({'error': 'URL, username and password are required'}), 400
        
        # Use dummy suite_id if not provided
        if not request_data.get('suite_id'):
            request_data['suite_id'] = DUMMY_SUITE_ID
        
        agent_args = {
            "suite_name": suite_name,
            "test_name": test_name
        }

        # create a new compose session and sign up flow
        compose_session, status_code = create_compose_session_and_sign_up_flow(current_user, request_data, agent_args)
        if status_code != 200:
            return jsonify({'error': 'Failed to create compose session and sign up flow'}), status_code

        return jsonify({'compose_id': compose_session.get("compose_id"), 'live_url': compose_session.get("live_url")}), 200
    except Exception as e:
        logger.error(f"Error in create_sign_up_flow: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500