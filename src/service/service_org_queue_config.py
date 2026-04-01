import traceback
import uuid
from database import db
from log_config.logger import logger
from models.OrgQueueConfig import OrgQueueConfig
from service.service_redis import *
from utils.utils_constants import ORG_TEST_RUN_RATE_LIMIT
from access_control.roles import ADMIN

def create_org_queue_config_implementation(org_id: str) -> tuple[dict, int]:
    logger.info(f"Creating org queue config for org: {org_id}")
    try:
        if not org_id:
            return {"error": "org_id is required"}, 400
        
        queue_name = str(uuid.uuid4())
        rate_limit = ORG_TEST_RUN_RATE_LIMIT

        existing = OrgQueueConfig.query.filter_by(org_id=org_id).first()
        if existing:
            logger.info(f"Org queue config already exists for org: {org_id}")
            return {"error": "Org queue config already exists"}, 409

        # Create new queue in Azure
        try:
            from service.service_queue import create_queue
            create_queue(queue_name, org_id)
        except Exception as e:
            logger.error(f"Error in create_queue: {str(e)}")
            logger.debug(traceback.format_exc())
            return {"error": "Failed to create queue in Azure"}, 500

        # Create new org queue config
        config = OrgQueueConfig(org_id=org_id, queue_name=queue_name, rate_limit=rate_limit)
        db.session.add(config)
        db.session.commit()

        # Initialize available rate limit in Redis
        try:
            add_new_org_to_available_rate_limits(org_id, rate_limit)
        except Exception as e:
            logger.error(f"Error in add_new_org_to_available_rate_limits: {str(e)}")
            logger.debug("Skipping Redis init for available_rate_limits")

        return config.serialize(), 201
    except Exception as e:
        logger.error(f"Error in create_org_queue_config_implementation: {str(e)}")
        logger.debug(traceback.format_exc())
        db.session.rollback()
        return {"error": "Error while creating org queue config"}, 500


def update_org_rate_limit_implementation(org_id: str, new_rate_limit: int) -> tuple[dict, int]:
    """
    Update the rate limit for an organization in DB and Redis.
    """
    logger.info(f"Updating org rate limit for org: {org_id} to {new_rate_limit}")
    try:
        if not org_id:
            return {"error": "org_id is required"}, 400
        try:
            new_rate_limit = int(new_rate_limit)
        except Exception:
            return {"error": "new_rate_limit must be an integer"}, 400
        if new_rate_limit < 0:
            return {"error": "new_rate_limit must be >= 0"}, 400

        config = OrgQueueConfig.query.filter_by(org_id=org_id).first()
        if not config:
            return {"error": "Org queue config not found"}, 404

        config.rate_limit = new_rate_limit
        config.modified_at = db.func.now()
        db.session.commit()

        try:
            update_org_rate_limit_in_redis(org_id, new_rate_limit)
        except Exception as e:
            logger.error(f"Failed updating Redis rate limit for org {org_id}: {str(e)}")

        return {"message": "Org rate limit updated successfully"}, 200
    except Exception as e:
        logger.error(f"Error in update_org_rate_limit_implementation: {str(e)}")
        logger.debug(traceback.print_exc())
        db.session.rollback()
        return {"error": "Internal server error"}, 500


def get_org_rate_limit_implementation(current_user: dict, org_id: str) -> tuple[dict, int]:
    """
    Get the rate limit for an organization.
    """
    logger.info(f"Getting org rate limit for org: {org_id}")
    try:
        if not org_id:
            return {"error": "org_id is required"}, 400

        # Check if the user is an admin
        if current_user.get("role") != ADMIN and current_user.get("org_id") != org_id:
            return {"error": "User is not authorized to get org rate limit"}, 403

        config = OrgQueueConfig.query.filter_by(org_id=org_id).first()
        if not config:
            return {"error": "Org config not found"}, 404

        response = config.serialize()
        response.pop('queue_name', None)

        return response, 200
    except Exception as e:
        logger.error(f"Error in get_org_rate_limit_implementation: {str(e)}")
        logger.debug(traceback.print_exc())
        return {"error": "Internal server error"}, 500