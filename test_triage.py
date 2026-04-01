#!/usr/bin/env python3
"""
Test script for triage implementation
"""
import json
import sys
import os
from dotenv import load_dotenv, find_dotenv

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from service.service_triage_cli_agent import triage_cli_agent_implementation

def main():
    # Load test data
    test_data_path = os.path.join(os.path.dirname(__file__), 'test_data', 'triage_request.json')
    
    with open(test_data_path, 'r') as f:
        request_data = json.load(f)
    
    # Create a dummy current_user
    current_user = {
        "id": "test_user_id",
        "org_id": "test_org_id",
        "role": "user"
    }
    
    print("=" * 80)
    print("Testing Triage Implementation")
    print("=" * 80)
    print(f"\nTest Info: {request_data.get('testInfo', {}).get('title', 'N/A')}")
    print(f"Error Message: {request_data.get('error', {}).get('message', 'N/A')[:100]}...")
    print(f"Screenshot present: {bool(request_data.get('screenshot', {}).get('data'))}")
    print("\n" + "=" * 80)
    print("Calling triage_implementation...")
    print("=" * 80 + "\n")
    
    # Check environment variables
    load_dotenv(find_dotenv("app.env"))
    
    print("\nChecking environment variables...")
    required_vars = ["AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_KEY", "AZURE_OPENAI_DEPLOYMENT_NAME", "AZURE_OPENAI_MODEL_NAME"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    if missing_vars:
        print(f"WARNING: Missing environment variables: {', '.join(missing_vars)}")
        print("The test may fail if these are not set.")
    else:
        print("All required environment variables are set.")
    
    # Call the implementation
    try:
        response, status_code = triage_cli_agent_implementation(current_user, request_data)
        
        print(f"\nStatus Code: {status_code}")
        print("\nResponse:")
        print(json.dumps(response, indent=2))
        
        if status_code == 200:
            print("\n" + "=" * 80)
            print("SUCCESS: Triage analysis completed")
            print("=" * 80)
            print(f"\nAction: {response.get('action')}")
            print(f"Rationale: {response.get('rationale')}")
            if response.get('severity'):
                print(f"Severity: {response.get('severity')}")
            
            # Check for new fields
            print("\n" + "=" * 80)
            print("Checking for ticket_summary and ticket_description fields...")
            print("=" * 80)
            has_ticket_summary = 'ticket_summary' in response
            has_ticket_description = 'ticket_description' in response
            
            print(f"\nticket_summary present: {has_ticket_summary}")
            if has_ticket_summary:
                summary = response.get('ticket_summary', '')
                print(f"ticket_summary length: {len(summary)} characters")
                print(f"ticket_summary content: {summary[:100]}..." if len(summary) > 100 else f"ticket_summary content: {summary}")
                if len(summary) >= 200:
                    print("⚠️  WARNING: ticket_summary is 200 characters or more (should be less than 200)")
            
            print(f"\nticket_description present: {has_ticket_description}")
            if has_ticket_description:
                description = response.get('ticket_description', '')
                print(f"ticket_description length: {len(description)} characters")
                print(f"ticket_description preview: {description[:200]}..." if len(description) > 200 else f"ticket_description content: {description}")
            
            if has_ticket_summary and has_ticket_description:
                print("\n✅ SUCCESS: Both ticket_summary and ticket_description are present in the response!")
            else:
                print("\n❌ ERROR: Missing required fields!")
                if not has_ticket_summary:
                    print("  - ticket_summary is missing")
                if not has_ticket_description:
                    print("  - ticket_description is missing")
        else:
            print("\n" + "=" * 80)
            print(f"ERROR: Status code {status_code}")
            print("=" * 80)
            if response.get('error'):
                print(f"Error message: {response.get('error')}")
            
    except Exception as e:
        print(f"\nEXCEPTION: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()

