import traceback
from database import db
from log_config.logger import logger
from models.Credits import Credits
from datetime import datetime, timezone
from sqlalchemy import or_
from service.service_org_queue_config import create_org_queue_config_implementation
from access_control.roles import ADMIN

def check_if_user_has_enough_ai_credits(suite_id: str = None, org_id: str = None) -> tuple[dict, int]:
    """
    Check if the org has enough AI credits for the test/suite/compose being run
    Args:
        suite_id: Suite ID
        org_id: Organization ID
    Returns:
        tuple[dict, int]: The response and the status code
    """
    try:
        logger.info("AI credits enforcement is disabled; allowing request")
        return {"message": "AI credits enforcement disabled"}, 200
    except Exception as e:
        logger.error(f"Error in check_if_user_has_enough_ai_credits: {e}")
        logger.debug(traceback.format_exc())
        raise e

def check_if_user_has_enough_credits(suite_id: str = None, org_id: str = None) -> tuple[dict, int]:
    """
    Check if the user has enough credits
    Args:
        suite_id (str): The suite id
        org_id (str): The organization id
    Returns:
        tuple[dict, int]: The response and the status code
    """
    try:
        logger.info("Browser credits enforcement is disabled; allowing request")
        return {"message": "Browser credits enforcement disabled"}, 200
    except Exception as e:
        logger.error(f"Error in check_if_user_has_enough_credits: {e}")
        logger.debug(traceback.format_exc())
        raise e
    

def create_org_in_credits_table(org_id: str) -> None:
    """
    Create a new credits entry if it doesn't exist
    Args:
        org_id (str): The org id
    """
    try:
        logger.info(f"Creating org in credits table: {org_id}")
        from app import app
        with app.app_context():
            credits = Credits.query.filter_by(org_id=org_id).first()

            # Create a new credits entry if it doesn't exist
            if not credits:
                logger.info(f"Creating new credits entry for org: {org_id}")
                credits = Credits(org_id=org_id)

                # Calculate next reset date
                credits.calculate_next_reset_date()
                db.session.add(credits)
                db.session.commit()
        logger.info(f"New credits entry created for org: {org_id}")
    except Exception as e:
        logger.error(f"Error in create_org_in_credits_table: {e}")
        logger.error(traceback.format_exc())
        raise e
    
def update_credits(org_id: str, seconds: int = None, ai_credits: float = None) -> None:
    """
    Update the credits table for the org
    Args:
        org_id (str): The org id
        seconds (int): The seconds to subtract
        ai_credits (float): The AI credits to subtract
    """
    try:
        logger.info(
            f"Skipping credit decrement for org: {org_id} "
            f"(seconds={seconds}, ai_credits={ai_credits})"
        )
        return
    except Exception as e:
        logger.error(f"Error in update_credits_table: {e}")
        logger.error(traceback.format_exc())
        raise e

def get_credits_implementation(current_user: dict) -> tuple[dict, int]:
    """
    Get the credits for the user
    Args:
        current_user (dict): The current user
    Returns:
        tuple[dict, int]: The credits and the status code
    """
    try:
        org_id = current_user.get('org_id')
        if not org_id:
            return {"error": "Org ID not provided"}, 400
        
        credits = Credits.query.filter_by(org_id=org_id).first()
        if not credits:
            return {"error": "Org not found"}, 400
        
        # Convert the browser_credits to minutes and round off to two decimal places
        browser_credits = round(int(credits.browser_credits)/60, 2)
        ai_credits = round(float(credits.ai_credits), 2)
        
        return {
            "browser_minutes": browser_credits,
            "ai_credits": ai_credits
        }, 200
    except Exception as e:
        logger.error(f"Error in get_credits_implementation: {e}")
        logger.error(traceback.format_exc())
        raise e

def get_credits_by_org_id_implementation(current_user: dict, org_id: str) -> tuple[dict, int]:
    """
    Get the credits for an organization by org id
    Args:
        current_user (dict): The current user
        org_id (str): The org id
    Returns:
        tuple[dict, int]: The credits and the status code
    """
    try:
        if current_user.get("role") != ADMIN:
            return {"error": "User is not authorized to get credits for org"}, 403
        
        logger.info(f"Getting credits for org: {org_id}")
        credits = Credits.query.filter_by(org_id=org_id).first()
        if not credits:
            return {"error": "Org not found"}, 400

        # Convert the browser_credits to minutes and round off to two decimal places
        browser_credits = round(int(credits.browser_credits)/60, 2)
        ai_credits = round(float(credits.ai_credits), 2)
        
        return {
            "browser_minutes": browser_credits,
            "ai_credits": ai_credits
        }, 200
    except Exception as e:
        logger.error(f"Error in get_credits_by_org_id_implementation: {e}")
        logger.error(traceback.format_exc())
        raise e

def update_credits_implementation(current_user: dict, org_id: str, request_data: dict) -> tuple[dict, int]:
    """
    Update the credits for an organization
    Args:
        current_user (dict): The current user
        org_id (str): The org id
        request_data (dict): The request data containing ai_credits and browser_minutes
    Returns:
        tuple[dict, int]: The response and status code
    """
    try:
        logger.info(f"Updating credits for org: {org_id}")

        # Check if the user is admin
        if current_user.get("role") != ADMIN:
            return {"error": "User is not authorized to update credits"}, 403
        
        ai_credits = request_data.get("ai_credits")
        browser_minutes = request_data.get("browser_minutes")
        
        if ai_credits is None and browser_minutes is None:
            return {"error": "At least one credit type must be provided"}, 400
        
        credits = Credits.query.filter_by(org_id=org_id).first()
        if not credits:
            return {"error": "Unable to find credits record for org"}, 400
        
        if ai_credits is not None:
            credits.ai_credits += float(ai_credits)
            logger.info(f"Updated AI credits for org {org_id} to {ai_credits}")
        
        if browser_minutes is not None:
            credits.browser_credits += int(browser_minutes * 60)  # Convert minutes to seconds
            logger.info(f"Updated browser credits for org {org_id} to {browser_minutes} minutes")
        
        credits.modified_date = datetime.now(timezone.utc)
        db.session.commit()

        # Convert the browser_credits to minutes and round off to two decimal places
        browser_credits = round(int(credits.browser_credits)/60, 2)
        ai_credits = round(float(credits.ai_credits), 2)
        
        return {
            "browser_minutes": browser_credits,
            "ai_credits": ai_credits
        }, 200
    except Exception as e:
        logger.error(f"Error in update_credits_implementation: {e}")
        logger.error(traceback.format_exc())
        raise e

def add_credits_implementation(current_user: dict, request_data: dict) -> tuple[dict, int]:
    """
    Add credits to the user's organization
    Args:
        current_user (dict): The current user
        request_data (dict): The request data org_id to add
    Returns:
        tuple[dict, int]: The response and the status code
    """
    try:
        org_id = request_data.get("org_id")
        if not org_id:
            return {"error": "Org ID not found in user details"}, 400

        logger.info(f"Create entry in credits table for org: {org_id}")
        
        # Ensure org exists in credits table
        create_org_in_credits_table(org_id)

        # Create new queue for org
        create_org_queue_config_implementation(org_id)
        
        logger.info(f"Credits added for org: {org_id}")
        return {"message": "Credits added successfully"}, 200
            
    except Exception as e:
        logger.error(f"Error in add_credits_implementation: {e}")
        logger.error(traceback.format_exc())
        raise e

def update_credit_to_zero_implementation(org_id: str) -> tuple[dict, int]:
    """
    Update the credits to zero for an organization
    Args:
        org_id (str): The org id
    Returns:
        tuple[dict, int]: The response and the status code
    """
    try:
        logger.info(f"Updating credits to zero for org: {org_id}")
        from app import app
        with app.app_context():
            credits = Credits.query.filter_by(org_id=org_id).first()
            if not credits:
                return {"error": "Org not found in credits table"}, 400
            
            credits.browser_credits = 0
            credits.ai_credits = 0
            credits.modified_date = datetime.now(timezone.utc)
            db.session.commit()
            return {"message": "Credits updated to zero successfully"}, 200
    except Exception as e:
        logger.error(f"Error in update_credit_to_zero_implementation: {e}")
        logger.error(traceback.format_exc())
        raise e

def list_orgs_with_low_credits_implementation(current_user: dict, ai_credits_threshold: float = None, browser_minutes_threshold: float = None, bearer_token: str = None) -> tuple[dict, int]:
    """
    List all organizations that have less than the specified ai_credits or browser_minutes
    Args:
        current_user (dict): The current user
        ai_credits_threshold (float): The threshold for AI credits (optional)
        browser_minutes_threshold (float): The threshold for browser minutes (optional)
        bearer_token (str): The bearer token
    Returns:
        tuple[dict, int]: The response and status code
    """
    try:
        # Check if the user is admin
        if current_user.get("role") != ADMIN:
            return {"error": "User is not authorized to list orgs with low credits"}, 403
        
        # Validate that at least one threshold is provided
        if ai_credits_threshold is None and browser_minutes_threshold is None:
            return {"error": "At least one valid threshold (ai_credits or browser_minutes) must be provided"}, 400
        
        logger.info(f"Listing orgs with low credits - ai_credits_threshold: {ai_credits_threshold}, browser_minutes_threshold: {browser_minutes_threshold}")
        
        # Build the query
        query = Credits.query
        
        # Convert browser_minutes_threshold to seconds for comparison
        browser_seconds_threshold = None
        if browser_minutes_threshold is not None:
            browser_seconds_threshold = int(browser_minutes_threshold * 60)
        
        # Build filter conditions
        conditions = []
        if ai_credits_threshold is not None:
            conditions.append(Credits.ai_credits < ai_credits_threshold)
        if browser_seconds_threshold is not None:
            conditions.append(Credits.browser_credits < browser_seconds_threshold)
        
        # Apply OR condition - orgs with low ai_credits OR low browser_minutes
        query = query.filter(or_(*conditions))
        
        # Execute query
        credits_list = query.all()
        
        # Format the response
        orgs = []
        for credits in credits_list:
            browser_minutes = round(int(credits.browser_credits) / 60, 2)
            ai_credits = round(float(credits.ai_credits), 2)
            
            orgs.append({
                "org_id": credits.org_id,
                "browser_minutes": browser_minutes,
                "ai_credits": ai_credits,
                "start_date": credits.start_date.isoformat() if credits.start_date else None,
                "modified_date": credits.modified_date.isoformat() if credits.modified_date else None,
                "last_reset_date": credits.last_reset_date.isoformat() if credits.last_reset_date else None,
                "next_reset_date": credits.next_reset_date.isoformat() if credits.next_reset_date else None
            })

        logger.info(f"Found {len(orgs)} organizations with low credits")
        
        return {
            "orgs": orgs,
            "count": len(orgs)
        }, 200
    except Exception as e:
        logger.error(f"Error in list_orgs_with_low_credits_implementation: {e}")
        logger.error(traceback.format_exc())
        raise e