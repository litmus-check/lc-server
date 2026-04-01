import os
from celery import Celery
from log_config.logger import logger
from dotenv import load_dotenv, find_dotenv
from utils.utils_constants import SCHEDULED_TRIGGER
import sentry_sdk
from sentry_sdk.integrations.celery import CeleryIntegration
from utils.utils_slack import schedule_run_error_notification
load_dotenv(find_dotenv("app.env"))

app = Celery('tasks', broker=os.getenv('REDIS_URL'))

app.conf.beat_scheduler = 'redbeat.RedBeatScheduler'

# Configure Celery
app.conf.update(
    worker_pool_restarts=True,
    timezone='UTC',
    enable_utc=True,  # Ensure UTC is enabled
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json'
)

# Start sentry for celery
sentry_sdk.init(
    dsn=os.getenv('SENTRY_URL'),
    integrations=[CeleryIntegration()],
    traces_sample_rate=1.0,
    profiles_sample_rate=1.0,
    environment=os.getenv('SENTRY_ENV'),
)

# @app.on_after_configure.connect
# def setup_periodic_tasks(sender: Celery, **kwargs):
#     # Calls test('hello') every 10 seconds.
#     sender.add_periodic_task(5.0, test.s('hello'), name='add every 5')

#     # Calls test('hello') every 30 seconds.
#     # It uses the same signature of previous task, an explicit name is
#     # defined to avoid this task replacing the previous one defined.
#     # sender.add_periodic_task(30.0, test.s('hello'), name='add every 30')

#     # Calls test('world') every 30 seconds
#     # sender.add_periodic_task(30.0, test.s('world'), expires=10)

#     # Executes every Monday morning at 7:30 a.m.
#     # sender.add_periodic_task(
#     #     crontab(hour=7, minute=30, day_of_week=1),
#     #     test.s('Happy Mondays!'),
#     # )
@app.task(name='tasks.test')
def test():
    logger.info("test")

@app.task(name='tasks.run_suite')
def run_suite(current_user, suite_id, browser, config):
    """
    Celery task wrapper for running suite implementation
    """
    try:
        logger.info(f"Starting run_suite task for suite_id: {suite_id}")
        logger.info(f"Current user: {current_user}")
        logger.info(f"Config: {config}")

        # Check for tag_filter in global_config
        if config and 'tag_filter' in config:
            tag_filter = config['tag_filter']
        else:
            tag_filter = None

        # Check if the config is global_config or old config type
        emails = None
        if config and 'environment_id' in config:  # global_config type
            environment_id = config['environment_id']
            # Extract emails from global_config if present (before extracting playwright config)
            emails = config.get('emails')
            config = config['config']
        else:                       # old config type
            environment_id = None
        
        # Use the Flask app context
        from app import app
        with app.app_context():
            from service.service_suite import run_suite_implementation
            request_data = {}
            if config:
                request_data['config'] = config
            if environment_id:
                request_data['environment_id'] = environment_id
            if tag_filter:
                request_data['tag_filter'] = tag_filter
            if emails is not None:
                request_data['emails'] = emails
            result, status_code = run_suite_implementation(current_user, suite_id, browser, request_data, trigger=SCHEDULED_TRIGGER)

            if status_code != 200:
                # send a slack notification
                error = result.get('error', 'Unknown error')
                schedule_run_error_notification(suite_id, f"Unable to start schedule run for suite_id {suite_id}, error: {error}", send_to_integration=True)
            logger.info(f"run_suite_implementation completed with result: {result}")
            return result, status_code
    except Exception as e:
        logger.error(f"Error in run_suite: {str(e)}")
        # send a slack notification
        schedule_run_error_notification(suite_id, f"Unable to start schedule run for suite_id: {suite_id}.", send_to_integration=True)
        raise
