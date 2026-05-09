import os
import json
import traceback
import uuid
from datetime import datetime, timezone

from log_config.logger import logger
from dotenv import load_dotenv, find_dotenv

# Mirrors docker-based flows
from utils.utils_constants import *
from service.service_queue import enqueue_run_request
from service.service_activity_log import update_activity_log, update_activity_log_with_ai_credits
from service.service_redis import *
from utils.utils_test import update_test_result_status, update_test_status, update_suite_run_status
from utils.instruction_formatter import format_instruction_for_display
from service.service_test import *
from service.service_triage import add_test_to_queue_with_triage_mode
from service.service_heal import add_test_to_queue_with_heal_mode

from service.service_runner import TestRunner
test_runner = TestRunner()

# Kubernetes client
try:
    from kubernetes import client as k8s_client, config as k8s_config
    from kubernetes.client import V1Pod
except Exception:
    k8s_client = None
    k8s_config = None
    V1Pod = None

load_dotenv(find_dotenv("app.env"))

# Environment variables
AZURE_CONTAINER_REGISTRY_URL = os.getenv("AZURE_CONTAINER_REGISTRY_URL", "litmuscheckuat.azurecr.io/")
KUBERNETES_NAMESPACE = os.getenv("KUBERNETES_NAMESPACE", "test-runners")
AZURE_PVC_NAME = os.getenv("AZURE_PVC_NAME", "azurefile-pvc")
LOGS_VOLUME_NAME = os.getenv("LOGS_VOLUME_NAME", "logs-volume")


def get_namespace() -> str:
    return KUBERNETES_NAMESPACE


def get_logs_volume_mount():
    """Return (volume, mount) to back `/app/logs` with a PVC if configured.

    This expects `AZURE_BLOB_LOGS_PVC` to reference a PVC provisioned by an
    Azure CSI driver (Blob or Files) so container logs persist to cloud storage.
    """
    pvc_name = AZURE_PVC_NAME
    if not pvc_name:
        return None, None
    volume = k8s_client.V1Volume(
        name=LOGS_VOLUME_NAME,
        persistent_volume_claim=k8s_client.V1PersistentVolumeClaimVolumeSource(claim_name=pvc_name),
    )
    mount = k8s_client.V1VolumeMount(name="logs-volume", mount_path="/app/logs")
    return volume, mount


class AksManager:
    instance = None

    def __new__(cls):
        if cls.instance is None:
            cls.instance = super(AksManager, cls).__new__(cls)
            cls.instance.initialize()
        return cls.instance

    def initialize(self):
        try:
            # Prefer in-cluster, fallback to kubeconfig
            try:
                k8s_config.load_incluster_config()
                logger.info("Loaded in-cluster Kubernetes config")
            except Exception:
                kubeconfig = os.getenv("KUBECONFIG")
                if kubeconfig and os.path.exists(kubeconfig):
                    k8s_config.load_kube_config(config_file=kubeconfig)
                else:
                    k8s_config.load_kube_config()
                logger.info("Loaded kubeconfig for Kubernetes client")

            self.core = k8s_client.CoreV1Api()
            logger.info("Initialized Kubernetes CoreV1Api client")
        except Exception as e:
            logger.error(f"Failed to initialize AKS client: {e}")
            logger.info(traceback.format_exc())
            raise

    def create_pod(self,playwright_instructions: str,instructions: str,mode: str,run_id: str,browser: str,browserbase_session_id: str,cdp_url: str,config: dict = None,variables_dict: dict = None,blob_url: str = None,labels: dict = {}) -> V1Pod:
        """Create a Kubernetes Pod that mirrors the Docker test container.

        - Uses same image/labels/arguments as Docker version
        - Mounts `/app/logs` if a PVC is configured (to persist logs to Azure)
        - Sets restartPolicy=Never so completion maps to Succeeded/Failed
        """
        try:
            namespace = get_namespace()
            image = AZURE_CONTAINER_REGISTRY_URL + LITMUS_TEST_RUNNER_IMAGE

            # Build args to mirror Docker invocation of: node dist/index.js <args>
            cli_args = [
                playwright_instructions,
                instructions,
                mode,
                run_id,
                browser,
                browserbase_session_id,
                cdp_url,
                json.dumps(config or {}),
                json.dumps(variables_dict or {}),
                blob_url or '',  # Add blob_url as 10th argument (empty string if not provided)
            ]
            logger.info(f"Creating pod for run_id={run_id} mode={mode} in ns={namespace}")
            logger.info(f"Container image={image} args={cli_args}")

            # Keep only selector-friendly labels; move queue_obj to annotations
            pod_labels = {"mode": mode, "run_id": run_id}
            annotations = {**labels}
            

            volume, mount = get_logs_volume_mount()
            volumes = [volume] if volume else []
            volume_mounts = [mount] if mount else []
            if volume:
                logger.info("Mounting logs PVC to /app/logs")
            else:
                logger.info("No AZURE_BLOB_LOGS_PVC configured; logs will go to stdout/stderr")

            # Expose port 8080 for websocket server if in compose mode
            container_ports = []
            if mode == "compose":
                # Add port 8080 for websocket server
                container_ports.append(k8s_client.V1ContainerPort(
                    container_port=8080,
                    name="websocket",
                    protocol="TCP"
                ))
                logger.info(f"[{run_id}] Exposing port 8080 for websocket server in compose mode")

            # Extract agent_type from labels and add as environment variable
            env_vars = []
            if labels.get("agent_type"):
                env_vars.append(k8s_client.V1EnvVar(name="AGENT_TYPE", value=labels.get("agent_type")))

            container = k8s_client.V1Container(
                name="litmus-test-runner",
                image=image,
                command=["node", "dist/index.js"],
                args=cli_args,
                env=env_vars,
                volume_mounts=volume_mounts,
                ports=container_ports if container_ports else None,
                resources=k8s_client.V1ResourceRequirements(
                    requests={"cpu": KUBERNETES_CPU_REQUEST, "memory": KUBERNETES_MEMORY_REQUEST},
                    limits={"cpu": KUBERNETES_CPU_LIMIT, "memory": KUBERNETES_MEMORY_LIMIT},
                ),
            )

            pod_spec = k8s_client.V1PodSpec(
                containers=[container],
                restart_policy="Never",
                volumes=volumes,
            )

            pod_meta = k8s_client.V1ObjectMeta(name=f"litmus-{run_id}", labels=pod_labels, annotations=annotations)
            pod = k8s_client.V1Pod(api_version="v1", kind="Pod", metadata=pod_meta, spec=pod_spec)

            created = self.core.create_namespaced_pod(namespace=namespace, body=pod)
            logger.info(f"Created pod {created.metadata.name} in namespace {namespace}")
            return created
        except Exception as e:
            logger.error(f"Failed to create AKS pod: {e}")
            logger.info(traceback.format_exc())
            raise

    def list_pods_with_labels(self, labels: dict, include_not_running: bool = True):
        """List pods by labels; optionally filter to Running phase only."""
        try:
            namespace = get_namespace()
            label_selector = ",".join([f"{k}={v}" for k, v in (labels or {}).items()])
            # logger.info(f"Listing pods in ns={namespace} with selector='{label_selector}'")
            pods = self.core.list_namespaced_pod(namespace=namespace, label_selector=label_selector).items
            if include_not_running:
                # logger.info(f"Found {len(pods)} matching pods (all phases)")
                return pods
            running = []
            for p in pods:
                phase = (p.status.phase or "").lower()
                if phase == "running":
                    running.append(p)
            logger.info(f"Found {len(running)}/{len(pods)} running pods")
            return running
        except Exception as e:
            logger.error(f"Failed to list pods with labels {labels}: {e}")
            logger.info(traceback.format_exc())
            raise

    def list_exited_pods_with_label(self, labels: dict):
        """Return pods in Succeeded or Failed phase for given labels (exited)."""
        try:
            pods = self.list_pods_with_labels(labels, include_not_running=True)
            exited = []
            for p in pods:
                phase = (p.status.phase or "").lower()
                # Treat Succeeded and Failed as exited (analogous to docker exited/dead)
                if phase in ["succeeded", "failed"]:
                    exited.append(p)
            # logger.info(f"Found {len(exited)}/{len(pods)} exited pods for labels {labels}")
            return exited
        except Exception as e:
            logger.error(f"Failed to list exited pods with labels {labels}: {e}")
            logger.info(traceback.format_exc())
            raise

    def kill_pods_with_label(self, labels: dict):
        """Delete pods matching labels with zero grace period (hard kill)."""
        try:
            namespace = get_namespace()
            pods = self.list_pods_with_labels(labels, include_not_running=True)
            logger.info(f"Found {len(pods)} pods with labels {labels}")
            for p in pods:
                name = p.metadata.name
                try:
                    # Delete the pod; no grace period to emulate kill/remove
                    self.core.delete_namespaced_pod(name=name, namespace=namespace, grace_period_seconds=0)
                    logger.info(f"Deleted pod {name}")
                except Exception as inner:
                    logger.error(f"Failed to delete pod {name}: {inner}")
                    logger.info(traceback.format_exc())
        except Exception as e:
            logger.error(f"Failed to kill pods with labels {labels}: {e}")
            logger.info(traceback.format_exc())
            raise

    def get_pod_finish_time(self, pod: V1Pod) -> datetime | None:
        """Extract container terminated.finishedAt timestamp if available."""
        try:
            # Prefer containerStatuses finishedAt
            statuses = (pod.status.container_statuses or [])
            for st in statuses:
                state = st.state
                if state and state.terminated and state.terminated.finished_at:
                    logger.info(f"Using container finishedAt for pod {pod.metadata.name}")
                    return state.terminated.finished_at.replace(tzinfo=timezone.utc)
            # Fallback to start/phase; none available => None
            logger.info(f"No terminated finishedAt found for pod {pod.metadata.name}")
            return None
        except Exception:
            return None

    def check_exited_pods_and_cleanup(self):
        """
        Checks for and cleans up exited Kubernetes pods with the specified label.
        
        Args:
            label_selector (str): The label to filter pods by. Defaults to "mode=script".
        
        This method:
        1. Lists all pods (including stopped ones) with the specified label mode=script
        2. Identifies pods in 'succeeded' or 'failed' state
        3. Updates database with test run results
        4. Removes these pods to free up system resources
        5. Increases the rate limit
        6. Clears the logs from redis
        7. Add log entry in activity log table
        8. Checks and cleanup compose pods. Removes long running compose pods.
        9. Checks and cleanup exited triage pods.
        """
        try:
            pods = self.list_exited_pods_with_label({"mode": "script"})
            for pod in pods:
                try:
                    labels = pod.metadata.labels or {}
                    run_id = labels.get("run_id")
                    queue_obj_str = (pod.metadata.annotations or {}).get("queue_obj")
                    
                    # Skip if queue_obj is None or empty
                    if not queue_obj_str:
                        logger.warning(f"No queue_obj found for pod {pod.metadata.name}")
                        continue
                        
                    try:
                        queue_obj = json.loads(queue_obj_str)
                    except json.JSONDecodeError as json_err:
                        logger.error(f"Failed to parse queue_obj for pod {pod.metadata.name}: {json_err}")
                        continue

                    # Get request data from queue_obj
                    test_id = queue_obj.get('test_id', None)
                    run_mode = queue_obj.get('run_mode', None)
                    suite_run_id = queue_obj.get('suite_run_id', None)
                    test_obj = queue_obj.get('test_obj', None)
                    container_retries = int(queue_obj.get("container_retries", 0))
                    test_run_retries = int(queue_obj.get("test_run_retries", 0))
                    current_user = queue_obj.get('current_user', None)
                    activity_log_id = queue_obj.get('activity_log_id', None)
                    row_number = queue_obj.get('row_number', None)
                    suite_obj = queue_obj.get('suite_obj', None)
                    
                    # Get the data from redis
                    test_result = get_test_result_from_redis(run_id)

                    # Get the time when the pod is exited
                    pod_exit_time = self.get_pod_finish_time(pod)

                    # Get ai_credits from redis session if available
                    session = get_compose_session_from_redis(run_id)
                    ai_credits = session.get("ai_credits") if session else None

                    # Update activity log, this will also update the credits table
                    update_activity_log(current_user, log_id=activity_log_id, end_time=pod_exit_time, ai_credits_consumed=ai_credits)
                    logger.info(f"Successfully updated activity log for test run {run_id} with end time {pod_exit_time} and ai_credits {ai_credits}")

                    # Remove pod to free space
                    self.kill_pods_with_label({"run_id": run_id, "mode": labels.get("mode")})
                    logger.info(f"✅ Cleaned up pod for run {run_id}")

                    # Increase rate limit since pod has exited
                    run_org_id = get_org_id_for_entity(test_id=test_id, suite_obj=suite_obj)
                    test_runner.increase_rate_limit(org_id=run_org_id)

                    # Remove the org id from the current runs
                    remove_from_current_runs(run_id)

                    # The pod is exited before the test result is updated in redis.
                    if test_result is None:
                        if container_retries < DOCKER_MAX_RETRIES:
                            # Add the test_obj back to queue to retry
                            container_retries = container_retries + 1
                            queue_obj["container_retries"] = container_retries

                            logger.info(f"Test result from pod {pod.metadata.name} not found in redis. Added test_obj back to queue to retry for run_id {run_id}")

                            add_log_to_redis(run_id, {"error": "Retrying the test", 'timestamp': datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",})

                            # Add logs to redis with attempt number as key
                            add_test_run_retries_to_redis(run_id, container_retries + test_run_retries)

                            enqueue_run_request(queue_obj)
                            continue
                        else:
                            logger.info(f"No test result found in redis for run_id {run_id}")
                            add_log_to_redis(run_id, {"error": "No test result received from pod", 'timestamp': datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",})
                            test_result = {}

                    gif_url = test_result.get('gif_url', None)
                    trace_url = test_result.get('trace_url', None)
                    status = test_result.get('status', FAILED_STATUS)

                    if test_run_retries < TEST_MAX_RUN_RETRIES and status == FAILED_STATUS:
                        test_run_retries = test_run_retries + 1
                        queue_obj["test_run_retries"] = test_run_retries

                        logger.info(f"Test run failed for run_id {run_id}. Retrying the test for {test_run_retries} times")

                        add_log_to_redis(run_id, {"error": "Retrying the test as the test failed for the first time", 'timestamp': datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",})

                        # Add logs to redis with attempt number as key
                        add_test_run_retries_to_redis(run_id, container_retries + test_run_retries)

                        # Enqueue the test again
                        enqueue_run_request(queue_obj)
                        continue

                    # Create output based on the status
                    output = "Test run completed successfully" if status == SUCCESS_STATUS else "Test run failed"

                    # Check if the test_result is still None. It means the pod is exited before the test result is updated in redis after max retries.
                    if test_result is None:
                        status = ERROR_STATUS
                        if row_number:
                            output = f"Server Error in row {row_number}. Please contact {SUPPORT_EMAIL}"
                        else:
                            output = f"Server Error. Please contact {SUPPORT_EMAIL}"

                    result = {
                        "output": output,
                        "gif_url": gif_url,
                        "trace_url": trace_url,
                        "retries": test_run_retries,
                    }

                    # Check if the status is failed, if yes then add the logs to redis with attemp number as key
                    if status == FAILED_STATUS or status == ERROR_STATUS:
                        logger.info(f"Entering the expected state {test_run_retries + container_retries}")
                        add_test_run_retries_to_redis(run_id, test_run_retries + container_retries + 1)

                    # Update the test result table
                    update_test_result_status(None, run_id, status, mode=run_mode, result=result, retries=test_run_retries, suite_run_id=suite_run_id)

                    # Update the test table
                    if status == FAILED_STATUS:
                        last_run_status = FAILED_STATUS

                        
                        # If the run mode is not triage and the suite run id is present, then add the test to the triage queue
                        if run_mode != TRIAGE_MODE and suite_run_id:
                            # Update the suite run triage status to running and increment the triage count
                            update_suite_run_status(suite_run_id, status=None, triage_count=1)

                             # Get failure data from Redis session if available
                            failure_data = test_result.get("failure_data", None)
                            if failure_data:
                                queue_obj["failure_data"] = failure_data
                                logger.info(f"Added failure data to triage queue for run_id {run_id}: instruction_id={failure_data.get('instruction', {}).get('id', 'unknown')}, has_image={bool(failure_data.get('image'))}")

                            # Add the test to the triage queue
                            add_test_to_queue_with_triage_mode(queue_obj)
                    
                    elif status == ERROR_STATUS :
                        last_run_status = ERROR_STATUS
                    else:
                        last_run_status = SUCCESS_STATUS if test_run_retries==0 else SUCCESS_FLAKY_STATUS
                    
                    update_test_status(test_id, last_run_status, run_mode)

                    # Extract environment name and config from queue_obj
                    environment_name = queue_obj.get('environment_name')
                    config = queue_obj.get('config', {})
                    config_string = format_config_string(config)

                    # Send message to slack
                    send_message_to_slack(
                        message = "🔄 Test Execution Complete",
                        obj = test_obj,
                        type = "test",
                        send_to_integration=False,
                        Test_Run_ID = run_id,
                        Status = status,
                        Mode = run_mode,
                        Retries = test_run_retries,
                        Environment = environment_name,
                        Config = config_string,
                        result_urls = {
                            "trace_url": trace_url
                        }
                    )

                    # Update the suite run table
                    if suite_run_id:
                        from utils.utils_test import handle_suite_run_completion
                        handle_suite_run_completion(suite_run_id, queue_obj, status, output, test_id, test_obj, environment_name, config_string, config)


                    logger.info(f"Successfully updated database for test run {run_id}")

                    # Clear logs from redis
                    clear_entry_from_redis(run_id)

                except Exception as e:
                    logger.error(f"❌ Failed to handle pod {pod.metadata.name}: {e}")
                    logger.info(traceback.format_exc())

            # Check and cleanup compose pods
            self.check_and_cleanup_compose_pods()

            # Check and cleanup triage pods
            self.check_exited_triage_pods_and_cleanup()

        except Exception as e:
            logger.error(f"Failed to check and cleanup pods: {e}")
            logger.info(traceback.format_exc())
            raise e

    def check_if_aks_pod_is_running(self, labels: dict):
        """Check if a pod is running with the given labels."""
        try:
            pods = self.list_pods_with_labels(labels, include_not_running=True)
            return len(pods) > 0
        except Exception:
            return False

    def aks_pod_is_crashed(self, labels: dict):
        """Check if a pod is crashed with the given labels."""
        try:
            pods = self.list_pods_with_labels(labels, include_not_running=True)
            for pod in pods:
                phase = (pod.status.phase or "").lower()
                if phase == "failed":
                    return True, self.get_pod_finish_time(pod)
            return False, None
        except Exception:
            return False, None

    def check_and_cleanup_compose_pods(self):
        from utils.utils_compose import update_compose_session_db
        """
        Checks for and cleans up compose pods that have been running longer than the timeout period.
        This method:
        1. Lists all pods with the 'mode=compose' label
        2. Identifies pods that have been running longer than BROWSERBASE_SESSION_TIMEOUT minutes
        3. Uses kill_pods_with_label to stop and remove these pods
        4. Logs the cleanup process
        """
        try:
            compose_pods = self.list_pods_with_labels({"mode": "compose"}, include_not_running=True)
            
            for pod in compose_pods:
                try:
                    labels = pod.metadata.labels or {}
                    annotations = pod.metadata.annotations or {}
                    
                    try:
                        current_user = json.loads(annotations.get("current_user", "{}")) if annotations.get("current_user") else None
                    except Exception as e:
                        logger.error(f"Error parsing current_user: {e}")
                        logger.debug(traceback.format_exc())
                        current_user = None
                
                    activity_log_id = annotations.get("activity_log_id")
                    run_id = labels.get("run_id")

                    end_time = None
                    
                    phase = (pod.status.phase or "").lower()
                    if phase == "running":
                        # Check if pod has been running longer than timeout
                        start_time = pod.status.start_time or datetime.now(timezone.utc)
                        current_time = datetime.now(timezone.utc)
                        
                        if (current_time - start_time).total_seconds() > (BROWSERBASE_SESSION_TIMEOUT + 30):
                            
                            logger.info(f"Found long-running compose pod {pod.metadata.name} with run_id {run_id}, attempting cleanup")
                            
                            try:
                                end_time = datetime.now(timezone.utc)
                                
                                # Kill the pod
                                self.kill_pods_with_label({"mode": "compose", "run_id": run_id})

                                from app import app
                                with app.app_context():
                                    # Update the compose session status to completed
                                    update_compose_session_db(run_id, status="completed")
                                    logger.info(f"Updated compose session status to completed for compose_id {run_id}")
                            except Exception as cleanup_err:
                                logger.warning(f"Failed to cleanup compose pod {pod.metadata.name}: {cleanup_err}")
                                # Don't raise the exception to continue processing other pods
                                continue
                    
                    elif phase in ["succeeded", "failed"]:
                        # Check if the pod has been running longer than the timeout
                        logger.info(f"Compose pod {pod.metadata.name} has been running longer than the timeout, attempting cleanup")

                        # check if additional annotations source and agent_type are present
                        source = annotations.get("source")
                        agent_type = annotations.get("agent_type")
                        if source and agent_type and source == COMPOSE_AGENT and (agent_type == COMPOSE_AGENT_SIGN_IN or agent_type == COMPOSE_AGENT_SIGN_UP):
                            logger.info(f"Compose pod {pod.metadata.name} is a sign in/sign up pod, attempting cleanup")
                            # call method from service_goal - it will check for failures internally
                            try:
                                from utils.utils_signin_agent import create_suite_and_test_from_sign_in_agent
                                create_suite_and_test_from_sign_in_agent(run_id, current_user)
                            except Exception as e:
                                logger.error(f"Error in create_suite_and_test_from_sign_in_agent: {str(e)}")
                                logger.debug(traceback.format_exc())
                                self.kill_pods_with_label({"mode": "compose", "run_id": run_id})
                                logger.info(f"✅ Removed pod {pod.metadata.name}")
                                continue
                        
                        # Clear logs from redis
                        self.kill_pods_with_label({"mode": "compose", "run_id": run_id})
                        logger.info(f"✅ Removed pod {pod.metadata.name}")
                        # clear_entry_from_redis(run_id)

                        # get the end time from the pod
                        end_time = self.get_pod_finish_time(pod) or datetime.now(timezone.utc)

                        from app import app
                        with app.app_context():
                            # Update the compose session status to completed
                            update_compose_session_db(run_id, status="completed")
                            logger.info(f"Updated compose session status to completed for compose_id {run_id}")

                    # check for ai_credits and update the activity_log and credits table
                    compose_session = get_compose_session_from_redis(run_id)
                    ai_credits = compose_session.get("ai_credits") if compose_session else None

                    if end_time:
                        # Update executed_seconds and ai_credits in the activity log and credits table.
                        update_activity_log(current_user, log_id=activity_log_id, end_time=end_time, ai_credits_consumed=ai_credits)
                    else:
                        # Update ai_credits in the activity log and credits table.
                        update_activity_log_with_ai_credits(current_user, log_id=activity_log_id, ai_credits_consumed=ai_credits)

                
                except Exception as e:
                    logger.error(f"Error processing compose pod {pod.metadata.name}: {e}")
                    continue
                
        except Exception as e:
            logger.error(f"Failed to check and cleanup compose pods: {e}")
            logger.debug(traceback.format_exc())
            # Don't raise the exception to prevent the entire cleanup process from failing

    def check_exited_triage_pods_and_cleanup(self):
        """
        Checks for and cleans up exited Kubernetes pods with label mode=triage.

        This method performs ONLY the following actions:
        1. Lists all pods (including stopped ones) with label mode=triage
        2. Identifies pods in 'succeeded' or 'failed' state
        3. Increases the rate limit
        4. Updates the suite run triage result/status (see handle_triage_pod_exit)
        5. Updates the test result status using data fetched from Redis only
        6. Removes the pod
        """
        try:
            pods = self.list_exited_pods_with_label({"mode": "triage"})

            for pod in pods:
                try:
                    labels = pod.metadata.labels or {}
                    run_id = labels.get("run_id")
                    queue_obj_str = (pod.metadata.annotations or {}).get("queue_obj")

                    # Get the time when the pod is exited
                    pod_exit_time = self.get_pod_finish_time(pod)

                    # Remove the pod
                    self.kill_pods_with_label({"run_id": run_id, "mode": "triage"})
                    logger.info(f"✅ Removed triage pod {run_id}")

                    if not queue_obj_str:
                        logger.warning(f"No queue_obj found for triage pod {run_id}")
                        # Increase rate limit even if metadata is missing
                        continue

                    try:
                        queue_obj = json.loads(queue_obj_str)
                    except json.JSONDecodeError as json_err:
                        logger.error(f"Failed to parse queue_obj for triage pod {run_id}: {json_err}")
                        continue

                    # Extract minimal fields
                    run_mode = queue_obj.get('run_mode', None)
                    suite_run_id = queue_obj.get('suite_run_id', None)
                    current_user = queue_obj.get('current_user', None)
                    activity_log_id = queue_obj.get('activity_log_id', None)
                    suite_run_id = queue_obj.get('suite_run_id', None)
                    test_id = queue_obj.get('test_id', None)
                    test_obj = queue_obj.get('test_obj', None)
                    test_name = test_obj.get('name', None)
                    row_number = queue_obj.get('row_number', None)
                    suite_obj = queue_obj.get('suite_obj', None)
                    config = queue_obj.get('config',{})

                    # Increase rate limit
                    run_org_id = get_org_id_for_entity(test_id=test_id, suite_obj=suite_obj)
                    test_runner.increase_rate_limit(org_id=run_org_id)

                    # Remove the org id from the current runs
                    remove_from_current_runs(run_id)

                    # Read triage result from Redis only
                    test_result = get_test_result_from_redis(run_id) or {}
                    if not test_result:
                        logger.warning(f"No test result found for triage pod {run_id}")
                        continue

                    # Update the suite run db
                    result_object = {
                        "test_name": test_name,
                        "row_number": row_number,
                        "test_id": test_id,
                        "category": test_result.get('category', None),
                        "reasoning": test_result.get('reasoning', None),
                        "error_instruction": test_result.get('error_instruction', None),
                        "prompt": test_result.get('prompt', None)
                    }

                    # If test result has sub category, then add it to the result object
                    if test_result.get('sub_category', None):
                        result_object['sub_category'] = test_result.get('sub_category', None)

                    # Update suite run with triage result
                    suite_run_obj = update_suite_run_status(suite_run_id, status=None, triage_result=result_object)
                    
                    # Check if all triage tests are completed and send consolidated message
                    if suite_run_obj and suite_run_obj.get('triage_status', None) == SUITE_COMPLETED_STATUS and suite_run_obj.get('status', None) == SUITE_COMPLETED_STATUS:
                        logger.info(f"All triage tests are completed and sending consolidated message for suite run {suite_run_id} and current triage count is {suite_run_obj.get('triage_count', None)}")

                        from utils.utils_slack import send_triage_findings_message
                        send_triage_findings_message(suite_run_id, suite_run_obj.get('triage_result'), queue_obj.get('suite_obj', None), send_to_integration=True)
                        logger.info(f"Sent consolidated triage findings message for suite run {suite_run_id}")

                    logger.info(f"Successfully updated suite run status for suite run {suite_run_id} with triage result {result_object}")

                    # Check if healing should be triggered
                    category = test_result.get('category', None)
                    heal_test_enabled = suite_obj.get('heal_test', False)
                    
                    # If sub_category is replace_step or re_generate_script and heal_test is enabled, enqueue for healing
                    if category in [TRIAGE_CATEGORIES['RAISE_BUG'], TRIAGE_CATEGORIES['UPDATE_SCRIPT']] and heal_test_enabled:
                        logger.info(f"Healing enabled for test {test_id}. Category: {category}. Enqueueing for healing.")
                        
                        try:
                            add_test_to_queue_with_heal_mode(queue_obj, result_object)
                        except Exception as e:
                            logger.error(f"Failed to enqueue test for healing: {str(e)}")
                            logger.debug(traceback.format_exc())

                    # Get gif_url and trace_url from redis
                    gif_url = test_result.get('gif_url', None)
                    trace_url = test_result.get('trace_url', None)

                    # Update test result status using Redis-only data
                    update_test_result_status(
                        None,
                        run_id,
                        test_result.get('status', FAILED_STATUS),
                        result={"output": "Traige agent completed the analysis", "gif_url": gif_url, "trace_url": trace_url},
                    )

                    # Get the ai_credits from redis
                    session = get_compose_session_from_redis(run_id)
                    ai_credits = session.get("ai_credits") if session else None

                    # Update executed_seconds and ai_credits in the activity log and credits table.
                    update_activity_log(current_user, log_id=activity_log_id, end_time=pod_exit_time, ai_credits_consumed=ai_credits)

                    # Extract environment name and config from queue_obj
                    environment_name = queue_obj.get('environment_name')
                    config_string = format_config_string(config)

                    # Create kwargs for send_message_to_slack
                    kwargs = {
                        "Category": test_result.get('category', None),
                        "Reasoning": test_result.get('reasoning', None),
                        "Error_Instruction": format_instruction_for_display(test_result.get('error_instruction', None)),
                        "Environment": environment_name,
                        "Config": config_string
                    }

                    if test_result.get('sub_category') is not None:
                        kwargs['Sub_Category'] = test_result.get('sub_category', None)

                    send_message_to_slack(
                            message = "Triage Agent Analysis Complete",
                            obj = test_obj,
                            type = "test",
                            send_to_integration=False,
                            Test_Run_ID = run_id,
                            Status = test_result.get('status', FAILED_STATUS),
                            Mode = run_mode,
                            result_urls = {
                                "trace_url": trace_url
                            },
                            **kwargs
                        )

                    # clear redis session
                    clear_entry_from_redis(run_id)
                    logger.info(f"✅ Cleared redis session for triage pod {run_id}")

                except Exception as e:
                    logger.error(f"❌ Failed to handle triage pod {run_id}: {e}")
                    logger.debug(traceback.format_exc())
                    continue

        except Exception as e:
            logger.error(f"Failed to check and cleanup triage pods: {e}")
            logger.debug(traceback.format_exc())
            raise e

    def check_exited_heal_pods_and_cleanup(self):
        """
        Checks for and cleans up exited Kubernetes pods with label mode=heal.

        This method performs ONLY the following actions:
        1. Lists all pods (including stopped ones) with label mode=heal
        2. Identifies pods in 'succeeded' or 'failed' state
        3. Increases the rate limit
        4. Gets heal_results from Redis and stores in HealingSuggestion database
        5. Updates the test result status using data fetched from Redis only
        6. Removes the pod
        """
        try:
            pods = self.list_exited_pods_with_label({"mode": "heal"})

            for pod in pods:
                try:
                    labels = pod.metadata.labels or {}
                    run_id = labels.get("run_id")
                    queue_obj_str = (pod.metadata.annotations or {}).get("queue_obj")

                    # Get the time when the pod is exited
                    pod_exit_time = self.get_pod_finish_time(pod)

                    # Remove the pod
                    self.kill_pods_with_label({"run_id": run_id, "mode": "heal"})
                    logger.info(f"✅ Removed heal pod {run_id}")

                    if not queue_obj_str:
                        logger.warning(f"No queue_obj found for heal pod {run_id}")
                        # Increase rate limit even if metadata is missing
                        continue

                    try:
                        queue_obj = json.loads(queue_obj_str)
                    except json.JSONDecodeError as json_err:
                        logger.error(f"Failed to parse queue_obj for heal pod {run_id}: {json_err}")
                        continue

                    # Extract minimal fields
                    suite_run_id = queue_obj.get('suite_run_id', None)
                    current_user = queue_obj.get('current_user', None)
                    activity_log_id = queue_obj.get('activity_log_id', None)
                    test_id = queue_obj.get('test_id', None)
                    test_obj = queue_obj.get('test_obj', None)
                    suite_obj = queue_obj.get('suite_obj', None)
                    config = queue_obj.get('config', {})

                    # Get suite_id from suite_obj or test_obj
                    suite_id = None
                    if suite_obj:
                        suite_id = suite_obj.get('suite_id')
                    elif test_obj:
                        suite_id = test_obj.get('suite_id')

                    # Increase rate limit
                    run_org_id = get_org_id_for_entity(test_id=test_id, suite_obj=suite_obj)
                    test_runner.increase_rate_limit(org_id=run_org_id)

                    # Remove the org id from the current runs
                    remove_from_current_runs(run_id)

                    # Get session from Redis to access heal_results and triage_result
                    session = get_compose_session_from_redis(run_id)
                    if not session:
                        logger.warning(f"No session found in Redis for heal pod {run_id}")
                        continue

                    # Get heal_results from session
                    heal_results = session.get('heal_results', {})
                    if not heal_results:
                        logger.warning(f"No heal_results found in Redis for heal pod {run_id}")
                        continue

                    # Get triage_result from session
                    triage_result = session.get('triage_result', {})

                    # Get original failed testrun_id
                    # Note: This should be stored in queue_obj when creating heal queue
                    # For now, try to get it from queue_obj or use the run_id as fallback
                    failed_test_run_id = queue_obj.get('original_testrun_id') or queue_obj.get('failed_testrun_id') or run_id
                    
                    # Get heal_status and reasoning
                    heal_status = heal_results.get('heal_status', 'unknown')
                    reasoning = heal_results.get('reasoning', '')

                    # Get suggested_test data
                    suggested_test = heal_results.get('suggested_test', {})
                    if not suggested_test:
                        logger.warning(f"No suggested_test found in heal_results for heal pod {run_id}")
                        continue

                    # Create current_test dict with only instructions from test_obj
                    current_test = {}
                    if test_obj and test_obj.get('instructions'):
                        current_test = {
                            'instructions': json.loads(test_obj.get('instructions', [])),
                            'playwright_actions': json.loads(test_obj.get('playwright_instructions', {}))
                        }

                    # Store in HealingSuggestion database
                    try:
                        from models.HealingSuggestion import HealingSuggestion
                        from app import app
                        from database import db
                        
                        with app.app_context():
                            healing_suggestion = HealingSuggestion(
                                id=str(uuid.uuid4()),
                                suite_id=suite_id,
                                suite_run_id=suite_run_id,
                                test_id=test_id,
                                failed_test_run_id=failed_test_run_id,
                                triage_result=json.dumps(triage_result) if triage_result else None,
                                suggested_test=json.dumps(suggested_test),  # Store suggested_test directly
                                reasoning=reasoning,
                                status=heal_status,
                                current_test=json.dumps(current_test) if current_test else None
                            )
                            
                            db.session.add(healing_suggestion)
                            db.session.commit()
                            logger.info(f"✅ Stored healing suggestion in database for heal pod {run_id}")
                    except Exception as e:
                        logger.error(f"Failed to store healing suggestion in database for heal pod {run_id}: {e}")
                        logger.debug(traceback.format_exc())
                        try:
                            from app import app
                            from database import db
                            with app.app_context():
                                db.session.rollback()
                        except Exception as rollback_err:
                            logger.error(f"Failed to rollback database session: {rollback_err}")

                    # Get test result from Redis
                    test_result = get_test_result_from_redis(run_id) or {}
                    
                    # Get gif_url and trace_url from redis
                    gif_url = test_result.get('gif_url', None)
                    trace_url = test_result.get('trace_url', None)

                    # Update test result status using Redis-only data
                    update_test_result_status(
                        None,
                        run_id,
                        heal_status,
                        result={"output": "Heal agent completed", "gif_url": gif_url, "trace_url": trace_url},
                    )

                    # Get the ai_credits from redis
                    ai_credits = session.get("ai_credits") if session else None

                    # Update executed_seconds and ai_credits in the activity log and credits table.
                    update_activity_log(current_user, log_id=activity_log_id, end_time=pod_exit_time, ai_credits_consumed=ai_credits)

                    # clear redis session
                    clear_entry_from_redis(run_id)
                    logger.info(f"✅ Cleared redis session for heal pod {run_id}")

                except Exception as e:
                    logger.error(f"❌ Failed to handle heal pod {run_id}: {e}")
                    logger.debug(traceback.format_exc())
                    continue

        except Exception as e:
            logger.error(f"Failed to check and cleanup heal pods: {e}")
            logger.debug(traceback.format_exc())
            raise e
