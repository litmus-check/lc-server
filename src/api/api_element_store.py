from flask import jsonify, request, Blueprint
from security.auth import token_required
from log_config.logger import logger
import traceback
from service.service_element_store import *
from access_control.operation_constants import *


api_element_store = Blueprint('api_element_store', __name__, url_prefix='/api/v1')


@api_element_store.route('/suite/<string:suite_id>/store', methods=['POST'])
@token_required(ELEMENT_STORE_CREATE)
def create_store(current_user, suite_id):
    logger.info("Create element store API called")
    try:
        data = request.get_json()
        response, status_code = create_element_store_implementation(current_user, suite_id, data)
        return jsonify(response), status_code
    except Exception as e:
        logger.error(f"Error in create_store: {str(e)}")
        logger.debug(traceback.print_exc())
        return jsonify({"error": "Internal server error"}), 500


@api_element_store.route('/suite/<string:suite_id>/store/<string:store_id>', methods=['PUT'])
@token_required(ELEMENT_STORE_UPDATE)
def update_store(current_user, suite_id, store_id):
    logger.info("Update element store API called")
    try:
        data = request.get_json()
        response, status_code = update_element_store_implementation(current_user, suite_id, store_id, data)
        return jsonify(response), status_code
    except Exception as e:
        logger.error(f"Error in update_store: {str(e)}")
        logger.debug(traceback.print_exc())
        return jsonify({"error": "Internal server error"}), 500


@api_element_store.route('/suite/<string:suite_id>/store', methods=['GET'])
@token_required(ELEMENT_STORE_GET_BY_SUITE)
def get_stores_by_suite(current_user, suite_id):
    logger.info("Get element stores by suite API called")
    try:
        response, status_code = get_element_stores_by_suite_implementation(current_user, suite_id)
        return jsonify(response), status_code
    except Exception as e:
        logger.error(f"Error in get_stores_by_suite: {str(e)}")
        logger.debug(traceback.print_exc())
        return jsonify({"error": "Internal server error"}), 500


@api_element_store.route('/suite/<string:suite_id>/store/<string:store_id>', methods=['DELETE'])
@token_required(ELEMENT_STORE_DELETE)
def delete_store(current_user, suite_id, store_id):
    logger.info("Delete element store API called")
    try:
        response, status_code = delete_element_store_implementation(current_user, suite_id, store_id)
        return jsonify(response), status_code
    except Exception as e:
        logger.error(f"Error in delete_store: {str(e)}")
        logger.debug(traceback.print_exc())
        return jsonify({"error": "Internal server error"}), 500


