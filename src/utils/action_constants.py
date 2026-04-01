 
# Supported Action Types
AI_ACTION = "AI"
NON_AI_ACTION = "Non-AI"
TEST_SEGMENT = "Test-Segment"
GOAL_ACTION = "Goal"
STOP_ACTION = "Stop"
CLEAR_ACTION = "Clear"
SUPPORTED_ACTION_TYPES = [AI_ACTION, NON_AI_ACTION, TEST_SEGMENT, GOAL_ACTION, STOP_ACTION, CLEAR_ACTION]

# Supported AI Actions
AI_CLICK = "ai_click"
AI_VERIFY = "ai_verify"
AI_ASSERT = "ai_assert"
AI_INPUT = "ai_input"
AI_SELECT = "ai_select"
AI_HOVER = "ai_hover"
AI_FILE_UPLOAD = "ai_file_upload"
AI_SCRIPT = "ai_script"
SUPPORTED_AI_ACTIONS = [AI_CLICK, AI_VERIFY, AI_ASSERT, AI_INPUT, AI_SELECT, AI_HOVER, AI_FILE_UPLOAD, AI_SCRIPT]

# Supported Non-AI Actions
GO_TO_URL = "go_to_url"
GO_BACK = "go_back"
WAIT_TIME = "wait_time"
OPEN_TAB = "open_tab"
RUN_SCRIPT = "run_script"
SCROLL = "scroll"
SWITCH_TAB = "switch_tab"
PAGE_RELOAD = "page_reload"
KEY_PRESS = "key_press"
VERIFY = "verify"
SET_STATE_VARIABLE = "set_state_variable"
API_INTERCEPT = "api_intercept"
REMOVE_API_HANDLERS = "remove_api_handlers"
API_MOCK = "api_mock"
SUPPORTED_NON_AI_ACTIONS = [GO_TO_URL, GO_BACK, WAIT_TIME, OPEN_TAB, RUN_SCRIPT, SCROLL, SWITCH_TAB, PAGE_RELOAD, KEY_PRESS, VERIFY, SET_STATE_VARIABLE, API_INTERCEPT, REMOVE_API_HANDLERS, API_MOCK]

# Supported Goal Actions
VERIFY_EMAIL = "verify_email"
CLEAR_BROWSER = "clear_browser"
AI_GOAL = "ai_goal"
SUPPORTED_GOAL_ACTIONS = [VERIFY_EMAIL, AI_GOAL]

# Supported Control Actions
SUPPORTED_CONTROL_ACTIONS = [STOP_ACTION]

# API Intercept Action Types
API_INTERCEPT_ACTION_MODIFY_REQUEST = "modify_request"
API_INTERCEPT_ACTION_MODIFY_RESPONSE = "modify_response"
API_INTERCEPT_ACTION_ABORT_REQUEST = "abort_request"
API_INTERCEPT_ACTION_RECORD_ONLY = "record_only"
API_INTERCEPT_ACTIONS = [
    API_INTERCEPT_ACTION_MODIFY_REQUEST,
    API_INTERCEPT_ACTION_MODIFY_RESPONSE,
    API_INTERCEPT_ACTION_ABORT_REQUEST,
    API_INTERCEPT_ACTION_RECORD_ONLY
]

# Special Agent Instruction IDs
SIGN_IN_GOAL_INSTRUCTION = "sign_in_goal_instruction"
SIGN_UP_GOAL_INSTRUCTION = "sign_up_goal_instruction"
# Required args for each AI action
AI_ACTION_REQUIRED_ARGS = {
    AI_CLICK: {},
    AI_VERIFY: {},
    AI_ASSERT: {},
    AI_INPUT: {
        "value": {  
            "required": True,
            "type": "string"
        }
    },
    AI_SELECT: {
        "value": {
            "required": True,
            "type": "string"
        }
    },
    AI_HOVER: {},
    AI_FILE_UPLOAD: {
        "file_id": {
            "required": True,
            "type": "string"
        }
    },
    AI_SCRIPT: {
        "description": {
            "required": False,
            "type": "string"
        }
    }
}
# Required args for each Non-AI action
NON_AI_ACTION_REQUIRED_ARGS = {
    GO_TO_URL: {
        "url": {
            "required": True,
            "type": "string"
        }
    },
    GO_BACK: {},
    WAIT_TIME: {
        "delay_seconds": {
            "required": True,
            "type": "number"
        }
    }   ,
    OPEN_TAB: {
        "url": {
            "required": True,
            "type": "string"
        }
    },
    RUN_SCRIPT: {
        "script": {
            "required": True,
            "type": "string"
        }
    },
    SCROLL: {
        "direction": {
            "required": True,
            "type": "string"
        },
        "value": {
            "required": True,
            "type": "number"
        }
    },
    SWITCH_TAB: {
        "url": {
            "required": True,
            "type": "string"
        }
    },
    VERIFY: {
        "target": {
            "required": True,
            "type": "string",
            "allowed_values": ["element", "page"]
        },
        "locator_type": {
            "required": False,
            "type": "string",
            "allowed_values": ["manual", "ai"]
        },
        "prompt": {
            "required": False,
            "type": "string"
        },
        "locator": {
            "required": False,
            "type": "string"
        },
        "property": {
            "required": True,
            "type": "string"
        },
        "check": {
            "required": False,
            "type": "string"
        },
        "sub_property": {
            "required": False,
            "type": "string"
        },
        "value": {
            "required": False,
            "type": "string"
        },
        "fail_test": {
            "required": True,
            "type": "boolean"
        },
        "expected_result": {
            "required": True,
            "type": "boolean"
        }
    },
    PAGE_RELOAD: {},
    KEY_PRESS: {
        "key_type": {
            "required": True,
            "type": "string"
        },
        "value": {
            "required": True,
            "type": "string"
        },
        "delay": {
            "required": False,
            "type": "number"
        }
    },
    SET_STATE_VARIABLE: {
        "variable_name": {
            "required": True,
            "type": "string"
        },
        "variable_value": {
            "required": True,
            "type": "any"
        }
    },
    API_INTERCEPT: {
        "url": {
            "required": True,
            "type": "string"
        },
        "method": {
            "required": True,
            "type": "string"
        },
        "action": {
            "required": True,
            "type": "string"
        },
        "js_code": {
            "required": False,
            "type": "string"
        },
        "variable_name": {
            "required": False,
            "type": "string"
        }
    },
    REMOVE_API_HANDLERS: {
        "url": {
            "required": True,
            "type": "string"
        }
    },
    API_MOCK: {
        "url": {
            "required": True,
            "type": "string"
        },
        "method": {
            "required": True,
            "type": "string"
        },
        "status_code": {
            "required": True,
            "type": "string"
        },
        "response_header": {
            "required": True,
            "type": "string"
        },
        "response_body": {
            "required": True,
            "type": "string"
        }
    }
}

# Boolean properties
VERIFICATION_BOOLEAN_PROPERTIES = [
    "verify_if_visible",
    "verify_if_checked",
    "verify_if_empty",
    "verify_if_in_viewport"
]

# Create AI action examples for system prompt
AI_ACTION_EXAMPLES = {
    AI_CLICK: {
        "action_format": '{{"action": "ai_click","prompt": ""}}',
        "action_example": '{{"action": "ai_click","prompt": "Click on Submit button"}}'
    },
    AI_VERIFY: {
        "action_format": '{{"action": "ai_verify","prompt": ""}}',
        "action_example": '{{"action": "ai_verify","prompt": "Verify if the login is successful"}}'
    },
    AI_ASSERT: {
        "action_format": '{{"action": "ai_assert","prompt": ""}}',
        "action_example": '{{"action": "ai_assert","prompt": "The page displays a success message after login"}}'
    },
    AI_INPUT: {
        "action_format": '{{"action": "ai_input","prompt": "", "value": ""}}',
        "action_example": '{{"action": "ai_input","prompt": "Input the text in username field", "value": "John Doe"}}',
        "args_explanation": "-value: The value to be used for the action."
    },
    AI_SELECT: {
        "action_format": '{{"action": "ai_select","prompt": "", "value": ""}}',
        "action_example": '{{"action": "ai_select","prompt": "Select the option from dropdown", "value": "Option 1"}}',
        "args_explanation": "-value: The value to be used for the action."
    },
    AI_HOVER: {
        "action_format": '{{"action": "ai_hover","prompt": ""}}',
        "action_example": '{{"action": "ai_hover","prompt": "Hover over the Submit button"}}'
    }
}

# Convenience constants for direct string access
VERIFICATION_TARGET_ELEMENT = "element"
VERIFICATION_TARGET_PAGE = "page"
VERIFICATION_LOCATOR_TYPE_MANUAL = "manual"
VERIFICATION_LOCATOR_TYPE_AI = "ai"

# Allowed values for different verification properties
VERIFICATION_PROPERTY_ALLOWED_VALUES = {
    VERIFICATION_TARGET_ELEMENT: [
        "verify_text",
        "verify_class",
        "verify_attribute",
        "verify_count",
        "verify_value",
        "verify_css",
        "verify_if_visible",
        "verify_if_checked",
        "verify_if_empty",
        "verify_if_in_viewport"
    ],
    VERIFICATION_TARGET_PAGE: [
        "verify_title",
        "verify_url"
    ]
}

# Properties that require sub_property
VERIFICATION_PROPERTIES_REQUIRING_SUB_PROPERTY = [
    "verify_attribute",
    "verify_css"
]

# Valid checks for each property
VERIFICATION_PROPERTY_CHECKS = {
    "verify_title": [
        "is",
        "contains"
    ],
    "verify_url": [
        "is",
        "contains"
    ],
    "verify_text": [
        "is",
        "contains"
    ],
    "verify_class": [
        "is",
        "contains"
    ],
    "verify_attribute": [
        "is",
        "contains"
    ],
    "verify_count": [
        "is",
        "greater_than",
        "less_than",
        "greater_than_or_equal",
        "less_than_or_equal"
    ],
    "verify_value": [
        "is",
        "contains"
    ],
    "verify_css": [
        "is",
        "contains"
    ]
}

# Action display structures for instruction formatting
ACTION_DISPLAY_STRUCTURES = {
    AI_CLICK: "Click on [prompt]",
    AI_HOVER: "Hover on [prompt]",
    AI_SELECT: "Select [value] from [prompt]",
    AI_INPUT: "Input [value] in [prompt]",
    AI_FILE_UPLOAD: "Upload file in [prompt]",
    AI_VERIFY: "Verify [prompt]",
    AI_ASSERT: "Assert [prompt]",
    GO_BACK: "Go back to last page",
    GO_TO_URL: "Go to URL [url]",
    VERIFY: "Verify [target]: [prompt]: [property] [check] [value]",
    WAIT_TIME: "Wait for [delay_seconds] seconds",
    OPEN_TAB: "Open a new tab with [url]",
    SWITCH_TAB: "Switch to tab with [url]",
    RUN_SCRIPT: "Run script [description]",
    SCROLL: "Scroll [direction] by [value] pixels",
    SET_STATE_VARIABLE: "Set state variable ",
    API_INTERCEPT: "Intercept API [method] [url]",
    REMOVE_API_HANDLERS: "Remove API handlers for [url]",
    API_MOCK: "Mock API [method] [url]"
}

# Action display names for instruction formatting
ACTION_DISPLAY_NAMES = {
    AI_CLICK: "Click",
    AI_HOVER: "Hover",
    AI_SELECT: "Select",
    AI_INPUT: "Input",
    AI_FILE_UPLOAD: "Upload File",
    AI_VERIFY: "AI Verify",
    AI_ASSERT: "AI Assert",
    GO_BACK: "Go Back",
    GO_TO_URL: "Go to URL",
    VERIFY: "Verify",
    WAIT_TIME: "Wait Time (seconds)",
    OPEN_TAB: "New Tab",
    SWITCH_TAB: "Switch Tab",
    RUN_SCRIPT: "Run Script",
    SCROLL: "Scroll",
    PAGE_RELOAD: "Page Reload",
    KEY_PRESS: "Key Press",
    SET_STATE_VARIABLE: "Set State Variable",
    API_INTERCEPT: "Intercept",
    REMOVE_API_HANDLERS: "Remove API Handlers",
    API_MOCK: "Mock API"
}

# Target display text mapping for verify actions
VERIFY_TARGET_DISPLAY_MAPPING = {
    VERIFICATION_TARGET_ELEMENT: "element",
    VERIFICATION_TARGET_PAGE: "page"
}

# Property display text mapping for verify actions
VERIFY_PROPERTY_DISPLAY_MAPPING = {
    "verify_title": "title",
    "verify_url": "URL",
    "verify_text": "text",
    "verify_class": "class",
    "verify_attribute": "attribute",
    "verify_count": "count",
    "verify_value": "value",
    "verify_css": "CSS",
    "verify_if_visible": "visibility",
    "verify_if_checked": "checked state",
    "verify_if_empty": "empty state",
    "verify_if_in_viewport": "viewport visibility"
}

# Mapping from incoming action identifiers to Playwright method names
ACTION_TO_PW_METHOD = {
    # AI-intent actions
    AI_INPUT: 'fill',
    AI_CLICK: 'click',
    AI_HOVER: 'hover',
    AI_SELECT: 'selectOption',
    AI_FILE_UPLOAD: 'setInputFiles',
    # Verify actions
    VERIFY: 'verify',
}

