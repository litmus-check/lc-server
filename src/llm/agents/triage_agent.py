import os
from langchain_openai import AzureChatOpenAI
from log_config.logger import logger

# Global variable for lazy initialization
_llm = None


def _initialize_llm() -> AzureChatOpenAI:
    """
    Initialize Azure OpenAI LLM for triage analysis
    """
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
            temperature=0.2,
            max_tokens=20000,
        )
    except Exception as e:
        logger.error(f"Failed to initialize LLM: {str(e)}")
        raise e


def get_triage_llm() -> AzureChatOpenAI:
    """
    Get or initialize the triage LLM instance (lazy initialization)
    """
    global _llm
    if _llm is None:
        _llm = _initialize_llm()
    return _llm

