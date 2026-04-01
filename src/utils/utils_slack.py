import os
import requests
import traceback
from models.Test import Test
from models.Suite import Suite
from dotenv import load_dotenv, find_dotenv
from utils.instruction_formatter import format_instruction_for_display
from log_config.logger import logger
load_dotenv(find_dotenv("app.env"))



def send_message_to_slack(message: str, obj: dict, type: str, send_to_integration = False, **kwargs):
    """
    Send a message to Slack using the webhook URL.
    Arguments:
    - message: The message to send.
    - obj: The object containing information about the test or suite.
    - type: The type of object ('test' or 'suite').
    - send_to_integration: Whether to send the message to the integration or not.
    - kwargs: Additional keyword arguments to include in the message.
    """
    logger.info("Sending message to slack")
    try:
        slack_webhook_url = os.getenv("SLACK_WEBHOOK_URL")
        
        formatted_message = create_slack_log_message(message, obj, type, **kwargs)
        
        message = {
            "blocks":[
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": formatted_message
                    }
                }
            ]
        }

        # logger.info(f"Message: {obj}")
        # logger.info(f"Type: {type}")

        # Org-specific webhook integrations are removed in OSS mode.

        # Slack webhook URL is Finigami org integration URL.
        if not slack_webhook_url:
            logger.error("SLACK_WEBHOOK_URL not set in environment variables")
            return
        
        # Add org_id to slack messages. This org_id is sent only to Finigami org integration URL.
        org_id = get_org_id_from_suite_id(obj['suite_id'])
        message['blocks'].append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"Org ID: {org_id}"
                }
            ]
        })

            
        response = requests.post(slack_webhook_url, json=message)
        logger.info(f"Response: {response}")
        if response.status_code != 200:
            logger.error(f"Failed to send message. Status code: {response.status_code}")

    except Exception as e:
        logger.error(f"Error sending message to webhook: {str(e)}")
        logger.debug(traceback.format_exc())

def create_slack_log_message(message, obj, type, **kwargs):
    logger.info("Creating slack log message")
    try:
        new_message = ""
        url_message=None

        # Extract information from the test object
        if type == 'test':
            test_id = obj['id']
            test_name = obj['name']

            new_message = f"*{message}*:\n"
            new_message += f"Test ID: {test_id}\n"
            new_message += f"Test Name: {test_name}\n"

            if 'Test_Run_ID' in kwargs:
                url = f"{os.getenv('BASE_URL')}/dashboard/test/{test_id}/run/{kwargs['Test_Run_ID']}"
                url_message = f"<{url}|Link to Test Run>\n"
            else:  # Send test URL if Test_Run_ID is not present in kwargs
                if not 'no_url' in kwargs:
                    url = f"{os.getenv('BASE_URL')}/dashboard/suite/{obj['suite_id']}/test/{test_id}"
                    url_message = f"<{url}|Link to Test>\n"


        elif type == 'suite':
            suite_id = obj['suite_id']
            suite_name = obj['name']

            new_message = f"*{message}*:\n"
            # Add suite name clickable. If no_url is present in kwargs, don't add url.
            if 'no_url' in kwargs:
                new_message += f"Name: {suite_name}\n"
            else:
                url = f"{os.getenv('BASE_URL')}/dashboard/suite/{suite_id}"
                new_message += f"Name: <{url}|{suite_name}>\n"

            # Send suite run URL if Suite_Run_ID is present in kwargs
            if 'Suite_Run_ID' in kwargs:
                url = f"{os.getenv('BASE_URL')}/dashboard/suite/{suite_id}/run/{kwargs['Suite_Run_ID']}"
                url_message = f"<{url}|Link to Run>\n"
                del kwargs['Suite_Run_ID']  # Delete Suite_Run_ID from kwargs to avoid it being added to message again

        # Add kwargs to message
        for key, value in kwargs.items():
            if key in ['no_url', 'result_urls', 'suite_completion_data']:  # Skip these keys
                continue
            # Handle Environment and Config fields specially - only show if not None/empty
            if key == 'Environment':
                if value:
                    new_message += f"Environment: {value}\n"
                # Skip if None/empty
                continue
            elif key == 'Config':
                if value:
                    new_message += f"Config: {value}\n"
                # Skip if None/empty
                continue
            key = key.replace('_', ' ')
            new_message += f"{key}: {value}\n"

        # Check if suite_completion_data is in kwargs
        if 'suite_completion_data' in kwargs:

            # Add suite completion data to message
            data = kwargs['suite_completion_data']
            # new_message += f"Run complete\n"
            new_message += f"<{url}|See complete report>\n\n"
            new_message += f":white_check_mark: Passed: {data['success_count']}\t\t\t\t"
            new_message += f":x: Failed: {data['failure_count']}\t\t\t\t"
            new_message += f":warning: Errors: {data.get('error_count', 0)}\n\n"

            if data.get('failed_tests'):
                failed_list = "\n".join([f"• {test}\n" for test in data['failed_tests']])
                new_message += f"Failed:\n{failed_list}\n\n"

            if data.get('error_messages'):
                error_list = ""
                for test_id, errors_dict in data['error_messages'].items():
                    error_message = f"• {errors_dict['test_name']} - "
                    for error in errors_dict['errors']:
                        error_message += f"{error}, "
                    error_list += f"{error_message}\n"
                new_message += f"Errors:\n{error_list}\n\n"

        # Iterate through result urls if present in kwargs. Result URLs are gif and trace url from test run.
        if 'result_urls' in kwargs:
            for key, url in kwargs['result_urls'].items():
                if key == 'gif_url':
                    new_message += f"• <{url}|View GIF>\n"
                elif key == 'trace_url':
                    new_message += f"• <https://trace.playwright.dev/?trace={url}|View Trace>\n"

        # Add URL message at the end
        if url_message and 'suite_completion_data' not in kwargs:
            new_message += url_message


        logger.info(f"Formatted message: {new_message}")

        return new_message

    except Exception as e:
        logger.error(f"Error creating slack log message: {str(e)}")
        logger.debug(traceback.format_exc())
        raise e
    
def get_org_id_from_suite_id(suite_id: str):
    """
    Get the organization ID from the test ID and suite ID.
    """
    try:
        from app import app
        with app.app_context():
            suite = Suite.query.filter_by(suite_id=suite_id).first()
            if suite:
                return suite.org_id
            return None
    except Exception as e:
        logger.error(f"Unable to get org id for suite_id {suite_id}, " + str(e))
        logger.debug(traceback.format_exc())
        raise e

def should_suppress_suite_slack_messages(org_id: str) -> bool:
    """
    Check if organization has flag set to suppress suite run Slack messages.
    Returns True if messages should be suppressed, False otherwise.
    """
    try:
        from app import app
        with app.app_context():
            from models.OrgQueueConfig import OrgQueueConfig
            config = OrgQueueConfig.query.filter_by(org_id=org_id).first()
            if config:
                return config.suppress_suite_slack_messages
            return False  # Default: don't suppress if config doesn't exist
    except Exception as e:
        logger.error(f"Error checking suppress_suite_slack_messages flag for org {org_id}: {str(e)}")
        logger.debug(traceback.format_exc())
        return False  # Default: don't suppress on error
    
def send_triage_findings_message(suite_run_id: str, triage_results: list, suite_obj: dict, send_to_integration: bool = False) -> None:
    """
    Send a consolidated Slack message for all triage findings in a suite run.
    
    Args:
        suite_run_id: The suite run ID
        triage_results: List of triage result objects with test_name, category, reasoning, etc.
        suite_obj: Suite object containing suite information
        send_to_integration: Whether to send the message to the integration or not.
    """
    try:
        from utils.utils_constants import TRIAGE_CATEGORIES
        
        # Group results by category
        potential_bugs = []
        repair_tests = []
        manual_review = []
        successful_retry = []
        retry_without_changes = []
        errors = []
        
        for result in triage_results:
            category = result.get('category')
            test_name = result.get('test_name', 'Unknown Test')
            reasoning = result.get('reasoning', 'No reasoning provided')
            row_number = result.get('row_number')
            test_id = result.get('test_id')
            error_instruction = result.get('error_instruction')
            
            # Create test link if test_id is available
            test_link = None
            if test_id:
                test_url = f"{os.getenv('BASE_URL')}/dashboard/suite/{suite_obj['suite_id']}/test/{test_id}"
                test_link = f"<{test_url}|{test_name}>"
            
            # Format error instruction for display
            formatted_instruction = None
            if error_instruction:
                formatted_instruction = format_instruction_for_display(error_instruction)
            
            if category == TRIAGE_CATEGORIES['RAISE_BUG']:
                potential_bugs.append({
                    'test_name': test_name,
                    'reasoning': reasoning,
                    'row_number': row_number,
                    'test_id': test_id,
                    'test_link': test_link,
                    'error_instruction': formatted_instruction
                })
            elif category == TRIAGE_CATEGORIES['UPDATE_SCRIPT']:
                repair_tests.append({
                    'test_name': test_name,
                    'reasoning': reasoning,
                    'row_number': row_number,
                    'sub_category': result.get('sub_category', None),
                    'test_id': test_id,
                    'test_link': test_link,
                    'error_instruction': formatted_instruction
                })
            elif category == TRIAGE_CATEGORIES['CANNOT_CONCLUDE']:
                manual_review.append({
                    'test_name': test_name,
                    'reasoning': reasoning,
                    'row_number': row_number,
                    'test_id': test_id,
                    'test_link': test_link,
                    'error_instruction': formatted_instruction
                })
            elif category == TRIAGE_CATEGORIES['RETRY_WITHOUT_CHANGES']:
                retry_without_changes.append({
                    'test_name': test_name,
                    'reasoning': reasoning,
                    'row_number': row_number,
                    'test_id': test_id,
                    'test_link': test_link,
                    'error_instruction': formatted_instruction
                })
            elif category == TRIAGE_CATEGORIES['SUCCESSFUL_ON_RETRY']:
                successful_retry.append({
                    'test_name': test_name,
                    'reasoning': reasoning,
                    'row_number': row_number,
                    'test_id': test_id,
                    'test_link': test_link,
                    'error_instruction': formatted_instruction
                })
            else:
                # Handle any new/unknown categories (e.g., "Error")
                errors.append({
                    'test_name': test_name,
                    'reasoning': reasoning,
                    'row_number': row_number,
                    'test_id': test_id,
                    'test_link': test_link,
                    'error_instruction': formatted_instruction
                })
        
        # Check if there are any tests other than successful_retry
        # This determines if we send to integration webhook
        has_other_results = (len(potential_bugs) > 0 or 
                            len(repair_tests) > 0 or 
                            len(manual_review) > 0 or 
                            len(retry_without_changes) > 0 or 
                            len(errors) > 0)
        
        # Build the message (always build, including successful_retry for general webhook)
        message_parts = []
        success_on_retry_message_parts = []
        
        # Header with link to suite run results
        suite_url = f"{os.getenv('BASE_URL')}/dashboard/suite/{suite_obj['suite_id']}/run/{suite_run_id}"
        message_parts.append(f"*Triage Findings for Suite Run*\n<{suite_url}|View Suite Run Results>\n")
        
        # Potential Bugs section
        if potential_bugs:
            message_parts.append(f":ladybug: *Potential Bugs: {len(potential_bugs)}*")
            for bug in potential_bugs:
                # If test_link is present, use it, otherwise use test_name
                if bug['test_link']:
                    test_display = bug['test_link']
                else:
                    test_display = f"{bug['test_name']}"
                # Add row number if present
                if bug['row_number']:
                    test_display += f"-row #{bug['row_number']}"
                # Add reasoning
                message_parts.append(f"• *Test*: {test_display}\n *Reasoning*: {bug['reasoning']}")
                # Add error instruction if present
                if bug['error_instruction']:
                    message_parts.append(f" *Failed Instruction*: {bug['error_instruction']}\n")
                else:
                    message_parts.append("\n")
            message_parts.append("\n")  # Empty line
        
        # Repair Tests section
        if repair_tests:
            message_parts.append(f":hammer_and_wrench: *Repair Test: {len(repair_tests)}*")
            for repair in repair_tests:
                # If test_link is present, use it, otherwise use test_name
                if repair['test_link']:
                    test_display = repair['test_link']
                else:
                    test_display = f"{repair['test_name']}"
                # Add row number if present
                if repair['row_number']:
                    test_display += f"-row #{repair['row_number']}"
                # Add reasoning
                message_parts.append(f"• *Test*: {test_display}\n *Reasoning*: {repair['reasoning']}")
                # Add error instruction if present
                if repair['error_instruction']:
                    message_parts.append(f" *Failed Instruction*: {repair['error_instruction']}\n")
                else:
                    message_parts.append("\n")
            message_parts.append("\n")  # Empty line
        
        # Manual Review section
        if manual_review:
            message_parts.append(f":face_with_monocle: *Manual review needed: {len(manual_review)}*")
            for review in manual_review:
                # If test_link is present, use it, otherwise use test_name
                if review['test_link']:
                    test_display = review['test_link']
                else:
                    test_display = f"{review['test_name']}"
                # Add row number if present
                if review['row_number']:
                    test_display += f"-row #{review['row_number']}"
                # Add reasoning
                message_parts.append(f"• *Test*: {test_display}\n *Reasoning*: {review['reasoning']}")
                # Add error instruction if present
                if review['error_instruction']:
                    message_parts.append(f" *Failed Instruction*: {review['error_instruction']}\n")
                else:
                    message_parts.append("\n")
            message_parts.append("\n")  # Empty line
        
        # Successful Retry section (included for general webhook, but integration webhook only gets it if there are other results)
        if successful_retry:
            success_on_retry_message_parts.append(f":white_check_mark: *Successful on retry: {len(successful_retry)}*")
            for retry in successful_retry:
                # If test_link is present, use it, otherwise use test_name
                if retry['test_link']:
                    test_display = retry['test_link']
                else:
                    test_display = f"{retry['test_name']}"
                # Add row number if present
                if retry['row_number']:
                    test_display += f"-row #{retry['row_number']}"
                # Add reasoning
                success_on_retry_message_parts.append(f"• *Test*: {test_display}\n *Reasoning*: {retry['reasoning']}")
                # Add error instruction if present
                if retry['error_instruction']:
                    success_on_retry_message_parts.append(f" *Failed Instruction*: {retry['error_instruction']}\n")
                else:
                    success_on_retry_message_parts.append("\n")
            success_on_retry_message_parts.append("\n")  # Empty line

        # Errors or Unknown category section (e.g., credits exhausted)
        if errors:
            message_parts.append(f":rotating_light: *Errors: {len(errors)}*")
            for err in errors:
                if err['test_link']:
                    test_display = err['test_link']
                else:
                    test_display = f"{err['test_name']}"
                if err['row_number']:
                    test_display += f"-row #{err['row_number']}"
                message_parts.append(f"• *Test*: {test_display}\n *Reasoning*: {err['reasoning']}")
                if err['error_instruction']:
                    message_parts.append(f" *Failed Instruction*: {err['error_instruction']}\n")
                else:
                    message_parts.append("\n")
            message_parts.append("\n")  # Empty line
        
        # Retry Without Changes section
        if retry_without_changes:
            message_parts.append(f":white_check_mark: *Retry without changes: {len(retry_without_changes)}*")
            for retry in retry_without_changes:
                # If test_link is present, use it, otherwise use test_name
                if retry['test_link']:
                    test_display = retry['test_link']
                else:
                    test_display = f"{retry['test_name']}"
                # Add row number if present
                if retry['row_number']:
                    test_display += f"-row #{retry['row_number']}"
                # Add reasoning
                message_parts.append(f"• *Test*: {test_display}\n *Reasoning*: {retry['reasoning']}")
                # Add error instruction if present
                if retry['error_instruction']:
                    message_parts.append(f" *Failed Instruction*: {retry['error_instruction']}\n")
                else:
                    message_parts.append("\n")
            message_parts.append("\n")  # Empty line
        
        # Build complete message for Slack (includes successful_retry)
        complete_message_parts = message_parts.copy()
        if successful_retry:
            complete_message_parts.extend(success_on_retry_message_parts)
        
        # Build message for integration webhook (excludes successful_retry if there are errors)
        integration_message_parts = message_parts.copy()
        
        # Join all parts for complete message (Slack)
        formatted_message = "\n".join(complete_message_parts)
        
        # Join parts for integration message (without successful_retry)
        integration_formatted_message = "\n".join(integration_message_parts)

        def _truncate_triage_message(message_text: str, target_label: str) -> str:
            if len(message_text) < 3000:
                return message_text

            # Leave buffer for the "View complete result" message
            truncate_at = 2000
            truncate_point = message_text.rfind('\n', 0, truncate_at)
            if truncate_point == -1:
                truncate_point = message_text.rfind('.', 0, truncate_at)
            if truncate_point == -1:
                truncate_point = truncate_at

            truncated_message = message_text[:truncate_point]
            truncated_message += f"\n\n<message clipped>\nView complete result here - <{suite_url}|Link to Suite Run>"
            logger.info(
                f"Triage findings {target_label} message truncated due to length. Original length: {len(message_text)} characters"
            )
            return truncated_message

        # Truncate both Slack and integration messages if needed
        formatted_message = _truncate_triage_message(formatted_message, "slack")
        integration_formatted_message = _truncate_triage_message(integration_formatted_message, "integration")
        
        # Create message blocks for Slack (complete message)
        message_blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": formatted_message
                }
            }
        ]
        
        message = {"blocks": message_blocks}
        
        # Create message blocks for integration webhook (without successful_retry if there are errors)
        integration_message_blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": integration_formatted_message
                }
            }
        ]
        
        integration_message = {"blocks": integration_message_blocks}
        
        # Org-specific webhook integrations are removed in OSS mode.
        
        # Send to Slack webhook
        slack_webhook_url = os.getenv("SLACK_WEBHOOK_URL")
        if not slack_webhook_url:
            logger.error("SLACK_WEBHOOK_URL not set in environment variables")
            return
        
        # Add org_id to slack messages. This org_id is sent only to Finigami org integration URL.
        org_id = get_org_id_from_suite_id(suite_obj['suite_id'])
        message['blocks'].append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"Org ID: {org_id}"
                }
            ]
        })
        
        response = requests.post(slack_webhook_url, json=message)
        logger.info(f"Response: {response}")
        
        if response.status_code != 200:
            logger.error(f"Failed to send triage findings message. Status code: {response.status_code}")
        else:
            logger.info(f"Successfully sent triage findings message for suite run {suite_run_id}")
            
    except Exception as e:
        logger.error(f"Error sending triage findings message: {str(e)}")
        logger.debug(traceback.format_exc())

def send_message_to_org_if_credits_are_low(org_id: str, credits: int, send_to_integration: bool = False, ai_credits: bool = False) -> None:
    """
    Send a message to the org if the credits are low
    """
    try:
        # Create messages
        if ai_credits:
            integration_message = f"Your organization has {credits} AI credits left. Please add more AI credits to your organization."
            slack_message = f"*Organization {org_id} has {credits} AI credits left.*"
        else:
            integration_message = f"Your organization has {credits} minutes of credits left. Please add more credits to your organization."
            slack_message = f"*Organization {org_id} has {credits} minutes of credits left.*"
        
        # Create message blocks
        message_blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*:rotating_light: Credit Alert!*"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": integration_message if send_to_integration else slack_message
                }
            }
        ]
        
        # Org-specific webhook integrations are removed in OSS mode.
        
        # Send to Slack webhook
        slack_webhook_url = os.getenv("SLACK_WEBHOOK_URL")
        if not slack_webhook_url:
            logger.error("SLACK_WEBHOOK_URL not set in environment variables")
            return
        
        # Update message for Slack (use slack_message instead of integration_message)
        message_blocks[1]["text"]["text"] = slack_message
        message = {"blocks": message_blocks}
        
        response = requests.post(slack_webhook_url, json=message)
        if response.status_code != 200:
            logger.error(f"Failed to send message to org: {org_id} {response.text} {response.status_code}")

    except Exception as e:
        logger.error(f"Error in send_message_to_org_if_credits_are_low: {e}")
        logger.debug(traceback.format_exc())
        raise e

def schedule_run_error_notification(suite_id: str, error_message: str, send_to_integration: bool = False) -> None:
    """
    Send a notification to the org if the schedule run fails
    """
    try:
        # Create message blocks
        message_blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*:octagonal_sign: Schedule Run Error: {error_message}*"
                }
            }
        ]

        message = {"blocks": message_blocks}
        
        # Org-specific webhook integrations are removed in OSS mode.
        
        # Send to Slack webhook
        slack_webhook_url = os.getenv("SLACK_WEBHOOK_URL")
        if not slack_webhook_url:
            logger.error("SLACK_WEBHOOK_URL not set in environment variables")
            return
        
        response = requests.post(slack_webhook_url, json=message)
        if response.status_code != 200:
            logger.error(f"Failed to send message to org: {suite_id} {response.text} {response.status_code}")

    except Exception as e:
        logger.error(f"Error in schedule_run_error_notification: {e}")
        logger.debug(traceback.format_exc())