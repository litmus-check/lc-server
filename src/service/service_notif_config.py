from models.NotifConfig import NotifConfig
from models.Suite import Suite
from database import db
from datetime import datetime
import uuid
import json
from log_config.logger import logger
import traceback
from sqlalchemy import func, and_

def get_recipients_implementation(current_user, suite_id):
    """
    Retrieve recipients for a specific suite
    Args:
        current_user: Dictionary containing user information including org_id
        suite_id: ID of the suite
    Returns:
        Tuple of (response_dict, status_code)
    """
    try:
        # Verify that the suite exists and user has access to it (handles admin and cross-org access)
        from service.service_suite import return_suite_obj
        suite = return_suite_obj(current_user, suite_id)
        if not suite:
            return {"error": "Suite not found or access denied"}, 404
        
        # Get notification config for the suite
        notif_config = NotifConfig.query.filter_by(suite_id=suite_id).first()
        
        if not notif_config:
            # Return empty recipients list if no config exists
            return {
                "suite_id": suite_id,
                "recipients": [],
                "created_at": None,
                "modified_at": None
            }, 200
        
        # Parse recipients from stringified JSON
        try:
            recipients = json.loads(notif_config.recipients)
            if not isinstance(recipients, list):
                recipients = []
        except (json.JSONDecodeError, TypeError):
            recipients = []
        
        return {
            "suite_id": suite_id,
            "recipients": recipients,
            "created_at": notif_config.created_at.isoformat() if notif_config.created_at else None,
            "modified_at": notif_config.modified_at.isoformat() if notif_config.modified_at else None
        }, 200
        
    except Exception as e:
        logger.error(f"Error in get_recipients_implementation: {str(e)}")
        logger.debug(traceback.format_exc())
        return {"error": "Internal server error"}, 500

def create_recipients_implementation(current_user, suite_id, data):
    """
    Create recipients for a specific suite
    Args:
        current_user: Dictionary containing user information including org_id
        suite_id: ID of the suite
        data: Dictionary containing recipients data
    Returns:
        Tuple of (response_dict, status_code)
    """
    try:
        # Verify that the suite exists and user has access to it (handles admin and cross-org access)
        from service.service_suite import return_suite_obj
        suite = return_suite_obj(current_user, suite_id)
        if not suite:
            return {"error": "Suite not found or access denied"}, 404
        
        # Validate required fields
        if 'recipients' not in data:
            return {"error": "Missing required field: recipients"}, 400
        
        # Validate recipients field using utility function
        from utils.utils_email import validate_recipients_list, validate_recipients_domains
        recipients = data['recipients']
        is_valid, error_message = validate_recipients_list(recipients)
        if not is_valid:
            return {"error": error_message}, 400
        
        # Validate domain whitelist for non-PROD environments
        is_domain_valid, domain_error_message = validate_recipients_domains(recipients)
        if not is_domain_valid:
            return {"error": domain_error_message}, 400
        
        # Check if notification config already exists
        existing_config = NotifConfig.query.filter_by(suite_id=suite_id).first()
        
        if existing_config:
            return {"error": "Recipients already exist for this suite. Use PUT to update."}, 409
        
        # Create new config
        new_config = NotifConfig(
            id=str(uuid.uuid4()),
            suite_id=suite_id,
            channel='email',  # Default to email channel
            recipients=json.dumps(recipients)
        )
        
        db.session.add(new_config)
        db.session.commit()
        
        return {
            "suite_id": suite_id,
            "recipients": recipients,
            "created_at": new_config.created_at.isoformat() if new_config.created_at else None,
            "modified_at": new_config.modified_at.isoformat() if new_config.modified_at else None
        }, 201
        
    except Exception as e:
        logger.error(f"Error in create_recipients_implementation: {str(e)}")
        logger.debug(traceback.format_exc())
        db.session.rollback()
        return {"error": "Internal server error"}, 500

def update_recipients_implementation(current_user, suite_id, data):
    """
    Update recipients for a specific suite
    Args:
        current_user: Dictionary containing user information including org_id
        suite_id: ID of the suite
        data: Dictionary containing recipients data
    Returns:
        Tuple of (response_dict, status_code)
    """
    try:
        # Verify that the suite exists and user has access to it (handles admin and cross-org access)
        from service.service_suite import return_suite_obj
        suite = return_suite_obj(current_user, suite_id)
        if not suite:
            return {"error": "Suite not found or access denied"}, 404
        
        # Validate required fields
        if 'recipients' not in data:
            return {"error": "Missing required field: recipients"}, 400
        
        # Validate recipients field using utility function
        from utils.utils_email import validate_recipients_list, validate_recipients_domains
        recipients = data['recipients']
        is_valid, error_message = validate_recipients_list(recipients)
        if not is_valid:
            return {"error": error_message}, 400
        
        # Validate domain whitelist for non-PROD environments
        is_domain_valid, domain_error_message = validate_recipients_domains(recipients)
        if not is_domain_valid:
            return {"error": domain_error_message}, 400
        
        # Check if notification config exists
        existing_config = NotifConfig.query.filter_by(suite_id=suite_id).first()
        
        if existing_config:
            # Update existing config
            existing_config.recipients = json.dumps(recipients)
            existing_config.modified_at = datetime.utcnow()
            db.session.commit()
        else:
            # Create new config if it doesn't exist
            new_config = NotifConfig(
                id=str(uuid.uuid4()),
                suite_id=suite_id,
                channel='email',  # Default to email channel
                recipients=json.dumps(recipients)
            )
            db.session.add(new_config)
            db.session.commit()
        
        # Get the updated config to return timestamps
        updated_config = NotifConfig.query.filter_by(suite_id=suite_id).first()
        
        return {
            "suite_id": suite_id,
            "recipients": recipients,
            "created_at": updated_config.created_at.isoformat() if updated_config.created_at else None,
            "modified_at": updated_config.modified_at.isoformat() if updated_config.modified_at else None
        }, 200
        
    except Exception as e:
        logger.error(f"Error in update_recipients_implementation: {str(e)}")
        logger.debug(traceback.format_exc())
        db.session.rollback()
        return {"error": "Internal server error"}, 500


def get_emails_for_suite(suite_id):
    """
    Get email recipients for a specific suite
    Args:
        suite_id: Suite ID
    Returns:
        List of email addresses or None if not found
    """
    try:
        # Get notification config for the suite
        from app import app
        with app.app_context():
            notif_config = NotifConfig.query.filter_by(suite_id=suite_id).first()
            
            if not notif_config:
                logger.warning(f"No notification config found for suite_id: {suite_id}")
                return None
            
            # Parse the recipients stringified array
            try:
                recipients = json.loads(notif_config.recipients)
                if isinstance(recipients, list):
                    return recipients
                else:
                    logger.error(f"Invalid recipients format for suite_id: {suite_id}")
                    return None
            except json.JSONDecodeError:
                logger.error(f"Failed to parse recipients JSON for suite_id: {suite_id}")
                return None
            
    except Exception as e:
        logger.error(f"Error in get_emails_for_org_and_suite: {str(e)}")
        logger.debug(traceback.format_exc())
        return None
