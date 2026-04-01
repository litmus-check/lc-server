from typing import Literal, Optional
from langchain_core.tools import tool
from pydantic import BaseModel, Field


class TriageResponseSchema(BaseModel):
    detailed_reasoning: str = Field(
        ...,
        description="Detailed reasoning across error message, network logs, console logs, screenshot etc."
    )
    action: Literal["raise_bug", "modify_test", "run_again", "review_manually"] = Field(
        ...,
        description="Recommended action: raise_bug, modify_test, run_again, or review_manually"
    )
    rationale: str = Field(
        ...,
        description="Summarized rationale for the suggested action"
    )
    severity: Optional[str] = Field(
        None,
        description="Severity level: critical, high, normal, or low. Only required if action is raise_bug"
    )
    ticket_summary: str = Field(
        ...,
        description="Brief summary for the JIRA ticket (should be less than 200 characters)"
    )
    ticket_description: str = Field(
        ...,
        description=(
            "Detailed description in simple markdown syntax (use only headings and bullet points, no complex markdown). "
            "Must include: test name, test description with expected behavior, issue description, potential impact, "
            "and specific artifacts (only error-related artifacts - exclude successful and unrelated requests). "
            "Network requests should be in curl bash format (without auth info). Include console errors and playwright errors. "
            "For 'review_manually' or 'run_again' actions: mention that a review is needed to assess if this is a task. "
            "For 'raise_bug' action: include severity, fix required to the product, or next step in investigation (e.g., review backend APIs). "
            "For 'modify_test' action: include the suggested fix to the test code."
        )
    )

@tool(args_schema=TriageResponseSchema)
def triage_analysis_tool(
    detailed_reasoning: str,
    action: Literal["raise_bug", "modify_test", "run_again", "review_manually"],
    rationale: str,
    ticket_summary: str,
    ticket_description: str,
    severity: Optional[str] = None
) -> dict:
    """Analyze Playwright test failure and provide triage recommendation"""
    result = {
        "detailed_reasoning": detailed_reasoning,
        "action": action,
        "rationale": rationale,
        "ticket_summary": ticket_summary,
        "ticket_description": ticket_description,
    }
    if action == "raise_bug" and severity:
        result["severity"] = severity
    return result

