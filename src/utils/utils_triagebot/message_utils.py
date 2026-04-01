import json
import os
from typing import Dict, Any, List
from log_config.logger import logger

# Global variable for lazy initialization
_prompt_template = None


def load_prompt_template() -> str:
    """
    Load the triage analysis prompt template from file
    """
    try:
        prompt_file_path = os.path.join(
            os.path.dirname(__file__),
            "..", "..", "prompts", "triage_analysis_prompt.md"
        )
        with open(prompt_file_path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        logger.error("Triage prompt file not found")
        return ""
    except Exception as e:
        logger.error(f"Error reading prompt file: {str(e)}")
        return ""


def get_prompt_template() -> str:
    """
    Get or load the prompt template (lazy initialization)
    """
    global _prompt_template
    if _prompt_template is None:
        _prompt_template = load_prompt_template()
    return _prompt_template


def format_screenshot_for_llm(screenshot_data: str, mime_type: str) -> Dict[str, Any]:
    """
    Format screenshot data for Langchain vision model
    Args:
        screenshot_data: Base64 encoded image data (with or without data URL prefix)
        mime_type: MIME type of the image (e.g., "image/jpeg", "image/png")
    Returns:
        Dictionary with image_url format for Langchain
    """
    # Remove data URL prefix if present
    if screenshot_data.startswith("data:"):
        # Extract base64 data after comma
        screenshot_data = screenshot_data.split(",", 1)[1]
    
    # Ensure we have the data URL format
    image_url = f"data:{mime_type};base64,{screenshot_data}"
    
    return {
        "type": "image_url",
        "image_url": {
            "url": image_url
        }
    }


def create_user_message(request_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Create user message with text and image content for vision model
    Args:
        request_data: Dictionary containing test failure information
    Returns:
        List that can be passed as content to HumanMessage
    """
    # Extract all relevant information
    test_info = request_data.get("testInfo", {})
    test_code = request_data.get("testCode", "")
    error = request_data.get("error", {})
    error_code_snippet = request_data.get("errorCodeSnippet", "")
    screenshot = request_data.get("screenshot", {})
    console_errors = request_data.get("consoleErrors", [])
    network_errors = request_data.get("networkErrors", [])
    
    # Build text content
    text_content = {
        "testInfo": test_info,
        "testCode": test_code,
        "error": error,
        "errorCodeSnippet": error_code_snippet,
        "consoleErrors": console_errors,
        "networkErrors": network_errors
    }
    
    message_content = [
        {
            "type": "text",
            "text": json.dumps(text_content, indent=2)
        }
    ]
    
    # Add screenshot if available
    if screenshot and screenshot.get("data"):
        screenshot_dict = format_screenshot_for_llm(
            screenshot.get("data"),
            screenshot.get("mimeType", "image/jpeg")
        )
        message_content.append(screenshot_dict)
    
    return message_content

