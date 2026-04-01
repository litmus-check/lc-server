import traceback
from datetime import datetime, timezone
from database import db
from log_config.logger import logger
from service.service_credits import update_credits
from models.ActivityLog import ActivityLog
from utils.utils_constants import MANUAL_TRIGGER, BROWSERBASE_SESSION_TIMEOUT


def create_activity_log(current_user: dict, log_id: str, reference_id: str, mode: str, environment: str, trigger: str = MANUAL_TRIGGER):
    """
    Create a new activity log entry in the database.
    
    Args:
        current_user (dict): The current user.
        log_id (str): The unique identifier for the log entry.
        reference_id (str): The unique identifier for the log entry.
        mode (str): The mode of the activity (e.g., 'script', 'compose').
        environment (str): The environment of the activity (e.g., 'browserbase', 'litmus_cloud').
        trigger (str): The trigger of the activity (e.g., 'manual', 'scheduled').
    """
    try:
        logger.info(f"Creating activity log for test_run/compose_run {reference_id}")

        # Extract user_id, org_id from current_user
        user_id = current_user.get('user_id')
        org_id = current_user.get('org_id')

        from app import app
        with app.app_context():
            activity_log = ActivityLog(log_id=log_id, reference_id=reference_id, mode=mode, environment=environment, trigger=trigger, 
                                       start_date=datetime.now(timezone.utc), user_id=user_id, org_id=org_id)
            db.session.add(activity_log)
            db.session.commit()
        
        logger.info(f"Activity log created for test_run/compose_run {reference_id}")
    except Exception as e:
        logger.error(f"Error in create_activity_log: {e}")
        logger.error(traceback.format_exc())
        raise e

def update_activity_log(current_user: dict, log_id: str=None, reference_id: str=None, end_time: datetime=None, ai_credits_consumed: float=None) -> None:
    """
    Update an existing activity log entry in the database.
    
    Args:
        current_user (dict): The current user.
        log_id (str): The unique identifier for the log entry.
        reference_id (str): The unique identifier for the log entry.
        end_time (datetime): The time when the activity ended.
        ai_credits_consumed (float): The AI credits consumed.
    """
    try:
        logger.info(f"Updating activity log for log_id: {log_id} and reference_id: {reference_id} and end_time: {end_time}")
        from app import app
        with app.app_context():
            # If log_id is not provided, we need to get the activity log by log_id and reference_id
            if not log_id:
                # Get the activity log by reference_id, get the latest one by order by start_date desc and end_date is null
                activity_log = ActivityLog.query.filter_by(reference_id=reference_id).order_by(ActivityLog.start_date.desc()).filter(ActivityLog.end_date.is_(None)).first()
            else:
                activity_log = ActivityLog.query.filter_by(log_id=log_id).first()
            
            if not activity_log:
                raise Exception(f"Activity log with log_id {log_id} not found")
            
            # Get the old executed_seconds and ai_credits
            executed_seconds_old = activity_log.executed_seconds
            ai_credits_to_update = None

            if end_time:
                activity_log.end_date = end_time

                # Calculate the difference in seconds using Python datetime
                time_diff = activity_log.end_date - activity_log.start_date
                seconds_diff = time_diff.total_seconds()

                if seconds_diff:
                    # Add the calculated seconds to the existing executed_seconds
                    activity_log.executed_seconds += min(int(seconds_diff), BROWSERBASE_SESSION_TIMEOUT)

            if ai_credits_consumed:
                # AI credits to update
                ai_credits_old = activity_log.ai_credits
                ai_credits_to_update = ai_credits_consumed - ai_credits_old

                # Add ai_credits to the activity_log
                activity_log.ai_credits = ai_credits_consumed


            # If there is change in the executed_seconds or ai_credits_consumed, we need to update the credits table
            if activity_log.executed_seconds != executed_seconds_old or ai_credits_to_update:
                update_credits(activity_log.org_id, seconds=activity_log.executed_seconds - executed_seconds_old, ai_credits=ai_credits_to_update)

            db.session.commit()
        
        logger.info(f"Activity log updated for test_run/compose_run {reference_id}")
    except Exception as e:
        logger.error(f"Error in update_activity_log: {e}")
        logger.error(traceback.format_exc())

def update_activity_log_with_ai_credits(current_user: dict, log_id: str=None, ai_credits_consumed: float=None) -> None:
    """
    Update an existing activity log entry in the database with ai_credits.
    """
    try:
        logger.info(f"Updating activity log with ai_credits for log_id: {log_id} and ai_credits_consumed: {ai_credits_consumed}")
        from app import app
        with app.app_context():
            # If log_id is not provided, we need to get the activity log by log_id and reference_id
            activity_log = ActivityLog.query.filter_by(log_id=log_id).first()
            
            if not activity_log:
                logger.info(f"Activity log with log_id {log_id} not found")
                return
            
            # Get the old ai_credits
            ai_credits_old = activity_log.ai_credits

            logger.info(f"Activity log org_id: {activity_log.org_id}")

            # If there is change in the ai_credits_consumed, we need to update the credits table
            if ai_credits_consumed and ai_credits_consumed > ai_credits_old:
                logger.info(f"Updating activity log for log_id: {log_id} and ai_credits_consumed: {ai_credits_consumed}")
                update_credits(activity_log.org_id, ai_credits=ai_credits_consumed - ai_credits_old)
                logger.info(f"Credits updated for log_id: {log_id}")

                # Add ai_credits to the activity_log
                activity_log.ai_credits = ai_credits_consumed

            db.session.commit()
        
    except Exception as e:
        logger.error(f"Error in update_activity_log_with_ai_credits: {e}")
        logger.error(traceback.format_exc())
        raise e