import os
import sentry_sdk
import subprocess
from flask import Flask
from database import db_url, db
from log_config.logger import logger
from dotenv import load_dotenv, find_dotenv
from utils.utils_constants import *
#from flask_cors import CORS

_app = None
_services_initialized = False

def get_app():
    global _app
    if _app is None:
        _app = Flask(__name__)
        #CORS(_app)
        create_app()
    return _app

def create_app():
    load_dotenv(find_dotenv('app.env'))
    
    # Initialize Sentry if configured
    SENTRY_URL = os.getenv('SENTRY_URL')
    SENTRY_ENV = os.getenv('SENTRY_ENV')
    if SENTRY_ENV is not None:
        sentry_sdk.init(
            dsn=SENTRY_URL,
            traces_sample_rate=1.0,
            profiles_sample_rate=1.0,
            environment=SENTRY_ENV,
        )
    
    # Configure database
    logger.info("Connecting to database")
    _app.config['SQLALCHEMY_DATABASE_URI'] = db_url
    _app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    _app.config['SQLALCHEMY_ECHO'] = True
    _app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
        "pool_size": 20,
        "max_overflow": 50
    }

    # Import and register blueprints
    from api.api_test import api_test
    from api.api_testrun import api_testrun
    from api.api_suite import api_suite
    from api.api_schedule import api_schedule
    from api.api_compose import api_compose
    from api.api_health import api_health
    from api.api_goal import api_goal
    from api.api_environment import api_environment
    from api.api_notification import api_notification
    from api.api_test_plan import api_test_plan
    from api.api_element_store import api_element_store
    from api.api_element import api_element
    from api.api_test_segment import api_test_segment
    from api.api_org_queue_config import api_org_queue_config
    from api.api_triagebot import api_triagebot
    from api.api_auth import api_auth

    _app.register_blueprint(api_test)
    _app.register_blueprint(api_testrun)
    _app.register_blueprint(api_suite)
    _app.register_blueprint(api_schedule)
    _app.register_blueprint(api_compose)
    _app.register_blueprint(api_health)
    _app.register_blueprint(api_goal)
    _app.register_blueprint(api_environment)
    _app.register_blueprint(api_notification)
    _app.register_blueprint(api_test_plan)
    _app.register_blueprint(api_element_store)
    _app.register_blueprint(api_element)
    _app.register_blueprint(api_test_segment)
    _app.register_blueprint(api_org_queue_config)
    _app.register_blueprint(api_triagebot)
    _app.register_blueprint(api_auth)
    
    # Initialize database
    logger.info("Creating tables")
    db.init_app(_app)
    with _app.app_context():
        db.create_all()

    return _app

def initialize_services():
    global _services_initialized
    if _services_initialized:
        return

    # Initialize and start container cleanup thread
    logger.info("Initializing container cleanup thread")
    from utils.container_cleanup_thread import start_cleanup_thread
    try:
        start_cleanup_thread()
    except Exception as e:
        logger.error(f"Error in starting container cleanup thread: {str(e)}")
        raise e

    # Initialize available rate limits from DB to Redis
    logger.info("Initializing available rate limits")
    from service.service_redis import initialize_available_rate_limits
    try:
        initialize_available_rate_limits()
    except Exception as e:
        logger.error(f"Error in initializing available rate limits: {str(e)}")
        # Don't raise - this is not critical for startup

    # Setup redis container if not already running. This is required for local mode.
    if os.getenv('ENVIRONMENT') is None or os.getenv('ENVIRONMENT') == 'local' or os.getenv('ENVIRONMENT') not in ['uat', 'prod']:
        logger.info("Setting up redis container")
        from utils.utils_docker import DockerManager
        try:
            docker_manager = DockerManager()
            docker_manager.setup_redis_and_network(
                redis_container_name=REDIS_CONTAINER_NAME,
                redis_image=REDIS_IMAGE,
                network_name=LITMUS_TEST_RUNNER_NETWORK_NAME
            )
        except Exception as e:
            logger.error(f"Error in setting up redis container: {str(e)}")
            logger.warning("Continuing without Redis container setup")

    _services_initialized = True