import re
import json
from sqlalchemy import text, cast, or_, and_, bindparam
from sqlalchemy.dialects.postgresql import JSONB
from utils.utils_constants import (
    TAG_VALIDATION_REGEX, 
    ALLOWED_TAG_FILTER_CONDITIONS,
    TAG_FILTER_CONDITION_CONTAINS_ANY,
    TAG_FILTER_CONDITION_DOES_NOT_CONTAIN_ANY
)
import traceback
from models.Suite import Suite
from database import db
from log_config.logger import logger

def validate_tags(tags):
    """
    Validate tags - tags can only contain alphanumerics, underscores, and hyphens.
    
    Args:
        tags: List of tag strings or None
        
    Returns:
        tuple: (error_message, status_code) or (None, 200) if validation passes
    """
    if tags is None:
        return None, 200
    
    if not isinstance(tags, list):
        logger.info(f"Tags validation failed: tags must be a list, got {type(tags).__name__}")
        return "Tags must be a list", 400
    
    for tag in tags:
        if not isinstance(tag, str):
            return f"Each tag must be a string. Found: {type(tag).__name__}", 400
        
        if not re.match(TAG_VALIDATION_REGEX, tag):
            logger.info(f"Tags validation failed: tag '{tag}' contains invalid characters")
            return f"Tag '{tag}' contains invalid characters. Tags can only contain alphanumerics, underscores, and hyphens", 400
    
    return None, 200

def validate_condition(condition):
    """
    Validate condition - condition must be one of the allowed tag filter conditions.
    
    Args:
        condition: Condition string or None
        
    Returns:
        tuple: (error_message, status_code) or (None, 200) if validation passes
    """
    if condition is None:
        return None, 200
    
    if not isinstance(condition, str):
        return f"Condition must be a string. Found: {type(condition).__name__}", 400
    
    if condition not in ALLOWED_TAG_FILTER_CONDITIONS:
        logger.info(f"Condition validation failed: invalid condition '{condition}'")
        return f"Invalid condition '{condition}'. Allowed values are: {', '.join(ALLOWED_TAG_FILTER_CONDITIONS)}", 400
    
    logger.info(f"Condition validation passed: {condition}")
    return None, 200

def validate_tag_filter(tag_filter):
    """
    Validate tags and conditions in tag_filter according to the following logic:
    - If tag_filter is None or empty → return valid
    - If tag_filter is provided but tags is empty and condition is provided → return error
    - If tag_filter is provided but tags is not empty and condition is not provided → return error
    - If tag_filter is provided but tags is not empty and condition is provided but not in allowed values → return error
    - If tag_filter is provided but tags is not empty and condition is provided and is in allowed values → return valid
    
    Args:
        tag_filter: Dict with 'condition' and 'tags' keys, or None
        
    Returns:
        tuple: (error_message, status_code) or (None, 200) if validation passes
    """
    # If tag_filter is None or empty, return valid
    if tag_filter is None or (isinstance(tag_filter, dict) and len(tag_filter) == 0):
        return None, 200

    if not isinstance(tag_filter, dict):
        return "Invalid tag_filter format", 400
    
    condition = tag_filter.get('condition')
    tags = tag_filter.get('tags')
    
    # If tags is empty or None but condition is provided, raise error
    if condition and (tags is None or (isinstance(tags, list) and len(tags) == 0)):
        logger.info(f"Tag filter validation failed: condition provided but tags is empty")
        return "tags cannot be empty when condition is provided", 400
    
    # If tags is provided (not None), validate tags and condition
    if tags is not None:
        # Validate tags (will check if it's a list and validate each tag)
        error_message, status_code = validate_tags(tags)
        if status_code != 200:
            return error_message, status_code
        
        # If tags is not empty, condition is required
        if isinstance(tags, list) and len(tags) > 0:
            # Condition is required when tags are provided
            if not condition:
                return "condition is required when tags are provided", 400
            
            # Validate condition
            error_message, status_code = validate_condition(condition)
            if status_code != 200:
                return error_message, status_code
    
    return None, 200


def apply_tag_filter_to_test_query(test_query, tag_filter):
    """
    Apply tag_filter conditions to a SQLAlchemy test query using PostgreSQL JSONB operators.
    Logic:
    - If tag_filter is None or empty → return query as-is (all tests)
    - If tag_filter is provided but tags is empty and condition is contains_any → return empty result (no tests)
    - If tag_filter is provided but tags is empty and condition is does_not_contain_any → return query as-is (all tests)
    - If tag_filter is provided but tags is not empty and condition is in allowed values → apply filter
    
    Args:
        test_query: SQLAlchemy query object for Test model
        tag_filter: Dict with 'condition' and 'tags' keys, or None
        
    Returns:
        Filtered SQLAlchemy query object, or original query if no valid filter

    Note :- Call validate tag_filter function before calling this function
    """
    # If no tag_filter or empty dict, return query as-is (run all tests)
    if not tag_filter or not isinstance(tag_filter, dict) or len(tag_filter) == 0:
        return test_query
    
    condition = tag_filter.get('condition')
    filter_tags = tag_filter.get('tags', [])
    
    # If tags is None, treat it as empty list
    if filter_tags is None:
        filter_tags = []
    
    logger.info(f"Applying tag filter - condition: {condition}, tags: {filter_tags}")
    
    # If tags is empty and condition is contains_any, return empty result (no tests)
    if len(filter_tags) == 0 and condition == TAG_FILTER_CONDITION_CONTAINS_ANY:
        # Return a query that will always be false (no results)
        return test_query.filter(text('1=0'))  # This will return no results
    
    # If tags is empty and condition is does_not_contain_any, return query as-is (all tests)
    if len(filter_tags) == 0 and condition == TAG_FILTER_CONDITION_DOES_NOT_CONTAIN_ANY:
        return test_query
    
    try:
        from models.Test import Test
        
        # Cast tags column to JSONB for PostgreSQL JSON operations
        tags_jsonb = cast(Test.tags, JSONB)
        
        # Build filter conditions for each tag
        # PostgreSQL ? operator checks if JSONB array contains a specific text value
        tag_conditions = []
        for idx, tag in enumerate(filter_tags):
            # Check if the JSONB array contains this tag value
            # Using ? operator: tags_jsonb ? 'tag_value'
            # Use bound parameters to prevent SQL injection
            param = bindparam(f"tag_param_{idx}", value=tag)
            tag_conditions.append(tags_jsonb.op('?')(param))
        
        if condition == TAG_FILTER_CONDITION_CONTAINS_ANY:
            # Test should have at least one tag from filter_tags
            # Using OR of all tag conditions
            # Note: Tests with NULL or empty tags are excluded
            test_query = test_query.filter(
                tags_jsonb.isnot(None),
                or_(*tag_conditions)
            )
        elif condition == TAG_FILTER_CONDITION_DOES_NOT_CONTAIN_ANY:
            # Test should NOT have any tag from filter_tags
            # This includes:
            # - Tests with NULL tags (None)
            # - Tests that don't contain any of the filter tags (empty arrays are handled by negation)
            
            # Check if tags is NULL
            tags_is_null = Test.tags.is_(None)
            
            # Check if tags does NOT contain any filter tag
            not_tag_conditions = [~tag_cond for tag_cond in tag_conditions]
            tags_does_not_contain_any = and_(*not_tag_conditions)
            
            # Combine: NULL OR doesn't contain any filter tag
            test_query = test_query.filter(
                tags_is_null | tags_does_not_contain_any
            )
        
        logger.info(f"Tag filter applied successfully with condition: {condition}")
        return test_query
        
    except Exception as e:
        # Log error and raise exception
        logger.error(f"Error in apply_tag_filter_to_test_query: {str(e)}")
        logger.debug(traceback.format_exc())
        raise e


def update_suite_tags_with_new_tags(suite_id: str, new_tags: list):
    """
    Update suite tags by adding new tags to the existing master set.
    This prevents duplicates at the suite level.
    
    Args:
        suite_id: UUID of the suite to update
        new_tags: List of new tags to add to the suite's master set
        
    Returns:
        None (updates the suite in the database)
    """
    try:
        
        # Get the suite
        suite = Suite.query.filter_by(suite_id=suite_id).first()
        if not suite:
            logger.info(f"Suite with id {suite_id} not found, cannot update tags")
            return
        
        # Get existing suite master tags as a set
        existing_tags = set()
        if suite.master_tags:
            try:
                existing_tags_list = json.loads(suite.master_tags) if isinstance(suite.master_tags, str) else suite.master_tags
                if isinstance(existing_tags_list, list):
                    existing_tags = set(existing_tags_list)
            except (json.JSONDecodeError, TypeError) as e:
                logger.info(f"Error parsing existing suite master tags for suite {suite_id}: {str(e)}")
                existing_tags = set()
        
        # Add new tags to the existing set
        if new_tags and isinstance(new_tags, list):
            existing_tags.update(new_tags)
        
        # Convert to sorted list for consistency
        suite_tags = sorted(list(existing_tags))
        
        # Update suite master tags
        suite.master_tags = json.dumps(suite_tags) if suite_tags else None
        db.session.commit()
        
        logger.info(f"Updated suite {suite_id} tags: {suite_tags}")
        
    except Exception as e:
        logger.error(f"Error updating suite tags for suite {suite_id}: {str(e)}")
        logger.debug(traceback.print_exc())