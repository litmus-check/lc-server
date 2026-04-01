import os
from log_config.logger import logger
from browserbase import Browserbase
bb = Browserbase(api_key=os.environ["BROWSERBASE_API_KEY"])

def get_browserbase_session(timeout=None, config=None):
    logger.info("Creating Browserbase session")
    try:
        # Extract the required fields from config
        viewport = config.get('viewport')
        device_pixel_ratio = config.get('device_pixel_ratio')
        device_type = config.get('device').get('type')
        device_os = config.get('device').get('device_config').get('os')
        browser = config.get('browser')

        logger.info(f"Browserbase config: {config}")

        if timeout is None:
            # Default timeout set by browserbase
            session = bb.sessions.create(
                project_id=os.environ["BROWSERBASE_PROJECT_ID"],
                region="us-east-1",  # Ensure US East region
                browser_settings={
                    "fingerprint": {
                        "browsers": [browser],
                        "devices": [device_type],
                        "operating_systems": [device_os]
                    },
                    "viewport":{
                        "width": int(viewport.get('width')),
                        "height": int(viewport.get('height'))
                    }
                }
            )
        else:
            session = bb.sessions.create(
                project_id=os.environ["BROWSERBASE_PROJECT_ID"], 
                api_timeout=timeout,
                region="us-east-1",  # Ensure US East region
                browser_settings={
                    "fingerprint": {
                        "browsers": [browser],
                        "devices": [device_type],
                        "operating_systems": [device_os]
                    },
                    "viewport":{
                        "width": int(viewport.get('width')),
                        "height": int(viewport.get('height'))
                    }
                }
            )
        return session
    except Exception as e:
        logger.error(f"Error creating Browserbase session: {e}")
        raise e

    
def get_session_debug_urls(session_id: str):
    """
    Get debug URLs for a Browserbase session.
    
    Args:
        session_id (str): The ID of the Browserbase session
    """
    try:
        debug_info = bb.sessions.debug(session_id)
        return debug_info
    except Exception as e:
        logger.error(f"Error getting debug URLs for session {session_id}: {e}")
        raise e
    
def close_browserbase_session(session_id: str):
    """
    Close a Browserbase session and its browser instances.
    """
    try:
        # Update session status
        update_browserbase_session(session_id, close_session=True)
        logger.info(f"Browserbase session {session_id} closed successfully")
    except Exception as e:
        logger.error(f"Error closing Browserbase session {session_id}: {e}")
        raise e
    
def update_browserbase_session(session_id: str, timeout: int = 1, close_session: bool = False):
    try:
        if close_session:
            session = bb.sessions.update(session_id, project_id=os.environ["BROWSERBASE_PROJECT_ID"], timeout=1, status="REQUEST_RELEASE")
        # else:
        #     session = bb.sessions.update(session_id, project_id=os.environ["BROWSERBASE_PROJECT_ID"], timeout=timeout, status="REQUEST_RELEASE")
        # logger.info(f"Browserbase session {session_id} updated to status {session.status}")
    except Exception as e:
        logger.error(f"Error updating Browserbase session {session_id}: {e}")
        raise e
    