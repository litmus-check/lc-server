import uuid
import json
import traceback
import re
from database import db
from models.Element import Element
from log_config.logger import logger
from sqlalchemy.orm import joinedload
from models.ElementStore import ElementStore
from service.service_suite import return_suite_obj
from access_control.roles import ADMIN
from models.Test import Test
from sqlalchemy import text, or_
from utils.utils_constants import ELEMENT_DESCRIPTION_MAX_LENGTH


def validate_store_name_for_suite(suite_id: str, store_name: str) -> tuple[bool, str | None]:
    if store_name is None or store_name == '':
        return True, None
    exists = ElementStore.query.filter_by(suite_id=suite_id, store_name=store_name).first()
    if exists:
        return True, None
    return False, "Store name not found for this suite"


def validate_element_id_format(element_id: str) -> bool:
    """
    Validate the element id format. Element should not have spaces and should be alphanumeric [a-zA-Z0-9_-]
    """
    if re.match(r'^[a-zA-Z0-9_-]+$', element_id):
        return True
    return False


def validate_element_description_length(element_description: str) -> tuple[bool, str | None]:
    """
    Validate the element description length.
    
    Args:
        element_description: The description text to validate
        
    Returns:
        tuple: (is_valid, error_message) - is_valid is True if valid, False otherwise
    """
    if element_description is None:
        return True, None
    
    if len(element_description) > ELEMENT_DESCRIPTION_MAX_LENGTH:
        return False, f"Element description exceeds maximum length of {ELEMENT_DESCRIPTION_MAX_LENGTH} characters. Current length: {len(element_description)}"
    
    return True, None


def create_elements_implementation(current_user: dict, suite_id: str, data: dict) -> tuple[dict, int]:
    try:
        logger.info(f"Creating elements for suite {suite_id}")
        suite = return_suite_obj(current_user, suite_id)
        if not suite:
            return {"error": "Suite not found or user does not have access to it"}, 404

        element_id = data.get('element_id')
        if not element_id:
            return {"error": "Element name is required"}, 400

        # Check if the element_id follows the required format
        if not validate_element_id_format(element_id):
            return {"error": "Element name must be alphanumeric [a-zA-Z0-9_-]"}, 400

        # Check if the element already exists
        element = return_element_obj(current_user, element_id, suite_id)
        if element:
            return {"error": "Element already exists"}, 400

        element_description = data.get('element_description', '').strip()
        element_prompt = data.get('element_prompt')
        store_name = data.get('store_name')
        selectors = data.get('selectors', [])

        # Validate element_description length
        is_valid, err = validate_element_description_length(element_description)
        logger.info(f"Element description length: {len(element_description)} is valid")
        if not is_valid:
            return {"error": err}, 400

        # Validate store_name
        is_valid, err = validate_store_name_for_suite(suite_id, store_name)
        if not is_valid:
            return {"error": err}, 400

        element = Element(
            element_id=element_id,
            suite_id=suite_id,
            element_description=element_description,
            element_prompt=element_prompt,
            store_name=store_name,
            selectors=json.dumps(selectors) if selectors is not None else json.dumps([]),
        )
        db.session.add(element)

        db.session.commit()
        logger.info(f"Elements created for suite {suite_id}")
        return element.serialize(), 201
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error in create_elements_implementation: {str(e)}")
        logger.debug(traceback.print_exc())
        return {"error": str(e)}, 400


def update_element_implementation(current_user: dict, suite_id: str, element_id: str, data: dict) -> tuple[dict, int]:
    logger.info(f"Updating element for suite {suite_id} with element id {element_id}")
    try:

        element = return_element_obj(current_user, element_id, suite_id)
        if not element:
            return {"error": "Element not found or user does not have access to it"}, 404

        if 'store_name' in data:
            is_valid, err = validate_store_name_for_suite(suite_id, data['store_name'])
            if not is_valid:
                return {"error": err}, 400
            element.store_name = data['store_name']

        if 'element_description' in data:
            # Validate element_description length
            element_description = data['element_description'].strip()
            is_valid, err = validate_element_description_length(element_description)
            if not is_valid:
                return {"error": err}, 400
            element.element_description = data['element_description']
        if 'element_prompt' in data:
            element.element_prompt = data['element_prompt']
        if 'selectors' in data:
            selectors = data['selectors'] if data['selectors'] is not None else []
            element.selectors = json.dumps(selectors)

        element.modified_at = db.func.now()
        db.session.commit()
        return element.serialize(), 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error in update_element_implementation: {str(e)}")
        logger.debug(traceback.print_exc())
        return {"error": str(e)}, 400


def get_elements_by_suite_implementation(current_user: dict, suite_id: str) -> tuple[dict, int]:
    logger.info(f"Getting elements for suite {suite_id}")
    try:
        suite = return_suite_obj(current_user, suite_id)
        if not suite:
            return {"error": "Suite not found or user does not have access to it"}, 404

        elements = Element.query.filter_by(suite_id=suite_id).order_by(Element.modified_at.desc()).all()
        logger.info(f"Elements retrieved for suite {suite_id}")
        return {"elements": [e.serialize() for e in elements]}, 200
    except Exception as e:
        logger.error(f"Error in get_elements_by_suite_implementation: {str(e)}")
        logger.debug(traceback.print_exc())
        return {"error": str(e)}, 400


def delete_element_implementation(current_user: dict, suite_id: str, element_id: str) -> tuple[dict, int]:
    try:
        logger.info(f"Deleting element for suite {suite_id} with element id {element_id}")

        element = return_element_obj(current_user, element_id, suite_id)
        if not element:
            return {"error": "Element not found or user does not have access to it"}, 404

        db.session.delete(element)
        db.session.commit()
        logger.info(f"Element deleted for suite {suite_id} with element id {element_id}")
        return {"message": "Element deleted successfully"}, 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error in delete_element_implementation: {str(e)}")
        logger.debug(traceback.print_exc())
        return {"error": str(e)}, 400

def return_element_obj(current_user: dict, element_id: str, suite_id: str=None) -> Element | None:
    try:
        # Add lazy loading for suite
        if suite_id:
            element = Element.query.filter_by(element_id=element_id, suite_id=suite_id).options(joinedload(Element.suite)).first()
        else:
            element = Element.query.filter_by(element_id=element_id).options(joinedload(Element.suite)).first()
        if not element:
            return None

        # Check if user has access to the element
        if current_user.get('role') != ADMIN and element.suite.org_id != current_user['org_id']:
            return None
        return element
    except Exception as e:
        logger.error(f"Error in return_element_obj: {str(e)}")
        logger.debug(traceback.print_exc())
        raise e


def merge_elements_implementation(current_user: dict, suite_id: str, data: dict) -> tuple[dict, int]:
    """
    Merge secondary elements into primary element by updating all test instructions
    and then deleting the secondary elements.
    """
    try:
        logger.info(f"Merging elements for suite {suite_id}")
        
        # Validate suite access
        suite = return_suite_obj(current_user, suite_id)
        if not suite:
            return {"error": "Suite not found or user does not have access to it"}, 404
        
        # Validate request data
        primary_element_id = data.get('primary_element_id')
        secondary_element_ids = data.get('secondary_element_ids', [])
        
        if not primary_element_id:
            return {"error": "primary_element_id is required"}, 400
        
        if not secondary_element_ids or not isinstance(secondary_element_ids, list):
            return {"error": "secondary_element_ids must be a non-empty array"}, 400
        
        if primary_element_id in secondary_element_ids:
            return {"error": "primary_element_id cannot be in secondary_element_ids"}, 400
        
        # Validate that all elements exist and belong to the suite
        all_element_ids = [primary_element_id] + secondary_element_ids
        elements = db.session.query(Element).filter(
            Element.element_id.in_(all_element_ids),
            Element.suite_id == suite_id
        ).all()
        
        found_element_ids = {elem.element_id for elem in elements}
        missing_elements = set(all_element_ids) - found_element_ids
        
        if missing_elements:
            return {"error": f"Elements not found or not accessible: {list(missing_elements)}"}, 404
        
        updated_tests_count = 0
        deleted_count = 0
        
        with db.session.begin_nested():
            # Use raw SQL to find and update element_id values directly
            for secondary_id in secondary_element_ids:
                # Use SQL to find and replace element_id values with specific JSON patterns
                # Handle two patterns: "element_id": <secondary_element> and "element_id":<secondary_element>
                update_query = text("""
                    UPDATE test 
                    SET instructions = REPLACE(REPLACE(instructions, :element_id_pattern1, :replacement_pattern1), 
                                               :element_id_pattern2, :replacement_pattern2)
                    WHERE suite_id = :suite_id 
                    AND (instructions LIKE :search_pattern1 OR instructions LIKE :search_pattern2)
                """)
                
                # Execute the update with pattern matching for both formats
                result = db.session.execute(update_query, {
                    'element_id_pattern1': f'"element_id": "{secondary_id}"',
                    'replacement_pattern1': f'"element_id": "{primary_element_id}"',
                    'element_id_pattern2': f'"element_id":"{secondary_id}"',
                    'replacement_pattern2': f'"element_id":"{primary_element_id}"',
                    'suite_id': suite_id,
                    'search_pattern1': f'%"element_id": "{secondary_id}"%',
                    'search_pattern2': f'%"element_id":"{secondary_id}"%'
                })
                
                # Get the number of affected rows
                rows_affected = result.rowcount
                if rows_affected > 0:
                    updated_tests_count += rows_affected
                    logger.info(f"Updated {rows_affected} tests, replaced element_id: {secondary_id} with {primary_element_id}")
            
            if updated_tests_count == 0:
                logger.info("No tests found with secondary element_ids to update")
            
            # Verify no remaining references before deletion
            remaining = db.session.query(Test.id).filter(
                Test.suite_id == suite_id,
                or_(*[Test.instructions.like(f'%"element_id": "{sid}"%') for sid in secondary_element_ids] + 
                    [Test.instructions.like(f'%"element_id":"{sid}"%') for sid in secondary_element_ids])
            ).all()

            logger.info(f"Primary element id: {primary_element_id}")
            logger.info(f"Secondary element ids: {secondary_element_ids}")
            logger.info(f"Remaining tests: {remaining}")
            
            if remaining:
                db.session.rollback()
                return {"error": "Merge aborted: remaining references to secondary elements found"}, 409
            
            # Safe delete within the same transaction
            deleted_count = db.session.query(Element).filter(
                Element.element_id.in_(secondary_element_ids),
                Element.suite_id == suite_id
            ).delete(synchronize_session=False)

        db.session.commit()
        
        logger.info(f"Successfully merged elements: {deleted_count} secondary elements deleted, {updated_tests_count} tests updated")
        
        return {
            "message": "Elements merged successfully",
            "updated_tests": updated_tests_count,
            "deleted_elements": deleted_count,
            "primary_element_id": primary_element_id,
            "secondary_element_ids": secondary_element_ids
        }, 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error in merge_elements_implementation: {str(e)}")
        logger.debug(traceback.print_exc())
        return {"error": "Internal server error"}, 500