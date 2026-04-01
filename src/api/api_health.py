from flask import jsonify
from flask import Blueprint
from log_config.logger import logger
from utils.utils_constants import TEST_RUNNER_THREAD_NAME
from service.service_runner import TestRunner

api_health = Blueprint('api_health', __name__, url_prefix='/api/v1')

@api_health.route('/health/testrunner', methods=['GET'])
def health_testrunner():
    try:
        if TestRunner.is_thread_running(TEST_RUNNER_THREAD_NAME):
            return jsonify({'status': 'ok'}), 200
        else:
            return jsonify({'status': 'TestRunner not running'}), 500
    except Exception as e:
        logger.error(f"Error in test runner health check: {str(e)}")
        return jsonify({'status': 'error'}), 500
