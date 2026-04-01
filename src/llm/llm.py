import os
from langchain_openai import AzureChatOpenAI
from log_config.logger import logger

# Global variable for lazy initialization (singleton pattern)
_llm_instance = None


def _create_llm() -> AzureChatOpenAI:
    """
    Create and configure Azure OpenAI LLM instance
    
    Returns:
        Configured AzureChatOpenAI instance
    
    Raises:
        ValueError: If required environment variables are missing
    """
    azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    api_key = os.getenv("AZURE_OPENAI_KEY")
    deployment_name = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")
    model_name = os.getenv("AZURE_OPENAI_MODEL_NAME")

    if not all([azure_endpoint, api_key, deployment_name, model_name]):
        raise ValueError("Missing required Azure OpenAI environment variables: "
                         "AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_KEY, "
                         "AZURE_OPENAI_DEPLOYMENT_NAME, AZURE_OPENAI_MODEL_NAME")

    return AzureChatOpenAI(
        azure_deployment=deployment_name,
        api_key=api_key,
        azure_endpoint=azure_endpoint,
        api_version="2024-02-15-preview",
        temperature=0.2,
        max_tokens=20000,
    )


def get_llm() -> AzureChatOpenAI:
    """
    Get or create the LLM instance (lazy initialization - singleton pattern)
    
    This is the single source of truth for LLM creation in the application.
    All agents and tools should use this function to get the LLM instance.
    
    Returns:
        AzureChatOpenAI instance
    
    Raises:
        ValueError: If LLM initialization fails
    """
    global _llm_instance
    if _llm_instance is None:
        try:
            _llm_instance = _create_llm()
            logger.info("LLM instance created successfully")
        except Exception as e:
            logger.error(f"Failed to initialize LLM: {str(e)}")
            raise
    return _llm_instance
