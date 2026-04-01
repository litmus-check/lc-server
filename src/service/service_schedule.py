import json
from models.Schedule import Schedule
from database import db
from datetime import datetime, timezone, timedelta
import uuid
from log_config.logger import logger
import traceback
from redbeat.schedulers import RedBeatSchedulerEntry
from tasks import app
import celery
from service.service_suite import return_suite_obj
from utils.utils_playwright_config import get_config_from_request
from service.service_environment import validate_environment_access_implementation
from utils.utils_email import validate_override_emails

def test_schedule_implementation():
    """
    Test the schedule implementation
    """
    try:
        interval = celery.schedules.schedule(run_every=10)
        entry = RedBeatSchedulerEntry(
            'schedule-blabla',
            'tasks.test',  # full task name
            interval,
            args=[],  # Arguments for the task
            app=app,  # Add the app parameter
            enabled=True  # Add the enabled parameter
        )
        entry.save()
        return {"message": "Schedule created successfully"}, 200
    except Exception as e:
        logger.error(f"Error in test_schedule_implementation: {str(e)}")
        logger.debug(traceback.print_exc())
        return {"error": str(e)}, 400

def create_schedule_implementation(current_user, suite_id, browser, data):
    """
    Create a new schedule for a suite
    Args:
        suite_id: UUID of the suite
        browser: Browser type
        data: Dictionary containing schedule details
    Returns:
        Tuple of (response_dict, status_code)
    """
    try:
        # Verify suite exists and user has access
        
        suite = return_suite_obj(current_user, suite_id)
        
        if not suite:
           return {"error": "Suite not found or user does not have access to it"}, 404

        # Validate required fields
        schedule_details = data.get('schedule_details')
        start_date_time, run_every_hours = validate_schedule(schedule_details)

        # Extract the config from the request data
        config = data.get('config')

        # Validate tag_filter if provided
        tag_filter = data.get('tag_filter')
        from utils.utils_tags import validate_tag_filter
        error_message, status_code = validate_tag_filter(tag_filter)
        if status_code != 200:
            return {"error": error_message}, status_code

        environment_id = data.get('environment_id')
        environment_name = data.get('environment_name')
        environment = None
        if environment_id or environment_name:
            # check if environment_id is valid and user has access to it
            environment, error_msg, status_code = validate_environment_access_implementation(current_user, environment_id, environment_name, suite_id)
            if status_code != 200:
                return {"error": error_msg}, status_code
    
        # Create new schedule instance
        try:
            new_schedule = Schedule(
                id=str(uuid.uuid4()),
                suite_id=suite_id,
                org_id=current_user['org_id'],
                run_every_hours=run_every_hours,
                start_date_time=start_date_time,
                config=json.dumps(config) if config else None,
                environment_id=environment.environment_id if environment else None,
                tag_filter=json.dumps(tag_filter) if tag_filter else None
            )
        
        #Save to database
            db.session.add(new_schedule)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error in create_schedule_implementation: {str(e)}")
            logger.debug(traceback.print_exc())
            return {"error": str(e)}, 400

        # Extract and validate emails from request data if present
        emails = data.get('emails')
        if emails is not None:
            is_valid, error_message = validate_override_emails(emails)
            if not is_valid:
                return {"error": error_message}, 400
        
        # Create a new dict of global_config that holds config, environment_id, and emails.
        # Format {config: config, environment_id: environment_id, tag_filter: tag_filter, emails: emails}
        global_config = {
            'config': config,
            'environment_id': environment_id,
            'tag_filter': tag_filter
        }
        
        # Add emails to global_config if provided (even if empty list)
        if emails is not None:
            global_config['emails'] = emails

        # Create dynamic RedBeat entry
        logger.info(f"Config: {config}")
        interval = celery.schedules.schedule(run_every=run_every_hours * 3600)
        # Calculate last_run_at by subtracting the interval from start date time
        # This ensures the next run will happen at the correct interval from the start time
        last_run_time = get_last_run_at(start_date_time, run_every_hours)
        entry = RedBeatSchedulerEntry(
            f'schedule-{suite_id}-{new_schedule.id}',
            'tasks.run_suite',  # full task name
            interval,
            args=[current_user, suite_id, browser, global_config],
            app=app,
            enabled=True,
            last_run_at=last_run_time
        )
        entry.save()  # Persist the task to Redis!
        
        return new_schedule.to_dict(), 200
        #return {"message": "Schedule created successfully"}, 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error in create_schedule_implementation: {str(e)}")
        logger.debug(traceback.print_exc())
        return {"error": str(e)}, 400

def update_schedule_implementation(current_user, suite_id, schedule_id, browser, data):
    """
    Update an existing schedule for a suite
    Args:
        suite_id: UUID of the suite
        schedule_id: UUID of the schedule to update
        browser: Browser type
        data: Dictionary containing schedule details to update
    Returns:
        Tuple of (response_dict, status_code)
    """
    try:
        # Verify suite exists and user has access
        suite = return_suite_obj(current_user, suite_id)
        if not suite:
            return {"error": "Suite not found or user does not have access to it"}, 404

        # Get the schedule
        schedule = Schedule.query.filter_by(id=schedule_id, suite_id=suite_id).first()
        if not schedule:
            return {"error": "Schedule not found"}, 404

        # Extract the config from the request data
        config, status_code = get_config_from_request(data, schedule=schedule)
        if status_code != 200:
            return config, status_code
        schedule.config = json.dumps(config)

        # Validate tag_filter if provided
        tag_filter = json.loads(schedule.tag_filter) if schedule.tag_filter else None
        if 'tag_filter' in data:
            tag_filter = data.get('tag_filter')
            from utils.utils_tags import validate_tag_filter
            error_message, status_code = validate_tag_filter(tag_filter)
            if status_code != 200:
                return {"error": error_message}, status_code
            schedule.tag_filter = json.dumps(tag_filter) if tag_filter else None

        # Validate schedule details if provided
        schedule_details = data.get('schedule_details')
        start_date_time, run_every_hours = validate_schedule(schedule_details)

        environment_id = schedule.environment_id
        if 'environment_id' in data or 'environment_name' in data:
            environment_id = data.get('environment_id', schedule.environment_id)
            environment_name = data.get('environment_name')
            # check if environment_id is valid and user has access to it
            environment, error_msg, status_code = validate_environment_access_implementation(current_user, environment_id, environment_name, suite_id)
            if status_code != 200:
                return {"error": error_msg}, status_code

            schedule.environment_id = environment.environment_id if environment else schedule.environment_id    # Fallback to existing environment_id if not found
            

        # Extract and validate emails from request data if present
        emails = data.get('emails')
        if emails is not None:
            is_valid, error_message = validate_override_emails(emails)
            if not is_valid:
                return {"error": error_message}, 400
        
        # Create a new dict of global_config that holds config, environment_id, and emails.
        # Format {config: config, environment_id: environment_id, tag_filter: tag_filter, emails: emails}
        global_config = {
            'config': config,
            'environment_id': environment_id
        }
        
        if tag_filter:
            global_config['tag_filter'] = tag_filter

        # Add emails to global_config if provided (even if empty list)
        if emails is not None:
            global_config['emails'] = emails

        # Update RedBeat schedule first
        try:
            # Create the schedule name
            schedule_name = f'schedule-{suite_id}-{schedule.id}'
            logger.info(f"Looking for RedBeat schedule with name: {schedule_name}")
            
            # Try to load the existing entry
            try:
                entry = RedBeatSchedulerEntry.from_key(f'redbeat:{schedule_name}', app=app)
                logger.info(f"Found existing RedBeat entry: {entry}")
            except KeyError:
                logger.warning(f"No RedBeat entry found with name: {schedule_name}")
                return {"error": "Schedule entry not found in scheduler"}, 404
            
            # Update the existing entry
            entry.schedule = celery.schedules.schedule(run_every=run_every_hours * 3600)
            # Calculate last_run_at by subtracting the interval from start date time
            last_run_time = get_last_run_at(start_date_time, run_every_hours)
            # entry.last_run_at = last_run_time
            entry.reschedule(last_run_time)
            entry.args = [current_user, suite_id, browser, global_config]
            entry.save()
            logger.info(f"Updated RedBeat entry: {entry}")
            
        except Exception as e:
            logger.error(f"Error updating RedBeat schedule: {str(e)}")
            logger.debug(traceback.print_exc())
            return {"error": f"Failed to update schedule in scheduler: {str(e)}"}, 400

        # Now update the database
        if schedule_details:
            if 'run_every_hours' in schedule_details:
                schedule.run_every_hours = schedule_details['run_every_hours']
            if 'start_date_time' in schedule_details:
                schedule.start_date_time = datetime.strptime(schedule_details['start_date_time'], "%Y-%m-%dT%H:%M")

        # Save changes to database
        db.session.commit()

        return schedule.to_dict(), 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error in update_schedule_implementation: {str(e)}")
        logger.debug(traceback.print_exc())
        return {"error": str(e)}, 400

def delete_schedule_implementation(current_user, suite_id, schedule_id):
    """
    Delete a schedule for a suite
    Args:
        suite_id: UUID of the suite
        schedule_id: UUID of the schedule to delete
    Returns:
        Tuple of (response_dict, status_code)
    """
    try:
        # Verify suite exists and user has access
        suite = return_suite_obj(current_user, suite_id)
        if not suite:
            return {"error": "Suite not found or user does not have access to it"}, 404

        # Get the schedule
        schedule = Schedule.query.filter_by(id=schedule_id, suite_id=suite_id).first()
        if not schedule:
            return {"error": "Schedule not found"}, 404

        # Delete from RedBeat first
        try:
            schedule_name = f'schedule-{suite_id}-{schedule_id}'
            logger.info(f"Deleting RedBeat schedule with name: {schedule_name}")
            
            # Try to find and delete the RedBeat entry
            try:
                entry = RedBeatSchedulerEntry.from_key(f'redbeat:{schedule_name}', app=app)
                entry.delete()
                logger.info(f"Deleted RedBeat entry: {entry}")
            except KeyError:
                logger.warning(f"No RedBeat entry found with name: {schedule_name}")
                
        except Exception as e:
            logger.error(f"Error deleting RedBeat schedule: {str(e)}")
            logger.debug(traceback.print_exc())
            return {"error": f"Failed to delete schedule from scheduler: {str(e)}"}, 400

        # Now delete from database
        db.session.delete(schedule)
        db.session.commit()

        return {"message": "Schedule deleted successfully"}, 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error in delete_schedule_implementation: {str(e)}")
        logger.debug(traceback.print_exc())
        return {"error": str(e)}, 400

def validate_schedule(schedule_details: dict):
    if not schedule_details:
            return {"error": "schedule_details is required"}, 400

    run_every_hours = schedule_details.get('run_every_hours')
    start_date_time = schedule_details.get('start_date_time')
    
    if not run_every_hours or not start_date_time:
        logger.error(f"Error in validate_schedule: run_every_hours and start_date_time are required")
        raise ValueError("run_every_hours and start_date_time are required")

    # Convert run_every_hours to integer
    try:
        run_every_hours = int(run_every_hours)
        if run_every_hours <= 0:
            return {"error": "run_every_hours must be greater than 0"}, 400
    except ValueError:
        logger.error(f"Error in validate_schedule: {str(e)}")
        logger.debug(traceback.print_exc())
        raise ValueError("run_every_hours must be a valid integer")

    # Parse the UTC date time string
    try:
        # The input is expected to be in UTC format: "2025-04-14T18:21"
        start_date_time = datetime.strptime(start_date_time, "%Y-%m-%dT%H:%M")
        now = datetime.now(timezone.utc)
        logger.info(f"Input time (UTC): {start_date_time}")
        logger.info(f"Current time (UTC): {now}")
        return start_date_time, run_every_hours
    except ValueError as e:
        logger.error(f"Error in validate_schedule: {str(e)}")
        logger.debug(traceback.print_exc())
        raise ValueError("Invalid date format. Expected format: YYYY-MM-DDTHH:MM in UTC")
    
def get_last_run_at(start_date_time, run_every_hours):
    last_run_time = start_date_time - timedelta(hours=run_every_hours)
    if last_run_time.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        logger.info(f"Last run time: {last_run_time}")
        return last_run_time
    else:
        return None