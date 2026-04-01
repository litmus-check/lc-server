"""
Functions to manage the Azure queue.
This module provides functions to add, remove, and process items in Azure queue.
We enqueue test run requests and dequeue one at a time and process them.
"""

import os
import json
import traceback
from log_config.logger import logger
from utils.utils_constants import *
from azure.storage.queue import QueueServiceClient
from models.OrgQueueConfig import OrgQueueConfig

environment = os.getenv("ENVIRONMENT", DEFAULT_ENV)

if environment != DEFAULT_ENV:
    storage_account_key = os.getenv("STORAGE_ACCOUNT_KEY")
    storage_account_name = os.getenv("STORAGE_ACCOUNT_NAME")
    connection_string = f"DefaultEndpointsProtocol=https;AccountName={storage_account_name};AccountKey={storage_account_key};EndpointSuffix=core.windows.net"
    queue_service_client = QueueServiceClient.from_connection_string(connection_string)
else:
    Queue = {}  # Structure: {org_id: [queue_items]}

_queue_clients_cache = {}     # Structure: {queue_name: queue_client}

def _get_queue_client_for_org(org_id: str):
    """
    Get the queue client for a specific org.
    """
    try:
        # fetch org queue_name from DB
        from app import app
        with app.app_context():
            config = OrgQueueConfig.query.filter_by(org_id=org_id).first()
            queue_name = config.queue_name if config else None
            if queue_name and queue_name not in _queue_clients_cache:
                _queue_clients_cache[queue_name] = queue_service_client.get_queue_client(queue_name)
            return _queue_clients_cache[queue_name]
    except Exception as e:
        logger.error(f"Error getting queue client for org {org_id}: {str(e)}")
        logger.debug(traceback.format_exc())
        raise e

def enqueue_run_request(queue_obj: dict):
    """
    Enqueue a test run request to the Azure queue.
    """
    logger.info(f"Enqueueing test run request called")
    try:
        # Get org_id from suite_obj, or test_id using unified function
        from service.service_redis import get_org_id_for_entity
        org_id = get_org_id_for_entity(
            test_id=queue_obj.get("test_id"),
            suite_obj=queue_obj.get("suite_obj")
        )       
        if not org_id:
            logger.error("No org_id found in queue_obj")
            raise ValueError("org_id is required for queue operations")
        
        # Check the environment and use the appropriate queue
        if environment != DEFAULT_ENV:

            qclient = _get_queue_client_for_org(org_id)
            response = qclient.send_message(json.dumps(queue_obj, default=str))
        else:
            # In local environment, append to the org-specific queue
            if org_id not in Queue:
                Queue[org_id] = []
            Queue[org_id].append(queue_obj)
        logger.info(f"Enqueued test run request for org {org_id}: {queue_obj}")

        # Add the org id to the current runs in redis
        from service.service_redis import add_to_current_runs
        suite_run_id = queue_obj.get("suite_run_id", None)
        testrun_id = queue_obj.get("testrun_id", None)
        mode = queue_obj.get("run_mode", None)
        if suite_run_id and mode != TRIAGE_MODE and mode != HEAL_MODE:    # Triage mode is considered as a single test run and not part of a suite run
            add_to_current_runs(suite_run_id, org_id)
        else:
            add_to_current_runs(testrun_id, org_id)

    except Exception as e:
        logger.error(f"Error enqueueing test run request: {str(e)}")
        logger.debug(traceback.format_exc())
        raise e

def dequeue_run_request(org_id: str = None):
    """
    Dequeue a test run request from the Azure queue for a specific org.
    """
    try:
        if not org_id:
            logger.error("org_id is required for dequeue operations")
            return None
            
        # Check the environment and use the appropriate queue
        if environment != DEFAULT_ENV:
            # Get queue client for the specific org
            qclient = _get_queue_client_for_org(org_id)
            if not qclient:
                return None
                
            # Dequeue a test run request
            messages = qclient.receive_messages(max_messages=1)

            for message in messages:
                content = json.loads(message.content)
                qclient.delete_message(message)
                return content
        else:
            # In local environment, pop from the org-specific queue
            if org_id in Queue and len(Queue[org_id]) > 0:
                return Queue[org_id].pop(0)
            
        return None
    except Exception as e:
        logger.error(f"Error dequeueing test run request: {str(e)}")
        logger.debug(traceback.format_exc())
        raise e

def create_queue(queue_name: str, org_id: str = None):
    """
    Create a new queue in Azure or initialize org-specific queue in local environment.
    """
    if environment != DEFAULT_ENV:
        try:
            queue_service_client.create_queue(queue_name)
            logger.info(f"Created Azure queue: {queue_name}")
        except Exception as e:
            logger.error(f"Error creating Azure queue {queue_name}: {str(e)}")
            raise e
    else:
        # In local environment, initialize the org-specific queue
        if org_id:
            if org_id not in Queue:
                Queue[org_id] = []
                logger.info(f"Initialized local queue for org: {org_id}")
            else:
                logger.info(f"Local queue for org {org_id} already exists")
        else:
            logger.warning("org_id is required for local queue initialization")