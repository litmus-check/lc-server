# Email utility functions for sending notifications

import requests
import json
import re
from log_config.logger import logger
import traceback
from service.service_notif_config import get_emails_for_suite
import os
from datetime import datetime
from dotenv import load_dotenv, find_dotenv
from utils.utils_constants import DEFAULT_ENV
from utils.utils_playwright_config import format_config_string

load_dotenv(find_dotenv("app.env"))

# Environment configuration
environment = os.getenv('ENVIRONMENT', DEFAULT_ENV)

# Whitelisted domains for email sending (only in non-PROD environments)
WHITELISTED_DOMAINS = ['litmuscheck.com', 'finigami.com']

def validate_email_format(email: str) -> bool:
    """
    Validate email format with comprehensive checks
    
    Args:
        email (str): Email address to validate
        
    Returns:
        bool: True if valid, False otherwise
    """
    if not isinstance(email, str):
        return False
    
    # Check if email is empty or whitespace
    email = email.strip()
    if not email:
        return False
    
    # Check for exactly one @ sign
    at_count = email.count('@')
    if at_count != 1:
        return False
    
    # Split email into local and domain parts
    local_part, domain_part = email.split('@')
    
    # Check local part is not empty
    if not local_part:
        return False
    
    # Check domain part has at least one dot
    if '.' not in domain_part:
        return False
    
    # Check domain part is not empty
    if not domain_part:
        return False
    
    # Use regex for comprehensive validation
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def validate_recipients_list(recipients: list) -> tuple:
    """
    Validate a list of email recipients
    
    Args:
        recipients (list): List of email addresses to validate
        
    Returns:
        tuple: (is_valid, error_message)
    """
    if not isinstance(recipients, list):
        return False, "Recipients must be an array of email addresses"
    
    # Check each email in the list
    for i, email in enumerate(recipients):
        if not isinstance(email, str):
            return False, f"Recipient at index {i} must be a string"
        
        if not validate_email_format(email):
            return False, f"Invalid email format: {email}"
    
    return True, None


def validate_recipients_domains(recipients: list) -> tuple:
    """
    Validate that all email recipients are from whitelisted domains in non-PROD environments
    
    Args:
        recipients (list): List of email addresses to validate
        
    Returns:
        tuple: (is_valid, error_message)
    """
    # Only check domains in non-PROD environments
    if environment == "prod":
        return True, None
    
    for i, email in enumerate(recipients):
        if not isinstance(email, str):
            continue
            
        # Extract domain from email
        if '@' in email:
            domain = email.split('@')[1].lower()
            if domain not in WHITELISTED_DOMAINS:
                return False, f"Email domain '{domain}' is not whitelisted."
    
    return True, None


def validate_override_emails(emails) -> tuple:
    """
    Validate override emails from API requests (for suite runs and schedules).
    Handles empty lists (which are valid overrides to skip email sending) and validates
    non-empty email lists.
    
    Args:
        emails: Email list from request (can be None, empty list, or list with emails)
        
    Returns:
        tuple: (is_valid, error_message)
        - If emails is None: returns (True, None) - no override provided
        - If emails is empty list: returns (True, None) - valid override to skip emails
        - If emails is non-empty list: validates and returns (is_valid, error_message)
    """
    # If emails is None, it's not provided - no validation needed
    if emails is None:
        return True, None
    
    # If emails is provided, it must be a list
    if not isinstance(emails, list):
        return False, "emails must be an array"
    
    # Empty list is valid (means skip email sending)
    if len(emails) == 0:
        return True, None
    
    # Validate non-empty email list format
    is_valid, error_message = validate_recipients_list(emails)
    if not is_valid:
        return False, error_message
    
    # Validate domain whitelist for non-PROD environments
    is_domain_valid, domain_error_message = validate_recipients_domains(emails)
    if not is_domain_valid:
        return False, domain_error_message
    
    return True, None

def send_email_impl(recipients, subject, body, sender_email, sender_name, bcc_emails=None):
    """Send email using Brevo API to multiple recipients at once"""
    # Handle both single email string and list of emails for backward compatibility
    if isinstance(recipients, str):
        recipients = [recipients]
    
    logger.info(f"Sending email to {len(recipients)} recipients: {recipients}")

    # Validate all email addresses
    valid_recipients = []
    for email in recipients:
        if validate_email_format(email):
            valid_recipients.append(email)
        else:
            logger.error(f"Invalid email id: {email}")
    
    if not valid_recipients:
        logger.error("No valid email recipients found")
        return False

    try:
        # Make call to brevo api to send email
        url = 'https://api.brevo.com/v3/smtp/email'
        headers = {
            'api-key': os.getenv('BREVO_API_KEY'),
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        }
        data = {
            "sender" : {
                "email": sender_email,
                "name": sender_name
            },
            "to" : [{"email": email} for email in valid_recipients],
            "subject" : subject,
            "htmlContent" : body
        }

        # Add BCC recipients if provided
        if bcc_emails:
            data["bcc"] = [{"email": email} for email in bcc_emails if validate_email_format(email)]

        # Whitelist check - only allow emails to litmuscheck.com or finigami.com in non-PROD environments
        if environment != "prod":
            # Check if any recipient domain is not whitelisted
            non_whitelisted_domains = []
            for email in valid_recipients:
                email_domain = email.split("@")[1] if "@" in email else ""
                if email_domain not in WHITELISTED_DOMAINS:
                    non_whitelisted_domains.append(email_domain)
            
            if non_whitelisted_domains:
                logger.warning(f"Email domains {non_whitelisted_domains} not whitelisted. Using sandbox mode.")
                data['headers'] = {
                    "X-Sib-Sandbox": "drop"
                }
        
        logger.info(f"Sending email data to Brevo: {json.dumps(data, indent=2)}")
        response = requests.post(url, json=data, headers=headers)

        logger.info(f"Brevo API response status: {response.status_code}")
        logger.info(f"Brevo API response: {response.text}")

        if response.status_code != 201:
            logger.error(f"Error while sending email: {response.text}")
            return False
        
        logger.info(f"Email sent successfully to {len(valid_recipients)} recipients: {valid_recipients}")
        return True
    except Exception as e:
        logger.error(f"Error in send_email_impl: {e}")
        logger.debug(traceback.format_exc())
        return False

def send_notification_email(org_id, suite_id, subject, body, override_emails=None):
    """
    Send notification email to recipients configured for a suite
    Args:
        org_id: Organization ID
        suite_id: Suite ID
        subject: Email subject
        body: Plain text email body
        override_emails: Optional list of email addresses to override suite's configured emails
    Returns:
        Boolean indicating success/failure
    """
    try:
        logger.info(f"send_notification_email called with org_id: {org_id}, suite_id: {suite_id}")
        logger.info(f"Subject: {subject}")
        logger.info(f"Email sending enabled for environment: {environment}")
        
        # Use override emails if provided, otherwise get email recipients for the suite
        # If override_emails is explicitly provided (even if empty list), use it
        # If override_emails is None, fall back to suite's configured emails
        if override_emails is not None:
            # Override emails were explicitly provided
            recipients = override_emails
            logger.info(f"Using override emails from request: {recipients}")
        else:
            # No override provided, use suite's configured emails
            recipients = get_emails_for_suite(suite_id)
            logger.info(f"Found recipients from suite config: {recipients}")
        
        if not recipients:
            logger.warning(f"No email recipients found for org_id: {org_id}, suite_id: {suite_id}")
            return False
        
        # Get sender configuration from environment variables
        sender_email = os.getenv('SENDER_EMAIL', 'mehul@finigamilabs.com')
        sender_name = os.getenv('SENDER_NAME', 'Mehul')
        
        # BCC email configuration - only include BCC in non-production environments
        logger.info(f"Current environment: {environment}")
        bcc_emails = None
        if environment != "prod":
            bcc_emails = os.getenv('BCC_EMAILS', 'nishanth@finigami.com').split(',') if os.getenv('BCC_EMAILS') else ['nishanth@finigami.com']
            logger.info(f"BCC enabled for non-prod environment: {bcc_emails}")
            logger.info(f"Emails will be sent in {environment} environment")
        else:
            logger.info("BCC disabled for production environment")
            logger.info(f"Emails will be sent in {environment} environment")
        
        # Send email to all recipients at once
        success = send_email_impl(recipients, subject, body, sender_email, sender_name, bcc_emails)
        
        if success:
            logger.info(f"Notification email sent successfully to all {len(recipients)} recipients for suite_id: {suite_id}")
        else:
            logger.error(f"Failed to send notification email to recipients for suite_id: {suite_id}")
        
        return success
        
    except Exception as e:
        logger.error(f"Error sending notification email: {str(e)}")
        logger.debug(traceback.format_exc())
        return False

def build_email_html(suite_name, results, failed_tests=None, report_link=None, logo_url=None, environment_name=None, config=None, tag_filter=None):
    """
    Build professional, responsive HTML email for test suite execution.
    
    Args:
        suite_name (str): Name of the suite
        results (dict): Dictionary with keys 'passed', 'failed', 'errors'
        failed_tests (list[str], optional): List of failed test names
        report_link (str, optional): Link to detailed report
        logo_url (str, optional): Publicly accessible URL of the brand logo
        environment_name (str, optional): Name of the environment where tests were executed
        config (dict, optional): Configuration details for the test execution
        tag_filter (dict, optional): Tag filter with 'condition' and 'tags' keys
    
    Returns:
        str: HTML email content
    """
    passed = results.get("passed", 0)
    failed = results.get("failed", 0)
    errors = results.get("errors", 0)

    # Dynamic subject line indicator
    status_text = "✅ Test Suite Passed" if failed == 0 and errors == 0 else "❌ Test Suite Failed"

    # Start HTML
    body = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1.0" />
  <title>Test Suite Execution Report</title>
  <style>
    @media only screen and (max-width: 600px) {{
      .container {{
        width: 100% !important;
        padding: 20px !important;
      }}
    }}
  </style>
</head>
<body style="margin:0;padding:0;background-color:#f4f6f8;font-family:Segoe UI,Roboto,Helvetica,Arial,sans-serif;line-height:1.6;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background-color:#f4f6f8;padding:20px 0;">
    <tr>
      <td align="center">
        <table class="container" width="600" cellspacing="0" cellpadding="0" border="0" style="background-color:#ffffff;border-radius:8px;overflow:hidden;box-shadow:0 4px 6px rgba(0,0,0,0.1);">
          
          <!-- Header -->
          <tr>
            <td align="center" style="background:linear-gradient(135deg,#AE00FF 0%,#4542CC 100%);padding:30px 20px;">
              {"<img src='" + logo_url + "' alt='Litmus Logo' width='120' style='margin-bottom:15px;display:block;' />" if logo_url else ""}
              <h1 style="margin:0;color:#ffffff;font-size:24px;font-weight:600;">{status_text}</h1>
              <p style="margin:10px 0 0 0;color:#e8f0fe;font-size:15px;">Execution completed for {suite_name}</p>
            </td>
          </tr>

          <!-- Results Summary -->
          <tr>
            <td style="padding:30px 20px;">
              <h2 style="margin:0 0 20px 0;color:#2d3748;font-size:18px;text-align:center;">Test Results Summary</h2>
              <table class="summary-table" width="100%" cellspacing="0" cellpadding="0" border="0" style="text-align:center;">
                <tr>
                  <td style="padding-bottom:15px;">
                    <table width="100%" cellspacing="0" cellpadding="0" border="0">
                      <tr>
                        <td style="background-color:#48bb78;color:#ffffff;border-radius:6px;font-size:14px;padding:15px;width:100%;">
                          <div style="font-size:22px;font-weight:700;">{passed}</div>
                          Passed
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>
                <tr>
                  <td style="padding-bottom:15px;">
                    <table width="100%" cellspacing="0" cellpadding="0" border="0">
                      <tr>
                        <td style="background-color:#f56565;color:#ffffff;border-radius:6px;font-size:14px;padding:15px;width:100%;">
                          <div style="font-size:22px;font-weight:700;">{failed}</div>
                          Failed
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>
                <tr>
                  <td>
                    <table width="100%" cellspacing="0" cellpadding="0" border="0">
                      <tr>
                        <td style="background-color:#ed8936;color:#ffffff;border-radius:6px;font-size:14px;padding:15px;width:100%;">
                          <div style="font-size:22px;font-weight:700;">{errors}</div>
                          Errors
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>
              </table>

            </td>
          </tr>
    """

    # Environment and Config Information section
    if environment_name or config or tag_filter:
        body += """
          <tr>
            <td style="padding:0 20px 30px 20px;">
              <h3 style="margin:0 0 15px 0;color:#2d3748;font-size:16px;font-weight:600;">🔧 Execution Details</h3>
              <table width="100%" cellspacing="0" cellpadding="0" border="0" style="background-color:#f7fafc;border-radius:6px;padding:15px;">
        """
        
        if environment_name:
            body += f"""
                <tr>
                  <td style="padding:8px 0;font-size:14px;color:#2d3748;">
                    <strong style="color:#4a5568;margin-right:8px;">Environment:</strong> {environment_name}
                  </td>
                </tr>
            """
        
        if config:
            # Format config information
            config_string = format_config_string(config) if config else "N/A"
            body += f"""
                <tr>
                  <td style="padding:8px 0;font-size:14px;color:#2d3748;">
                    <strong style="color:#4a5568;margin-right:8px;">Configuration:</strong> {config_string}
                  </td>
                </tr>
            """
        
        if tag_filter:
            condition = tag_filter.get('condition', '')
            tags = tag_filter.get('tags', [])
            tags_display = ', '.join(tags) if tags else 'None'
            body += f"""
                <tr>
                  <td style="padding:8px 0;font-size:14px;color:#2d3748;">
                    <strong style="color:#4a5568;margin-right:8px;">Tag Filter Condition:</strong> {condition if condition else 'N/A'}
                  </td>
                </tr>
                <tr>
                  <td style="padding:8px 0;font-size:14px;color:#2d3748;">
                    <strong style="color:#4a5568;margin-right:8px;">Tag Filter Tags:</strong> {tags_display}
                  </td>
                </tr>
            """
        
        body += """
              </table>
            </td>
          </tr>
        """

    # Failed tests section
    if failed_tests and len(failed_tests) > 0:
        body += f"""
          <tr>
            <td style="padding:0 20px 30px 20px;">
              <h3 style="margin:0 0 10px 0;color:#c05621;font-size:16px;font-weight:600;">⚠️ Failed Tests ({len(failed_tests)})</h3>
              <ul style="margin:0;padding:0;list-style:none;">
        """
        for i, test_name in enumerate(failed_tests, 1):
            body += f"""
                <li style="padding:8px 0;font-size:14px;color:#2d3748;">
                  <strong style="color:#f56565;margin-right:8px;">{i}.</strong> {test_name}
                </li>
            """
        body += """
              </ul>
            </td>
          </tr>
        """

    # Report link
    if report_link:
        body += f"""
          <tr>
            <td align="center" style="padding:20px;">
              <a href="{report_link}" style="display:inline-block;background:linear-gradient(135deg,#AE00FF 0%,#4542CC 100%);color:#ffffff;text-decoration:none;padding:14px 28px;border-radius:6px;font-weight:600;font-size:15px;">
                📊 View Detailed Report
              </a>
              <p style="margin:12px 0 0 0;color:#718096;font-size:13px;">Click above to view the full test execution report</p>
            </td>
          </tr>
        """

    # Footer
    body += f"""
          <tr>
            <td style="background-color:#f7fafc;padding:20px;text-align:center;border-top:1px solid #e2e8f0;">
              <p style="margin:0;color:#718096;font-size:13px;">This is an automated notification from your test execution system.</p>
              <p style="margin:6px 0 0 0;color:#a0aec0;font-size:12px;">Generated on {datetime.now().strftime("%B %d, %Y at %I:%M %p UTC")}</p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""
    return body

def suite_completion_email(org_id, suite_id, suite_name, test_results, failed_test_names=None, report_link=None, environment_name=None, config=None, tag_filter=None, override_emails=None):
    """
    Send test completion notification email using the specified template
    Args:
        org_id: Organization ID
        suite_id: Suite ID
        suite_name: Name of the test suite
        test_results: Dictionary containing test results
        failed_test_names: List of failed test names (optional)
        report_link: Link to the complete report (optional)
        environment_name: Name of the environment where tests were executed (optional)
        config: Configuration details for the test execution (optional)
        tag_filter: Tag filter dictionary with 'condition' and 'tags' keys (optional)
        override_emails: Optional list of email addresses to override suite's configured emails
    Returns:
        Boolean indicating success/failure
    """
    try:
        logger.info(f"suite_completion_email called with org_id: {org_id}, suite_id: {suite_id}, suite_name: {suite_name}")
        logger.info(f"test_results: {test_results}, failed_test_names: {failed_test_names}")
        # Determine if execution passed or failed
        passed = test_results.get('passed', 0)
        failed = test_results.get('failed', 0)
        errors = test_results.get('errors', 0)
        
        # Determine pass/fail status and emoji
        if failed > 0 or errors > 0:
            status_emoji = "❌"
            status_text = "Fail"
        else:
            status_emoji = "✅"
            status_text = "Pass"
        
        # Determine environment display name
        if environment_name and (environment_name == 'NA' or environment_name == 'Custom env variables'):
            env_display = "Custom"
        elif environment_name:
            env_display = environment_name
        else:
            env_display = "NA"

        # Create subject line with new format
        # Format: ❌ Fail: LitmusCheck Demo Suite (Env: Prod) (47 Pass, 6 Fail, 0 Error)
        subject = f"{status_emoji} {status_text}: {suite_name} (Env: {env_display}) ({passed} Pass, {failed} Fail, {errors} Error)"
        
        # Create professional email body using the build_email_html function
        logo_url = "https://testaifinigami.blob.core.windows.net/test-ai-results/litmuscheck_images/litmus-logo-light.png"
        body = build_email_html(
            suite_name=suite_name,
            results=test_results,
            failed_tests=failed_test_names,
            report_link=report_link,
            logo_url=logo_url,
            environment_name=environment_name,
            config=config,
            tag_filter=tag_filter
        )
        
        return send_notification_email(org_id, suite_id, subject, body, override_emails=override_emails)
        
    except Exception as e:
        logger.error(f"Error sending test completion email: {str(e)}")
        logger.debug(traceback.format_exc())
        return False


