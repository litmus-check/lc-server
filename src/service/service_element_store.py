from database import db
from models.ElementStore import ElementStore
from models.Element import Element
from service.service_suite import return_suite_obj
from log_config.logger import logger
import traceback
import uuid
from access_control.roles import ADMIN
from sqlalchemy.orm import joinedload


def create_element_store_implementation(current_user: dict, suite_id: str, data: dict) -> tuple[dict, int]:
    try:
        logger.info(f"Creating element store for suite {suite_id}")
        store_name = data.get('store_name')
        if not store_name:
            return {"error": "store_name is required"}, 400

        suite = return_suite_obj(current_user, suite_id)
        if not suite:
            return {"error": "Suite not found or user does not have access to it"}, 404

        # Enforce unique store name per suite at app level too
        existing = ElementStore.query.filter_by(suite_id=suite_id, store_name=store_name).first()
        if existing:
            logger.info(f"Store name {store_name} already exists for suite {suite_id}")
            return {"error": "Store name already exists for this suite"}, 409

        new_store = ElementStore(
            store_id=str(uuid.uuid4()),
            store_name=store_name,
            store_description=data.get('store_description', ''),
            suite_id=suite_id,
        )

        db.session.add(new_store)
        db.session.commit()
        logger.info(f"Element store created for suite {suite_id} with name {store_name}")
        return new_store.serialize(), 201
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error in create_element_store_implementation: {str(e)}")
        logger.debug(traceback.print_exc())
        return {"error": str(e)}, 400


def update_element_store_implementation(current_user: dict, suite_id: str, store_id: str, data: dict) -> tuple[dict, int]:
    logger.info(f"Updating element store for suite {suite_id} with store id {store_id}")
    try:
        store = return_element_store_obj(current_user, store_id, suite_id)
        if not store:
            return {"error": "Store not found or user does not have access to it"}, 404

        # Do not allow updating suite_id
        if 'suite_id' in data and data['suite_id'] != store.suite_id:
            return {"error": "Updating suite_id is not allowed"}, 400

        # If updating name, enforce uniqueness per suite
        if 'store_name' in data and data['store_name'] != store.store_name:
            conflict = ElementStore.query.filter_by(suite_id=store.suite_id, store_name=data['store_name']).first()
            if conflict:
                return {"error": "Store name already exists for this suite"}, 409
            store.store_name = data['store_name']

        if 'store_description' in data:
            store.store_description = data['store_description']

        # Update modified_at
        store.modified_at = db.func.now()

        db.session.commit()
        logger.info(f"Element store updated for suite {suite_id} with store id {store_id}")
        return store.serialize(), 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error in update_element_store_implementation: {str(e)}")
        logger.debug(traceback.print_exc())
        return {"error": str(e)}, 400


def get_element_stores_by_suite_implementation(current_user: dict, suite_id: str) -> tuple[dict, int]:
    logger.info(f"Getting element stores for suite {suite_id}")
    try:
        suite = return_suite_obj(current_user, suite_id)
        if not suite:
            return {"error": "Suite not found or user does not have access to it"}, 404

        stores = ElementStore.query.filter_by(suite_id=suite_id).order_by(ElementStore.modified_at.desc()).all()
        logger.info(f"Element stores retrieved for suite {suite_id}")
        return {"stores": [s.serialize() for s in stores]}, 200
    except Exception as e:
        logger.error(f"Error in get_element_stores_by_suite_implementation: {str(e)}")
        logger.debug(traceback.print_exc())
        return {"error": str(e)}, 400


def delete_element_store_implementation(current_user: dict, suite_id: str, store_id: str) -> tuple[dict, int]:
    try:
        logger.info(f"Deleting element store for suite {suite_id} with store id {store_id}")
        store = return_element_store_obj(current_user, store_id, suite_id)
        if not store:
            return {"error": "Store not found or user does not have access to it"}, 404

        db.session.delete(store)

        # Delete elements that are present in store
        Element.query.filter_by(store_name=store.store_name, suite_id=suite_id).delete(synchronize_session=False)
        db.session.commit()

        logger.info(f"Element store deleted for suite {suite_id} with store id {store_id}")
        return {"message": "Store deleted successfully"}, 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error in delete_element_store_implementation: {str(e)}")
        logger.debug(traceback.print_exc())
        return {"error": str(e)}, 400

def return_element_store_obj(current_user: dict, store_id: str, suite_id: str) -> ElementStore | None:
    try:
        logger.info(f"Returning element store object for suite {suite_id} with store id {store_id}")
        store = ElementStore.query.filter_by(store_id=store_id, suite_id=suite_id).options(joinedload(ElementStore.suite)).first()
        if not store:
            return None

        # Check if user has access to the suite containing this store
        if current_user.get('role') != ADMIN and store.suite.org_id != current_user['org_id']:
            return None
        return store
    except Exception as e:
        logger.error(f"Error in return_element_store_obj: {str(e)}")
        logger.debug(traceback.print_exc())
        return None

