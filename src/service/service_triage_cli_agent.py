import json
from typing import Dict, Any
from langchain_core.messages import SystemMessage, HumanMessage
from log_config.logger import logger
import traceback

from llm.agents.triage_agent import get_triage_llm
from llm.tools.triage_tool import triage_analysis_tool
from utils.utils_triagebot.message_utils import (
    get_prompt_template,
    create_user_message
)


def _call_triage_agent(request_data: dict) -> dict:
    """
    Call the LLM agent to analyze the test failure and return parsed tool arguments
    Args:
        request_data: Dictionary containing test failure information
    Returns:
        Dictionary containing parsed tool arguments (detailed_reasoning, action, rationale, severity)
    Raises:
        ValueError: If LLM call fails or returns invalid response
    """
    # Get LLM and prompt
    llm = get_triage_llm()
    system_prompt = get_prompt_template()
    
    if not system_prompt:
        raise ValueError("Failed to load prompt template")
    
    # Create messages
    system_message = SystemMessage(content=system_prompt)
    user_message_content = create_user_message(request_data)
    user_message = HumanMessage(content=user_message_content)
    
    # Bind the tool
    model_with_tools = llm.bind_tools([triage_analysis_tool])
    
    # Call model
    logger.info("Calling LLM for triage analysis")
    response = model_with_tools.invoke([system_message, user_message])
    
    logger.info(f"LLM Response: {response}")
    
    # Parse tool call
    tool_calls = getattr(response, "additional_kwargs", {}).get("tool_calls", [])
    if not tool_calls:
        logger.error("No tool calls returned from LLM")
        raise ValueError("Agent did not return a valid response")
    
    tool_call = tool_calls[0]
    if tool_call.get("function", {}).get("name") != "triage_analysis_tool":
        logger.error(f"Unexpected tool called: {tool_call.get('function', {}).get('name')}")
        raise ValueError("Unexpected agent response")
    
    # Parse tool arguments
    tool_args = json.loads(tool_call["function"]["arguments"])
    
    # Validate action
    action = tool_args.get("action")
    if action not in ["raise_bug", "modify_test", "run_again", "review_manually"]:
        logger.error(f"Invalid action: {action}")
        raise ValueError("Invalid agent response")
    
    # Validate severity if action is raise_bug
    if action == "raise_bug":
        severity = tool_args.get("severity")
        if not severity or severity not in ["critical", "high", "normal", "low"]:
            logger.error(f"Invalid severity: {severity}")
            raise ValueError("Invalid agent response")
    
    # Validate ticket_summary and ticket_description are present
    if not tool_args.get("ticket_summary"):
        logger.error("Missing ticket_summary in agent response")
    
    if not tool_args.get("ticket_description"):
        logger.error("Missing ticket_description in agent response")
    
    return tool_args


def triage_cli_agent_implementation(current_user: dict, request_data: dict) -> tuple[dict, int]:
    """
    Analyze Playwright test failure using LLM agent
    Args:
        current_user: Dictionary containing user information including role and org_id
        request_data: Dictionary containing test failure information
    Returns:
        Tuple of (response_dict, status_code)
    """
    try:
        logger.info("Triage implementation called")
        
        # Validate required fields
        if not request_data.get("testInfo"):
            return {"error": "testInfo is required"}, 400
        # if not request_data.get("testCode"):
        #     return {"error": "testCode is required"}, 400
        if not request_data.get("error"):
            return {"error": "error is required"}, 400
        
        # Call the LLM agent
        tool_args = _call_triage_agent(request_data)
        action = tool_args.get("action")
        
        # Build response
        result = {
            "detailed_reasoning": tool_args.get("detailed_reasoning", ""),
            "action": action,
            "rationale": tool_args.get("rationale", ""),
            "ticket_summary": tool_args.get("ticket_summary", ""),
            "ticket_description": tool_args.get("ticket_description", ""),
        }
        
        if action == "raise_bug" and tool_args.get("severity"):
            result["severity"] = tool_args.get("severity")
        
        logger.info(f"Triage analysis completed: action={action}")
        return result, 200
        
    except ValueError as e:
        logger.error(f"Validation error in triage_implementation: {str(e)}")
        return {"error": str(e)}, 500
    except Exception as e:
        logger.error(f"Error in triage_implementation: {str(e)}")
        logger.debug(traceback.format_exc())
        return {"error": "Internal server error"}, 500
