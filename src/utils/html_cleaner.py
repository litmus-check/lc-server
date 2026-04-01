"""
HTML Cleaner utility for cleaning HTML content before AI processing.
Port of LitmusAgent's HtmlCleaner.ts to Python.
"""

import re
from typing import Optional
from log_config.logger import logger

DEFAULT_WORD_COUNT_LIMIT = 10000


def clean_html(
    html: str,
    remove_head: bool = True,
    remove_scripts: bool = True,
    remove_style_attributes: bool = True,
    remove_inline_styles: bool = True,
    remove_comments: bool = True,
    remove_event_handlers: bool = True,
    word_count_limit: Optional[int] = DEFAULT_WORD_COUNT_LIMIT
) -> str:
    """
    Clean HTML content by removing specified elements and attributes.
    
    Args:
        html: The HTML content to clean
        remove_head: Remove <head> section
        remove_scripts: Remove <script> tags
        remove_style_attributes: Remove style="..." attributes
        remove_inline_styles: Remove <style> tags
        remove_comments: Remove HTML comments
        remove_event_handlers: Remove onclick, onload, etc.
        word_count_limit: Maximum words to keep (None for no limit)
    
    Returns:
        Cleaned HTML content
    """
    try:
        cleaned_html = html
        
        # Remove head section
        if remove_head:
            cleaned_html = re.sub(r'<head[^>]*>[\s\S]*?</head>', '', cleaned_html, flags=re.IGNORECASE)
        
        # Remove script tags
        if remove_scripts:
            cleaned_html = re.sub(r'<script[^>]*>[\s\S]*?</script>', '', cleaned_html, flags=re.IGNORECASE)
        
        # Remove style attributes
        if remove_style_attributes:
            cleaned_html = re.sub(r'\sstyle\s*=\s*["\'][^"\']*["\']', '', cleaned_html, flags=re.IGNORECASE)
        
        # Remove inline style tags
        if remove_inline_styles:
            cleaned_html = re.sub(r'<style[^>]*>[\s\S]*?</style>', '', cleaned_html, flags=re.IGNORECASE)
        
        # Remove HTML comments
        if remove_comments:
            cleaned_html = re.sub(r'<!--[\s\S]*?-->', '', cleaned_html)
        
        # Remove event handlers
        if remove_event_handlers:
            event_handlers = [
                'onclick', 'onload', 'onchange', 'onsubmit', 
                'onmouseover', 'onmouseout', 'onfocus', 'onblur',
                'onkeydown', 'onkeyup', 'onkeypress'
            ]
            pattern = r'\s*(' + '|'.join(event_handlers) + r')\s*=\s*["\'][^"\']*["\']'
            cleaned_html = re.sub(pattern, '', cleaned_html, flags=re.IGNORECASE)
        
        # Apply word count limit
        if word_count_limit and word_count_limit > 0:
            cleaned_html = _apply_word_limit(cleaned_html, word_count_limit)
        
        logger.info(f'HTML cleaned successfully. Length: {len(cleaned_html)} chars')
        return cleaned_html
        
    except Exception as e:
        logger.error(f'Error cleaning HTML: {str(e)}')
        raise


def _apply_word_limit(html: str, word_limit: int) -> str:
    """Truncate HTML to approximately word_limit words."""
    # Extract text and count words
    text_only = re.sub(r'<[^>]+>', ' ', html)
    words = text_only.split()
    
    if len(words) <= word_limit:
        return html
    
    # Estimate cut position based on word ratio
    word_ratio = word_limit / len(words)
    cut_position = int(len(html) * word_ratio)
    
    truncated = html[:cut_position]
    
    # Ensure we don't cut in the middle of a tag
    last_open = truncated.rfind('<')
    last_close = truncated.rfind('>')
    
    if last_open > last_close:
        truncated = truncated[:last_open]
    
    logger.info(f'HTML truncated from {len(words)} to ~{word_limit} words')
    return truncated

