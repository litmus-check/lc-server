import json
import re
from typing import List, Dict, Any, Tuple
from log_config.logger import logger

# Constants
MAX_SUITE_WORDS = 5000
DEFAULT_TESTS_PER_BATCH = 10

def build_suite_context(suite_data: Dict[str, Any]) -> str:
    """
    Build context string from suite data
    
    Args:
        suite_data: Dictionary containing suite information
        
    Returns:
        Formatted context string
    """
    context_parts = []
    
    # Add suite information
    if suite_data.get('name'):
        context_parts.append(f"Suite: {suite_data['name']}")
    
    if suite_data.get('description'):
        context_parts.append(f"Description: {suite_data['description']}")
    
    # Add existing tests
    context_parts.append("Existing Tests:")
    tests = suite_data.get('tests', [])
    
    if not tests:
        context_parts.append("No existing tests in the suite.")
    else:
        for i, test in enumerate(tests, 1):
            test_name = test.get('name', f'Test {i}')
            test_desc = test.get('description', 'No description')
            context_parts.append(f"{i}. {test_name}: {test_desc}")
    
    return '\n'.join(context_parts)

def extract_existing_test_names(suite_data: Dict[str, Any]) -> List[str]:
    """
    Extract list of existing test names from suite data
    
    Args:
        suite_data: Dictionary containing suite information
        
    Returns:
        List of existing test names
    """
    tests = suite_data.get('tests', [])
    return [test.get('name', '') for test in tests if test.get('name')]

def validate_input(suite_data: Dict[str, Any], feature_description: str) -> Tuple[bool, str]:
    """
    Validate input parameters for test plan generation
    
    Args:
        suite_data: Dictionary containing suite information
        feature_description: Description of the new feature
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not suite_data:
        return False, "Suite data is required"
    
    if not feature_description or not feature_description.strip():
        return False, "Feature description is required"
    
    if len(feature_description.strip()) < 10:
        return False, "Feature description must be at least 10 characters long"
    
    # Check suite context word limit
    suite_context = build_suite_context(suite_data)
    word_count = len(suite_context.split())
    
    if word_count > MAX_SUITE_WORDS:
        return False, f"Suite context exceeds {MAX_SUITE_WORDS} word limit. Current: {word_count} words"
    
    return True, ""

def create_llm_input(suite_data: Dict[str, Any], feature_description: str) -> Dict[str, Any]:
    """
    Create structured input for LLM
    
    Args:
        suite_data: Dictionary containing suite information
        feature_description: Description of the new feature
        
    Returns:
        Dictionary with structured input for LLM
    """
    suite_description = ""
    if suite_data.get('name'):
        suite_description += suite_data['name']
    if suite_data.get('description'):
        suite_description += f" - {suite_data['description']}"
    
    existing_tests = []
    for test in suite_data.get('tests', []):
        if test.get('name') and test.get('description'):
            existing_tests.append({
                'name': test['name'],
                'description': test['description']
            })
    
    return {
        'suiteDescription': suite_description.strip(),
        'existingTests': existing_tests,
        'featureDescription': feature_description.strip()
    }

def create_user_message(llm_input: Dict[str, Any]) -> str:
    """
    Create user message for LLM
    
    Args:
        llm_input: Structured input for LLM
        
    Returns:
        Formatted user message
    """
    message = "# Test Plan Generation Request\n\n"
    
    message += f"## Suite Description\n{llm_input['suiteDescription']}\n\n"
    
    message += "## Existing Tests\n"
    if not llm_input['existingTests']:
        message += "No existing tests in the suite.\n\n"
    else:
        for i, test in enumerate(llm_input['existingTests'], 1):
            message += f"{i}. **{test['name']}**: {test['description']}\n"
        message += "\n"
    
    message += f"## New Feature Description\n{llm_input['featureDescription']}\n\n"
    
    message += "Please generate comprehensive test plans for this new feature, considering the existing test suite context. Return your response as a JSON array of test plans."
    
    return message

def ensure_unique_test_names(test_plans: List[Dict[str, str]], existing_test_names: List[str]) -> List[Dict[str, str]]:
    """
    Ensure test names are unique by adding counters if needed
    
    Args:
        test_plans: List of generated test plans
        existing_test_names: List of existing test names
        
    Returns:
        List of test plans with unique names
    """
    unique_test_plans = []
    
    for test_plan in test_plans:
        test_name = test_plan["name"]
        counter = 1
        original_name = test_name
        
        while test_name in existing_test_names:
            test_name = f"{original_name} {counter}"
            counter += 1
        
        test_plan["name"] = test_name
        unique_test_plans.append(test_plan)
    
    return unique_test_plans