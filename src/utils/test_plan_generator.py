import json
import os
from typing import Dict, Any, List
from langchain_openai import AzureChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.tools import tool
from pydantic import BaseModel, Field
from log_config.logger import logger
from utils.utils_test_plan import (
    validate_input,
    create_llm_input,
    create_user_message,
    extract_existing_test_names,
    ensure_unique_test_names,
)

# Global variables for lazy initialization
_llm = None
_prompt_template = None


# -----------------------------
# Tool schema + definition
# -----------------------------
class TestItem(BaseModel):
    name: str = Field(..., description="The name of the test case")
    description: str = Field(..., description="The description of the test case")

class TestPlanSchema(BaseModel):
    test_plan: List[TestItem] = Field(
        ..., description="List of tests, each with name and description"
    )

@tool(args_schema=TestPlanSchema)
def generate_test_plan_tool(test_plan: List[TestItem]) -> dict:
    """Generate test plan based on suite context and feature description"""
    return {
        "test_plan": [item.dict() for item in test_plan],
        "processed_by": "TestPlanTool",
    }


# -----------------------------
# LLM initialization
# -----------------------------
def _initialize_llm() -> AzureChatOpenAI:
    try:
        azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        api_key = os.getenv("AZURE_OPENAI_KEY")
        deployment_name = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")
        model_name = os.getenv("AZURE_OPENAI_MODEL_NAME")

        if not all([azure_endpoint, api_key, deployment_name, model_name]):
            raise ValueError("Missing required Azure OpenAI environment variables")

        return AzureChatOpenAI(
          
            azure_deployment=deployment_name,
            api_key=api_key,
            azure_endpoint=azure_endpoint,
            api_version="2024-02-15-preview",
            temperature=0.7,
            max_tokens=4000,
        )
    except Exception as e:
        logger.error(f"Failed to initialize LLM: {str(e)}")
        raise e


def _get_llm() -> AzureChatOpenAI:
    global _llm
    if _llm is None:
        _llm = _initialize_llm()
    return _llm


def _load_prompt_template() -> str:
    try:
        prompt_file_path = os.path.join(
            os.path.dirname(__file__),
            "..", "prompts", "test_plan_generation_prompt.md"
        )
        with open(prompt_file_path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        logger.error("Prompt file not found")
        return ""
    except Exception as e:
        logger.error(f"Error reading prompt file: {str(e)}")
        return ""


def _get_prompt_template() -> str:
    global _prompt_template
    if _prompt_template is None:
        _prompt_template = _load_prompt_template()
    return _prompt_template


def generate_test_plan(suite_data: Dict[str, Any], feature_description: str) -> Dict[str, Any]:
    """
    Generate test plan using LangChain tool calling
    """
    try:
        is_valid, error_message = validate_input(suite_data, feature_description)
        if not is_valid:
            return {"error": error_message}

        llm_input = create_llm_input(suite_data, feature_description)
        existing_test_names = extract_existing_test_names(suite_data)

        result = _call_llm_for_test_plan(llm_input)
        if "error" in result:
            return {"error": result["error"]}

        test_plan = ensure_unique_test_names(result.get("test_plan", []), existing_test_names)

        return {
            "test_suggestions": test_plan,
            "suite_id": suite_data.get("suite_id"),
            "feature_description": feature_description,
            "tests_generated": len(test_plan),
            "status": "draft",
        }
    except Exception as e:
        logger.error(f"Error generating test plan: {str(e)}")
        return {"error": f"Failed to generate test plan: {str(e)}"}


# -----------------------------
# Internal LLM call
# -----------------------------
def _call_llm_for_test_plan(llm_input: Dict[str, Any]) -> Dict[str, Any]:
    try:
        system_message = SystemMessage(content=_get_prompt_template())
        user_message = HumanMessage(content=create_user_message(llm_input))

        # Bind the tool
        model_with_tools = _get_llm().bind_tools([generate_test_plan_tool])

        # Call model
        response = model_with_tools.invoke([system_message, user_message])

        logger.info(f"LLM Response: {response}")

        # Parse tool call
        tool_calls = getattr(response, "additional_kwargs", {}).get("tool_calls", [])
        if not tool_calls:
            return {"error": "No tool calls returned"}

        tool_call = tool_calls[0]
        if tool_call.get("function", {}).get("name") != "generate_test_plan_tool":
            return {"error": "Unexpected tool called"}

        tool_args = json.loads(tool_call["function"]["arguments"])
        return {"test_plan": tool_args.get("test_plan", [])}

    except Exception as e:
        logger.error(f"Error calling LLM with tool: {str(e)}")
        return {"error": f"LLM call failed: {str(e)}"}
