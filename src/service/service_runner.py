import time
import threading
import traceback
from log_config.logger import logger
from service.service_redis import *
from utils.utils_constants import TEST_RUN_RATE_LIMIT, TEST_RUNNER_THREAD_NAME
from service.service_test import run_test_implementation_helper
from service.service_queue import dequeue_run_request

class TestRunner():
    """
    Singleton class responsible for running tests in a separate thread.
    It dequeues test run requests from the Azure queue and runs the tests.
    Thread-safe singleton: only one instance and one thread can ever be created.
    """
    
    _instance = None
    _lock = threading.Lock()
    _initialized = False
    
    def __new__(cls):
        """
        Thread-safe singleton pattern implementation.
        Ensures only one instance is ever created.
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """
        Initialize TestRunner. Thread-safe - only initializes once.
        """
        if self._initialized:
            return
            
        with self._lock:
            if self._initialized:
                return
                
            logger.info("Initializing TestRunner singleton")
            self.rate_limit = TEST_RUN_RATE_LIMIT
            self.lock = threading.Lock()
            self._test_runner_thread = None
            
            # Start the worker thread
            self._start_worker_thread()
            
            self._initialized = True
            logger.info("TestRunner singleton initialized successfully")

    def _start_worker_thread(self):
        """
        Start the test runner worker thread. Thread-safe.
        Only creates thread if CELERY_PROCESS environment variable is None.
        """
        import os
        if os.getenv('CELERY_PROCESS') is not None:
            logger.info("CELERY_PROCESS environment variable is set, skipping test runner thread creation")
            return
        if self._test_runner_thread is not None and self._test_runner_thread.is_alive():
            logger.info("TestRunner worker thread is already running")
            return
            
        try:
            logger.info("Starting TestRunner worker thread")
            self._test_runner_thread = threading.Thread(
                target=self.test_runner, 
                name=TEST_RUNNER_THREAD_NAME,
                daemon=True
            )
            self._test_runner_thread.start()
            logger.info("TestRunner worker thread started successfully")
        except Exception as e:
            logger.error(f"Failed to start TestRunner worker thread: {str(e)}")
            logger.debug(traceback.format_exc())
            raise e

    def test_runner(self):
        """
        This function continuously runs in a separate thread and processes test run requests.
        It dequeues test run requests from the Azure queue from all the orgs and runs the tests.
        """
        logger.info("Test runner worker started")

        while True:
            try:
                # Get the list of org_ids from the redis
                org_ids = get_active_org_ids_from_current_runs()

                rate_limits = get_available_rate_limits(org_ids=org_ids)   # Return all the org_ids and their available rate limits

                # For each org_id, check if the rate limit is available
                for org_id in org_ids:
                    if self.rate_limit_exceeded(rate_limits, org_id):
                        continue
                    
                    # Dequeue a test run request
                    test_run_request = dequeue_run_request(org_id)
                    if test_run_request:
                        logger.info(f"Test run request dequeued for org {org_id}: {test_run_request}")

                        # Decrement the rate limit
                        decrement_available_rate_limit(org_id)
                        logger.info(f"Current rate limit for org {org_id}: {rate_limits[org_id]['available_limit']}")                    

                        self.run_dequeued_test(test_run_request)

                time.sleep(2)
            except Exception as e:
                logger.error(f"Error in test runner thread: {str(e)}")
                logger.debug(traceback.format_exc())

    def run_dequeued_test(self, test_run_request):
        """
        Run the dequeued test.
        """
        org_id = get_org_id_for_entity(test_id=test_run_request.get("test_id"), suite_obj=test_run_request.get("suite_obj"))
        test_id = test_run_request["test_id"]
        logger.info(f"Running test with ID: {test_id}")

        try:
            run_test_implementation_helper(test_run_request, self.lock)
        except Exception as e:
            logger.error(f"Error in running test: {str(e)}")
            logger.debug(traceback.format_exc())

            # increase the rate limit
            '''
            Increase ratelimit only in exception case. Because once docker container is started, it will be handled by the cleanup thread.
            '''
            self.increase_rate_limit(org_id)

    def rate_limit_exceeded(self, rate_limits: dict, org_id: str):
        """
        Check if the rate limit for processing test run requests has been exceeded.
        """
        org_data = rate_limits.get(org_id, {})
        available_limit = org_data.get("available_limit", 0)
        return available_limit <= 0

    def increase_rate_limit(self, org_id: str ):
        """
        Increment the available rate limit for the org in redis
        """
        with self.lock:
            increment_available_rate_limit(org_id)
            logger.info(f"Increased rate limit for org {org_id}")
            
    @staticmethod
    def is_thread_running(thread_name):
        """
        Check if a thread with the given name is running.
        """
        try:
            for thread in threading.enumerate():
                if thread.name == thread_name:
                    return True
            return False
        except Exception as e:
            logger.error(f"Error in checking if thread is running: {str(e)}")
            logger.debug(traceback.format_exc())
            raise e
    
    @classmethod
    def get_instance(cls):
        """
        Get the singleton instance. Thread-safe.
        """
        return cls()
    
    def is_initialized(self):
        """
        Check if the singleton is initialized.
        """
        return self._initialized
