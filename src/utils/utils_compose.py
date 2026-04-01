import traceback
import json
from database import db
from log_config.logger import logger
from browserbase import RateLimitError
from service.service_activity_log import *
from service.service_browserbase import *
from utils.utils_constants import *
from models.ComposeSession import ComposeSession
from utils.utils_docker import DockerManager

from service.service_redis import get_compose_session_from_redis
from datetime import datetime, timezone

def update_compose_session_db(compose_id: str, status: str = None, environment: str = None, browserbase_session_id: str = None, environment_variables: dict = None):
    """
    Update the compose session db
    """
    try:
        logger.info(f"Getting compose session from db for compose_id:  {compose_id} {type(compose_id)}")
        compose_session = ComposeSession.query.filter_by(compose_id=compose_id).first()
        logger.info(f"Compose session: {compose_session.serialize()}")
        if status:
            compose_session.status = status
            if status == "completed":
                compose_session.end_date = db.func.now()
            elif status == "running":       # When the compose session is started again, the end_date is set to None
                compose_session.end_date = None
        if environment:
            compose_session.environment = environment
        if browserbase_session_id:
            compose_session.browserbase_session_id = browserbase_session_id
        if environment_variables:
            compose_session.environment_variables = json.dumps(environment_variables)
        db.session.commit()
    except Exception as e:
        logger.error(f"Error in update_compose_session_db: {e}")
        logger.debug(traceback.format_exc())
        raise e
    
def create_compose_session_db(current_user: dict, compose_id: str, environment: str = None, browserbase_session_id: str = None, test_id: str = None, user_id: str = None, config: dict = None, source: str = COMPOSE_USER, agent_type: str = None, agent_args: dict = None, environment_variables: dict = None):
    """
    Create a compose session db
    """
    try:
        # Create new compose session object
        compose_session = ComposeSession(
            compose_id=compose_id, 
            test_id=test_id, 
            browserbase_session_id=browserbase_session_id,  # Store browserbase session ID or None for litmus_cloud
            user_id=current_user.get("user_id"),
            environment=environment,                         # Store the environment as browserbase or litmus_cloud
            config=json.dumps(config), 
            environment_variables=json.dumps(environment_variables),
            source=source,
            agent_type=agent_type,
            agent_args=json.dumps(agent_args)
        )

        db.session.add(compose_session)
        db.session.commit()

        return compose_session
    except Exception as e:
        logger.error(f"Error in create_compose_session_db: {e}")
        logger.debug(traceback.format_exc())
        raise e
    
def compose_session_creation_helper(current_user: dict, compose_id: str, activity_log_id: str, environment: str, config: dict = DEFAULT_PLAYWRIGHT_CONFIG, variables_dict: dict = None, additional_labels: dict = None):
    """
    Helper function to create a compose session
    Args:
        current_user: dict
        compose_id: str
        activity_log_id: str
        environment: str
    Returns:
        tuple: (browserbase_session_id, live_url)
    """
    # Initialize variables for cleanup
    session = None
    container = None
    
    try:
        # Determine browser type based on environment
        browser_type = LITMUS_CLOUD_ENV if environment == LITMUS_CLOUD_ENV else BROWSERBASE_ENV
        logger.info(f"[{compose_id}] Using browser type: {browser_type}")
        
        # Check if there are any active browserbase sessions for the user and kill them
        # Note: This will only kill the browserbase sessions that are in compose mode.
        # Check if the user_email is from domain @litmuscheck.com or finigami.com
        is_litmuscheck_user = current_user.get('email','').endswith('@litmuscheck.com') or current_user.get('email','').endswith('@finigami.com')
        if browser_type == BROWSERBASE_ENV and not is_litmuscheck_user:
            try:
                kill_active_browserbase_sessions(current_user)
            except Exception as e:
                logger.error(f"Error in kill_active_browserbase_sessions: {e}")
                logger.debug(traceback.format_exc())
        
        # Create Docker container for compose session
        docker_manager = DockerManager()

        # Initialize variables for browserbase session
        live_url = None
        browserbase_session_id = None
        cdp_url = None

        # Only create browserbase session if using browserbase environment
        if browser_type == BROWSERBASE_ENV:
            try:
                session = get_browserbase_session(timeout=BROWSERBASE_SESSION_TIMEOUT, config=config)    # Create a new browserbase session
                live_url = get_session_debug_urls(session.id).debugger_fullscreen_url
                browserbase_session_id = session.id
                cdp_url = session.connect_url
                logger.info(f"[{compose_id}] Successfully created browserbase session with ID: {session.id}")
                logger.info(f"[{compose_id}] Live URL: {session.connect_url}")
            except RateLimitError as e:
                logger.error(f"[{compose_id}] Rate limit exceeded while creating browserbase session: {e}")
                raise Exception("Server is busy, please try again later")
            except Exception as e:
                logger.error(f"[{compose_id}] Unable to create browserbase session: {str(e)}")
                logger.debug(traceback.format_exc())
                raise Exception("Unable to create browserbase session")
        
        try:
            if additional_labels and isinstance(additional_labels, dict):
                labels_values = {"activity_log_id": activity_log_id, "current_user": json.dumps(current_user), "run_id": compose_id, **additional_labels}
            else:
                labels_values = {"activity_log_id": activity_log_id, "current_user": json.dumps(current_user), "run_id": compose_id}

            current_environment = os.getenv('ENVIRONMENT', DEFAULT_ENV)
            if current_environment == DEFAULT_ENV:
                # Spin up Docker container with compose parameters
                container = docker_manager.spin_up_docker_container(
                    playwright_instructions=None,
                    instructions=None,
                    mode="compose",
                    run_id=compose_id,
                    browser=browser_type,
                    browserbase_session_id=browserbase_session_id,
                    cdp_url=cdp_url,
                    config=json.dumps(config),
                    variables_dict=variables_dict,
                    labels=labels_values
                )

                logger.info(f"[{compose_id}] Successfully created Docker container with ID: {container.id}")
            else:
                from utils.utils_aks import AksManager
                aks_manager = AksManager()
                # Spin up AKS pod with compose parameters
                pod = aks_manager.create_pod(
                    playwright_instructions=None,
                    instructions=None,
                    mode="compose",
                    run_id=compose_id,
                    browser=browser_type,
                    browserbase_session_id=browserbase_session_id,
                    cdp_url=cdp_url,
                    config=config,
                    variables_dict=variables_dict,
                    labels=labels_values
                )

                logger.info(f"[{compose_id}] Successfully created AKS pod with ID: {pod.metadata.name}")
            
            
            # Return the expected tuple
            return browserbase_session_id, live_url

        except Exception as e:
            logger.error(f"[{compose_id}] Unable to create Docker container: {str(e)}")
            logger.debug(traceback.format_exc())
            raise Exception("Unable to create Docker container")
            
    except Exception as e:
        logger.error(f"[{compose_id}] Unexpected error in compose_session_creation_helper: {str(e)}")
        logger.debug(traceback.format_exc())
        raise Exception("An unexpected error occurred while creating compose session")
    
def kill_active_browserbase_sessions(current_user: dict):
    """
    Kill active browserbase sessions for a user
    """
    try:
        user_id = current_user.get("user_id")
        logger.info(f"Killing active browserbase sessions for user {user_id}")
        active_sessions = ComposeSession.query.filter_by(user_id=user_id, status="running").all()
        for session in active_sessions:
            try:
                # Only close browserbase session if browserbase_session_id exists
                if session.browserbase_session_id:
                    close_browserbase_session(session.browserbase_session_id)
                session.status = "completed"
                session.end_date = db.func.now()


                # Check for the ai_credits and update the activity_log and credits table
                ai_credits = None
                compose_session = get_compose_session_from_redis(session.compose_id)
                if not compose_session:
                    logger.error(f"Compose session not found for compose_id: {session.compose_id}")
                else:
                    ai_credits = compose_session.get("ai_credits") if compose_session else None

                # Update the activity log table
                update_activity_log(current_user, reference_id=session.compose_id, end_time=datetime.now(timezone.utc), ai_credits_consumed=ai_credits)

                current_environment = os.getenv('ENVIRONMENT', DEFAULT_ENV)
                if current_environment == DEFAULT_ENV:
                    # Kill the docker container
                    docker_manager = DockerManager()
                    docker_manager.kill_container_with_label({"mode": "compose", "run_id": session.compose_id})
                else:
                    from utils.utils_aks import AksManager
                    aks_manager = AksManager()
                    aks_manager.kill_pods_with_label({"mode": "compose", "run_id": session.compose_id})

            except Exception as e:
                logger.error(f"Error closing Browserbase session {session.browserbase_session_id}: {e}")
                logger.debug(traceback.format_exc())
        db.session.commit()
    except Exception as e:
        logger.error(f"Error killing Browserbase sessions for user {user_id}: {e}")
        logger.debug(traceback.format_exc())
        raise e

def get_compose_session_from_db(compose_id: str):
    """
    Get a compose session from the db
    """
    try:
        logger.info(f"Getting compose session from db for compose_id:  {compose_id} {type(compose_id)}")
        compose_session = ComposeSession.query.filter_by(compose_id=compose_id).first()
        if not compose_session:
            logger.error(f"Compose session not found for compose_id: {compose_id}")
            raise Exception(f"Compose session not found for compose_id: {compose_id}")
        logger.info(f"Compose session: {compose_session.serialize()}")
        return compose_session.serialize()
    except Exception as e:
        logger.error(f"Error getting compose session from db: {e}")
        logger.debug(traceback.format_exc())
        raise e