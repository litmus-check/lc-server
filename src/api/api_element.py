from flask import jsonify, request, Blueprint
from security.auth import token_required
from log_config.logger import logger
import traceback
from service.service_element import *
from access_control.operation_constants import *


api_element = Blueprint('api_element', __name__, url_prefix='/api/v1')


@api_element.route('/suite/<string:suite_id>/element', methods=['POST'])
@token_required(ELEMENT_CREATE)
def create_elements(current_user, suite_id):
    logger.info("Create elements API called")
    try:
        data = request.get_json()
        response, status_code = create_elements_implementation(current_user, suite_id, data)
        return jsonify(response), status_code
    except Exception as e:
        logger.error(f"Error in create_element: {str(e)}")
        logger.debug(traceback.print_exc())
        return jsonify({"error": "Internal server error"}), 500


@api_element.route('/suite/<string:suite_id>/element/<string:element_id>', methods=['PUT'])
@token_required(ELEMENT_UPDATE)
def update_element(current_user, suite_id, element_id):
    logger.info("Update element API called")
    try:
        data = request.get_json()
        response, status_code = update_element_implementation(current_user, suite_id, element_id, data)
        return jsonify(response), status_code
    except Exception as e:
        logger.error(f"Error in update_element: {str(e)}")
        logger.debug(traceback.print_exc())
        return jsonify({"error": "Internal server error"}), 500


@api_element.route('/suite/<string:suite_id>/elements', methods=['GET'])
@token_required(ELEMENT_GET_BY_SUITE)
def get_elements_by_suite(current_user, suite_id):
    logger.info("Get elements by suite API called")
    try:
        response, status_code = get_elements_by_suite_implementation(current_user, suite_id)
        return jsonify(response), status_code
    except Exception as e:
        logger.error(f"Error in get_elements_by_suite: {str(e)}")
        logger.debug(traceback.print_exc())
        return jsonify({"error": "Internal server error"}), 500


@api_element.route('/suite/<string:suite_id>/element/<string:element_id>', methods=['DELETE'])
@token_required(ELEMENT_DELETE)
def delete_element(current_user, suite_id, element_id):
    logger.info("Delete element API called")
    try:
        response, status_code = delete_element_implementation(current_user, suite_id, element_id)
        return jsonify(response), status_code
    except Exception as e:
        logger.error(f"Error in delete_element: {str(e)}")
        logger.debug(traceback.print_exc())
        return jsonify({"error": "Internal server error"}), 500


@api_element.route('/suite/<string:suite_id>/elements/merge', methods=['POST'])
@token_required(ELEMENT_MERGE)
def merge_elements(current_user, suite_id):
    logger.info("Merge elements API called")
    try:
        data = request.get_json()
        response, status_code = merge_elements_implementation(current_user, suite_id, data)
        return jsonify(response), status_code
    except Exception as e:
        logger.error(f"Error in merge_elements: {str(e)}")
        logger.debug(traceback.print_exc())
        return jsonify({"error": "Internal server error"}), 500


