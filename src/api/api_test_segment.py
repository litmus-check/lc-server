from flask import jsonify, request, Blueprint
from security.auth import token_required
from log_config.logger import logger
from service.service_test_segment import *
from access_control.operation_constants import *


api_test_segment = Blueprint('api_test_segment', __name__, url_prefix='/api/v1')


@api_test_segment.route('/test_segment', methods=['POST'])
@token_required(TEST_SEGMENT_CREATE)
def create_test_segment(current_user):
    logger.info("Create test segment API called")
    try:
        try:
            data = request.get_json()
        except Exception as e:
            logger.error(f"Invalid request data: {str(e)}")
            return jsonify({'error': 'Invalid request data. Please ensure request is well-formed JSON'}), 400

        if not data:
            return jsonify({"error": "Request body is required"}), 400

        response, status_code = create_test_segment_implementation(current_user, data)
        return jsonify(response), status_code
    except Exception as e:
        logger.error(f"Error in create_test_segment: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500


@api_test_segment.route('/test_segment/<string:segment_id>', methods=['GET'])
@token_required(TEST_SEGMENT_GET)
def get_test_segment(current_user, segment_id):
    logger.info("Get test segment by id API called")
    try:
        response, status_code = get_test_segment_by_id_implementation(current_user, segment_id)
        return jsonify(response), status_code
    except Exception as e:
        logger.error(f"Error in get_test_segment: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500


@api_test_segment.route('/test_segment/suite/<string:suite_id>', methods=['GET'])
@token_required(TEST_SEGMENT_GET_BY_SUITE)
def get_test_segments_by_suite(current_user, suite_id):
    logger.info("Get test segments by suite id API called")
    try:
        response, status_code = get_test_segments_by_suite_implementation(current_user, suite_id)
        return jsonify(response), status_code
    except Exception as e:
        logger.error(f"Error in get_test_segments_by_suite: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500


@api_test_segment.route('/test_segment/<string:segment_id>', methods=['PUT'])
@token_required(TEST_SEGMENT_UPDATE)
def update_test_segment(current_user, segment_id):
    logger.info("Update test segment API called")
    try:
        try:
            data = request.get_json()
        except Exception as e:
            logger.error(f"Invalid request data: {str(e)}")
            return jsonify({'error': 'Invalid request data. Please ensure request is well-formed JSON'}), 400

        if not data:
            return jsonify({"error": "Request body is required"}), 400

        response, status_code = update_test_segment_implementation(current_user, segment_id, data)
        return jsonify(response), status_code
    except Exception as e:
        logger.error(f"Error in update_test_segment: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500


@api_test_segment.route('/test_segment/<string:segment_id>', methods=['DELETE'])
@token_required(TEST_SEGMENT_DELETE)
def delete_test_segment(current_user, segment_id):
    logger.info("Delete test segment API called")
    try:
        response, status_code = delete_test_segment_implementation(current_user, segment_id)
        return jsonify(response), status_code
    except Exception as e:
        logger.error(f"Error in delete_test_segment: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500


