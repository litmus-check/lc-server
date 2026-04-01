import { BrowserConfig } from '../types/browser';
import { AgentConfig } from '../types/state';

export const DEFAULT_BROWSER_CONFIG: BrowserConfig = {
    headless: false,
    viewport: {
        width: 1366,
        height: 768
    },
    disableSecurity: false,
    extraChromiumArgs: [],
    userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    locale: 'en-US',
    tracePath: './traces',
    timeout: 30000,
    retryAttempts: 3,
    waitBetweenActions: 1000,
    screenshotBeforeAction: true,
    screenshotAfterAction: true
};

export const AI_CREDIT_UNIT = 1.0;
export const TRIAGE_CREDIT_UNIT = 1.0;

export const DEFAULT_AGENT_CONFIG: AgentConfig = {
    maxRetries: 3,
    timeout: 30000,
    waitBetweenActions: 1000,
    screenshotBeforeAction: true,
    screenshotAfterAction: true,
    logLevel: 'info'
};

export const ACTION_TYPES = {
    // AI Actions
    CLICK: 'ai_click',
    VERIFY: 'ai_verify',
    ASSERT: 'ai_assert',
    VERIFY_EMAIL: 'verify_email',
    INPUT: 'ai_input',
    SELECT: 'ai_select',
    HOVER: 'ai_hover',
    FILE_UPLOAD: 'ai_file_upload',
    GOAL: 'ai_goal',
    SCRIPT: 'ai_script',

    // Non-AI Actions
    GO_TO_URL: 'go_to_url',
    GO_BACK: 'go_back',
    WAIT_TIME: 'wait_time',
    OPEN_TAB: 'open_tab',
    RUN_SCRIPT: 'run_script',
    SCROLL: 'scroll',
    SWITCH_TAB: 'switch_tab',
    PAGE_RELOAD: 'page_reload',
    KEY_PRESS: 'key_press',
    VERIFICATION: 'verify',

    // Special Actions
    CLEAR_BROWSER: 'clear_browser',
    SET_STATE_VARIABLE: 'set_state_variable',
    API_INTERCEPT: 'api_intercept',
    REMOVE_API_HANDLERS: 'remove_api_handlers',
    API_MOCK: 'api_mock'
} as const;

export const SUPPORTED_AI_ACTIONS = [
    ACTION_TYPES.CLICK,
    ACTION_TYPES.VERIFY,
    ACTION_TYPES.ASSERT,
    ACTION_TYPES.VERIFY_EMAIL,
    ACTION_TYPES.INPUT,
    ACTION_TYPES.SELECT,
    ACTION_TYPES.HOVER,
    ACTION_TYPES.FILE_UPLOAD,
    ACTION_TYPES.GOAL,
    ACTION_TYPES.SCRIPT
]

export const SUPPORTED_NON_AI_ACTIONS = [
    ACTION_TYPES.GO_TO_URL,
    ACTION_TYPES.GO_BACK,
    ACTION_TYPES.WAIT_TIME,
    ACTION_TYPES.OPEN_TAB,
    ACTION_TYPES.RUN_SCRIPT,
    ACTION_TYPES.SCROLL,
    ACTION_TYPES.SWITCH_TAB,
    ACTION_TYPES.PAGE_RELOAD,
    ACTION_TYPES.KEY_PRESS,
    ACTION_TYPES.VERIFICATION,
    ACTION_TYPES.API_INTERCEPT,
    ACTION_TYPES.REMOVE_API_HANDLERS,
    ACTION_TYPES.API_MOCK
]

export const INSTRUCTION_TYPES = {
    AI: 'AI',
    NON_AI: 'Non-AI',
    GOAL: 'Goal',
    STOP: 'Stop',
    CLEAR: 'Clear'
} as const;

export const INSTRUCTION_STATUS = {
    PENDING: 'pending',
    RUNNING: 'running',
    COMPLETED: 'completed',
    FAILED: 'failed'
} as const;

export const ERROR_TYPES = {
    EXCEPTION: 'exception',
    WARNING: 'warning'
} as const;

export const LOG_LEVELS = {
    DEBUG: 'debug',
    INFO: 'info',
    WARN: 'warn',
    ERROR: 'error'
} as const;

export const FRAMEWORKS = {
    PLAYWRIGHT: 'playwright'
} as const;

export const TASK_STATUS = {
    RUNNING: 'running',
    SUCCESS: 'success',
    FAILED: 'failed',
    COMPLETED: 'completed'
} as const;

export const ERROR_STATUS = {
    SUCCESS: 'success',
    ERROR: 'error',
    WARNING: 'warning',
} as const;

export const FILE_UPLOADS_DIR = './file_uploads';

// HTML Cleaning Constants
export const DEFAULT_WORD_COUNT_LIMIT = 10000;

// Browser Fingerprinting Constants
export const DEVICE_TYPES = {
    DESKTOP: 'desktop',
    MOBILE: 'mobile'
} as const;

export const OPERATING_SYSTEMS = {
    WINDOWS: 'windows',
    MACOS: 'macos',
    LINUX: 'linux',
    IOS: 'ios',
    ANDROID: 'android'
} as const;

export const BROWSER_TYPES = {
    CHROME: 'chrome',
    SAFARI: 'safari',
    FIREFOX: 'firefox',
    EDGE: 'edge'
} as const;

// User Agent strings for different OS and browser combinations
export const USER_AGENTS = {
    // Windows User Agents
    [OPERATING_SYSTEMS.WINDOWS]: {
        [BROWSER_TYPES.CHROME]: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        [BROWSER_TYPES.FIREFOX]: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0',
        [BROWSER_TYPES.EDGE]: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0',
        [BROWSER_TYPES.SAFARI]: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15'
    },
    
    // macOS User Agents
    [OPERATING_SYSTEMS.MACOS]: {
        [BROWSER_TYPES.CHROME]: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        [BROWSER_TYPES.FIREFOX]: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:123.0) Gecko/20100101 Firefox/123.0',
        [BROWSER_TYPES.SAFARI]: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
        [BROWSER_TYPES.EDGE]: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0'
    },
    
    // Linux User Agents
    [OPERATING_SYSTEMS.LINUX]: {
        [BROWSER_TYPES.CHROME]: 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        [BROWSER_TYPES.FIREFOX]: 'Mozilla/5.0 (X11; Linux x86_64; rv:123.0) Gecko/20100101 Firefox/123.0',
        [BROWSER_TYPES.SAFARI]: 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
        [BROWSER_TYPES.EDGE]: 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0'
    },
    
    // iOS User Agents (Mobile)
    [OPERATING_SYSTEMS.IOS]: {
        [BROWSER_TYPES.SAFARI]: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
        [BROWSER_TYPES.CHROME]: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/122.0.6261.89 Mobile/15E148 Safari/604.1',
        [BROWSER_TYPES.FIREFOX]: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) FxiOS/123.0 Mobile/15E148 Safari/605.1.15',
        [BROWSER_TYPES.EDGE]: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 EdgiOS/122.0.2365.80 Mobile/15E148 Safari/605.1.15'
    },
    
    // Android User Agents (Mobile)
    [OPERATING_SYSTEMS.ANDROID]: {
        [BROWSER_TYPES.CHROME]: 'Mozilla/5.0 (Linux; Android 14; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.6261.89 Mobile Safari/537.36',
        [BROWSER_TYPES.FIREFOX]: 'Mozilla/5.0 (Android 14; Mobile; rv:123.0) Gecko/123.0 Firefox/123.0',
        [BROWSER_TYPES.SAFARI]: 'Mozilla/5.0 (Linux; Android 14; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/122.0.6261.89 Mobile Safari/537.36',
        [BROWSER_TYPES.EDGE]: 'Mozilla/5.0 (Linux; Android 14; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.6261.89 Mobile Safari/537.36 EdgA/122.0.2365.80'
    }
} as const;

export const DEFAULT_BROWSER_ARGS = [
    '--no-sandbox',
    '--disable-setuid-sandbox',
    '--disable-dev-shm-usage',
    '--disable-accelerated-2d-canvas',
    '--no-first-run',
    '--no-zygote',
    '--disable-gpu',
    '--disable-blink-features=AutomationControlled',
    '--disable-features=IsolateOrigins,site-per-process',
    '--disable-site-isolation-trials'
];

// Variable regex pattern for matching ${variable_name} format
export const VARIABLE_REGEX_PATTERN = /\$\{(?!state\.)(.*?)\}/g;   // Exclude ${state.*}
export const ENV_VARIABLE_REGEX_PATTERN = /\{\{env.([^}]+)\}\}/g;

// Regex pattern for matching ${state.*} template literals
export const STATE_TEMPLATE_REGEX = /\$\{state\.[^}]+\}/;

// Verification validation constants
export const VERIFICATION_TARGETS = {
    ELEMENT: 'element',
    PAGE: 'page'
} as const;

export const VERIFICATION_LOCATOR_TYPES = {
    MANUAL: 'manual',
    AI: 'ai'
} as const;

export const VERIFICATION_PAGE_PROPERTIES = {
    VERIFY_TITLE: 'verify_title',
    VERIFY_URL: 'verify_url'
} as const;

export const VERIFICATION_ELEMENT_PROPERTIES = {
    VERIFY_TEXT: 'verify_text',
    VERIFY_CLASS: 'verify_class',
    VERIFY_ATTRIBUTE: 'verify_attribute',
    VERIFY_COUNT: 'verify_count',
    VERIFY_VALUE: 'verify_value',
    VERIFY_CSS: 'verify_css',
    VERIFY_IF_VISIBLE: 'verify_if_visible',
    VERIFY_IF_CHECKED: 'verify_if_checked',
    VERIFY_IF_EMPTY: 'verify_if_empty',
    VERIFY_IF_IN_VIEWPORT: 'verify_if_in_viewport'
} as const;

export const VERIFICATION_CHECKS = {
    IS: 'is',
    CONTAINS: 'contains',
    GREATER_THAN: 'greater_than',
    LESS_THAN: 'less_than',
    GREATER_THAN_OR_EQUAL: 'greater_than_or_equal',
    LESS_THAN_OR_EQUAL: 'less_than_or_equal'
} as const;

// Note :- If any new property is added, add it python constants file as well.
// Allowed values for different verification properties
export const VERIFICATION_PROPERTY_ALLOWED_VALUES = {
    [VERIFICATION_TARGETS.ELEMENT]: [
        VERIFICATION_ELEMENT_PROPERTIES.VERIFY_TEXT,
        VERIFICATION_ELEMENT_PROPERTIES.VERIFY_CLASS,
        VERIFICATION_ELEMENT_PROPERTIES.VERIFY_ATTRIBUTE,
        VERIFICATION_ELEMENT_PROPERTIES.VERIFY_COUNT,
        VERIFICATION_ELEMENT_PROPERTIES.VERIFY_VALUE,
        VERIFICATION_ELEMENT_PROPERTIES.VERIFY_CSS,
        VERIFICATION_ELEMENT_PROPERTIES.VERIFY_IF_VISIBLE,
        VERIFICATION_ELEMENT_PROPERTIES.VERIFY_IF_CHECKED,
        VERIFICATION_ELEMENT_PROPERTIES.VERIFY_IF_EMPTY,
        VERIFICATION_ELEMENT_PROPERTIES.VERIFY_IF_IN_VIEWPORT
    ],
    [VERIFICATION_TARGETS.PAGE]: [
        VERIFICATION_PAGE_PROPERTIES.VERIFY_TITLE,
        VERIFICATION_PAGE_PROPERTIES.VERIFY_URL
    ]
} as const;

// Properties that require sub_property
export const VERIFICATION_PROPERTIES_REQUIRING_SUB_PROPERTY = [
    VERIFICATION_ELEMENT_PROPERTIES.VERIFY_ATTRIBUTE,
    VERIFICATION_ELEMENT_PROPERTIES.VERIFY_CSS
] as const;

// Valid checks for each property
export const VERIFICATION_PROPERTY_CHECKS = {
    [VERIFICATION_PAGE_PROPERTIES.VERIFY_TITLE]: [
        VERIFICATION_CHECKS.IS,
        VERIFICATION_CHECKS.CONTAINS
    ],
    [VERIFICATION_PAGE_PROPERTIES.VERIFY_URL]: [
        VERIFICATION_CHECKS.IS,
        VERIFICATION_CHECKS.CONTAINS
    ],
    [VERIFICATION_ELEMENT_PROPERTIES.VERIFY_TEXT]: [
        VERIFICATION_CHECKS.IS,
        VERIFICATION_CHECKS.CONTAINS
    ],
    [VERIFICATION_ELEMENT_PROPERTIES.VERIFY_CLASS]: [
        VERIFICATION_CHECKS.IS,
        VERIFICATION_CHECKS.CONTAINS
    ],
    [VERIFICATION_ELEMENT_PROPERTIES.VERIFY_ATTRIBUTE]: [
        VERIFICATION_CHECKS.IS,
        VERIFICATION_CHECKS.CONTAINS
    ],
    [VERIFICATION_ELEMENT_PROPERTIES.VERIFY_COUNT]: [
        VERIFICATION_CHECKS.IS,
        VERIFICATION_CHECKS.GREATER_THAN,
        VERIFICATION_CHECKS.LESS_THAN,
        VERIFICATION_CHECKS.GREATER_THAN_OR_EQUAL,
        VERIFICATION_CHECKS.LESS_THAN_OR_EQUAL
    ],
    [VERIFICATION_ELEMENT_PROPERTIES.VERIFY_VALUE]: [
        VERIFICATION_CHECKS.IS,
        VERIFICATION_CHECKS.CONTAINS
    ],
    [VERIFICATION_ELEMENT_PROPERTIES.VERIFY_CSS]: [
        VERIFICATION_CHECKS.IS,
        VERIFICATION_CHECKS.CONTAINS
    ]
} as const;

// Mode constants
export const TRIAGE_MODE = 'triage';

// TRIAGE CATEGORIES
export const TRIAGE_CATEGORIES = {
    RAISE_BUG: 'raise_bug',
    UPDATE_SCRIPT: 'update_script',
    CANNOT_CONCLUDE: 'cannot_conclude',
    RETRY_WITHOUT_CHANGES: 'retry_without_changes',
    SUCCESSFUL_ON_RETRY: 'successful_on_retry'
} as const;

// TRIAGE SUB CATEGORIES
export const TRIAGE_SUB_CATEGORIES = {
    ADD_NEW_STEP: 'add_new_step',
    REMOVE_STEP: 'remove_step',
    REPLACE_STEP: 'replace_step',
    RE_GENERATE_SCRIPT: 're_generate_script'
} as const;

// EDIT TYPES
export const EDIT_TYPES = {
    NEW: 'new',
    UPDATE: 'update',
    UNCHANGED: 'unchanged',
    DELETE: 'delete'
} as const;

// API INTERCEPT ACTION TYPES
export const API_INTERCEPT_ACTIONS = {
    MODIFY_REQUEST: 'modify_request',
    MODIFY_RESPONSE: 'modify_response',
    ABORT_REQUEST: 'abort_request',
    RECORD_ONLY: 'record_only'
} as const;