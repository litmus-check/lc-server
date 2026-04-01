import os
import threading
import time
from log_config.logger import logger
from utils.utils_constants import DOCKER_CONTAINER_CHECK_INTERVAL, DEFAULT_ENV


# Global state management
_cleanup_thread = None
_cleanup_lock = threading.Lock()
_initialized = False

def container_cleanup_worker():
    """
    Worker function that runs in a separate thread to clean up Docker containers.
    """
    logger.info("Container cleanup worker started")
    
    while True:
        try:
            time.sleep(DOCKER_CONTAINER_CHECK_INTERVAL)
            env = os.getenv('ENVIRONMENT', DEFAULT_ENV)
            if env == DEFAULT_ENV:
                from utils.utils_docker import DockerManager
                docker_manager = DockerManager()
                docker_manager.check_exited_containers_and_cleanup()
                docker_manager.check_exited_heal_containers_and_cleanup()
            else:
                from utils.utils_aks import AksManager
                aks_manager = AksManager()
                aks_manager.check_exited_pods_and_cleanup()
                aks_manager.check_exited_heal_pods_and_cleanup()
        except Exception as e:
            logger.error(f"Error in container cleanup worker: {e}")

def start_cleanup_thread():
    """
    Start the container cleanup thread if it's not already running.
    Thread-safe function that prevents multiple threads from being created.
    Only creates thread if CELERY_PROCESS environment variable is None.
    """
    global _cleanup_thread, _initialized

    # Check if CELERY_PROCESS environment variable is set
    if os.getenv('CELERY_PROCESS') is not None:
        logger.info("CELERY_PROCESS environment variable is set, skipping container cleanup thread creation")
        return True
    
    with _cleanup_lock:
        if _initialized:
            logger.info("Container cleanup thread already initialized")
            return True
        
        try:
            logger.info("Initializing container cleanup thread")
            _cleanup_thread = threading.Thread(
                target=container_cleanup_worker, 
                name="ContainerCleanupThread",
                daemon=True
            )
            _cleanup_thread.start()
            _initialized = True
            logger.info("Container cleanup thread started successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start container cleanup thread: {e}")
            return False 