TEST_STATUS_DRAFT = "draft"
TEST_STATUS_READY = "ready"
TEST_STATUS_BLANK = "blank"
TEST_STATUS_PROCESSING = "processing"
TEST_STATUS_FAILED = "failed"

# Suite statuses
SUITE_COMPLETED_STATUS = "completed"

# Test result statuses
RUNNING_STATUS = 'running'

QUEUED_STATUS = 'queued'

GIF_BLOB_STORAGE_FOLDER = 'gif_urls'

TRACE_BLOB_STORAGE_FOLDER = 'trace_urls'

SUCCESS_STATUS = 'success'

SUCCESS_FLAKY_STATUS = 'success-flaky'

SUCCESS_HEALED_STATUS = 'success-healed'

FAILED_STATUS = 'failed'

ERROR_STATUS = 'error'

SCRIPT_MODE = 'script'

AI_MODE = 'ai'

COMPOSE_MODE = 'compose'

TRIAGE_MODE = 'triage'

HEAL_MODE = 'heal'

TEST_RUN_MAX_TIMEOUT = 600   # 10 minutes
GOAL_RUN_MAX_TIMEOUT = 1200  # 20 minutes
TEST_RUN_MAX_STEPS = 50 

# Element constants
ELEMENT_DESCRIPTION_MAX_LENGTH = 1000 

TEST_RUN_RATE_LIMIT = 2  # Number of tests that can be run in parallel
ORG_TEST_RUN_RATE_LIMIT = 1  # Number of tests that can be run in parallel for an org

DEFAULT_ENV = "local"

LOCAL_BROWSER = "litmus_cloud"
REMOTE_BROWSER_BASE = "browserbase"
DEFAULT_BROWSER = LOCAL_BROWSER
ALLOWED_BROWSERS = [LOCAL_BROWSER, REMOTE_BROWSER_BASE]

# TEST RUNNER thread name
TEST_RUNNER_THREAD_NAME = "TestRunner"


#Compose Mode constants
BROWSERBASE_SESSION_TIMEOUT = 1200  # 20 minutes


# Docker constants
DOCKER_CONTAINER_CHECK_INTERVAL = 5   # Check for container status every 5 seconds

LITMUS_TEST_RUNNER_IMAGE = "litmus-test-runner:latest"

LITMUS_TEST_RUNNER_CONTAINER_NAME = "litmus-test-runner"

LITMUS_TEST_RUNNER_NETWORK_NAME = "litmus-test-runner-network"

REDIS_IMAGE = "redis:latest"

REDIS_CONTAINER_NAME = "redis"

DOCKER_MAX_RETRIES = 0      # Maximum number of retries for a test in docker container in script mode

TEST_MAX_RUN_RETRIES = 0    # Maximum number of retries for a test in script mode when the test fails.

REDIS_DATA_TTL = 3600       # 1 hour


# Compose session constants
BROWSERBASE_ENV = "browserbase"
LITMUS_CLOUD_ENV = "litmus_cloud"
ALLOWED_BROWSER_ENVS = [LITMUS_CLOUD_ENV, BROWSERBASE_ENV]

# Credits table constants

DEFAULT_BROWSER_MINUTES = 500*60   # 500 minutes

DEFAULT_AI_CREDITS = 100.00

# AI credit units for different operations
AI_CREDIT_UNIT = 1.0

#Threshold for sending message to org if credits are low
THRESHOLD_CREDITS = 30*60   # 30 minutes
THRESHOLD_AI_CREDITS = 0.00

# TRIGGER CONSTANTS
SCHEDULED_TRIGGER = 'scheduled'
MANUAL_TRIGGER = 'manual'

# Playwright Browser Configuration Constants

# Browser types
BROWSER_CHROME = "chrome"
BROWSER_FIREFOX = "firefox"
BROWSER_EDGE = "edge"
BROWSER_SAFARI = "safari"
ALLOWED_BROWSERS = [BROWSER_CHROME, BROWSER_FIREFOX, BROWSER_EDGE, BROWSER_SAFARI]
DEFAULT_BROWSER = BROWSER_CHROME

# Device types
DEVICE_TYPE_DESKTOP = "desktop"
DEVICE_TYPE_MOBILE = "mobile"
ALLOWED_DEVICE_TYPES = [DEVICE_TYPE_DESKTOP, DEVICE_TYPE_MOBILE]
DEFAULT_DEVICE_TYPE = DEVICE_TYPE_DESKTOP

# Operating systems for mobile devices
MOBILE_OS_ANDROID = "android"
MOBILE_OS_IOS = "ios"
ALLOWED_MOBILE_OS = [MOBILE_OS_ANDROID, MOBILE_OS_IOS]
DEFAULT_MOBILE_OS = MOBILE_OS_ANDROID

# Operating systems for desktop devices
DESKTOP_OS_MACOS = "macos"
DESKTOP_OS_WINDOWS = "windows"
ALLOWED_DESKTOP_OS = [DESKTOP_OS_MACOS, DESKTOP_OS_WINDOWS]
DEFAULT_DESKTOP_OS = DESKTOP_OS_WINDOWS

# Viewport configurations
VIEWPORT_CONFIGS = {
    # Desktop viewports
    "desktop":{
        "1920x1080": {"width": 1920, "height": 1080, "dpr": 1},
        "1366x768": {"width": 1366, "height": 768, "dpr": 1},
        "1536x864": {"width": 1536, "height": 864, "dpr": 2},
        "1280x720": {"width": 1280, "height": 720, "dpr": 1},
        "1024x768": {"width": 1024, "height": 768, "dpr": 1},
    },
    
    # Mobile viewports
    "mobile":{
        "414x896": {"width": 414, "height": 896, "dpr": 2},
        "390x844": {"width": 390, "height": 844, "dpr": 3},
        "375x812": {"width": 375, "height": 812, "dpr": 3},
        "360x800": {"width": 360, "height": 800, "dpr": 3},
        "320x568": {"width": 320, "height": 568, "dpr": 2}
    }
}

# Default viewport configuration
DEFAULT_VIEWPORT = "1920x1080"

# Device pixel ratio options
ALLOWED_DEVICE_PIXEL_RATIOS = [1, 2, 3]
DEFAULT_DEVICE_PIXEL_RATIO = 1

# Playwright Browser Configuration Schema
PLAYWRIGHT_CONFIG_SCHEMA = {
    "type": "object",
    "properties": {
        "browser": {
            "type": "string",
            "enum": ALLOWED_BROWSERS,
            "default": DEFAULT_BROWSER
        },
        "device": {
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "enum": ALLOWED_DEVICE_TYPES,
                    "default": DEFAULT_DEVICE_TYPE
                },
                "device_config": {
                    "type": "object",
                    "properties": {
                        "os": {
                            "type": "string",
                            "enum": ALLOWED_MOBILE_OS + ALLOWED_DESKTOP_OS,
                            "default": DEFAULT_DESKTOP_OS
                        }
                    },
                    "required": ["os"]
                }
            },
            "required": ["type", "device_config"]
        },
        "viewport": {
            "type": "object",
            "properties": {
                "width": {
                    "type": "integer",
                },
                "height": {
                    "type": "integer",
                }
            },
            "required": ["width", "height"]
        },
        "device_pixel_ratio": {
            "type": "integer",
            "enum": ALLOWED_DEVICE_PIXEL_RATIOS,
            "default": DEFAULT_DEVICE_PIXEL_RATIO
        }
    },
    "required": ["browser", "device", "viewport", "device_pixel_ratio"]
}

# Default Playwright Browser Configuration
DEFAULT_PLAYWRIGHT_CONFIG = {
    "browser": DEFAULT_BROWSER,
    "device": {
        "type": DEFAULT_DEVICE_TYPE,
        "device_config": {
            "os": DEFAULT_DESKTOP_OS
        }
    },
    "viewport": {
        "width": VIEWPORT_CONFIGS[DEFAULT_DEVICE_TYPE][DEFAULT_VIEWPORT]["width"],
        "height": VIEWPORT_CONFIGS[DEFAULT_DEVICE_TYPE][DEFAULT_VIEWPORT]["height"]
    },
    "device_pixel_ratio": DEFAULT_DEVICE_PIXEL_RATIO
}

# Variable regex pattern for matching ${variable_name} format, excluding ${state.*}
VARIABLE_REGEX_PATTERN = r'\$\{(?!state\.)([^}]+)\}'

# Environment variable regex pattern for matching {{env.variable_name}} format
ENV_VARIABLE_REGEX_PATTERN = r'\{\{env.([^}]+)\}\}'

# State template regex pattern for matching ${state.*} format
STATE_TEMPLATE_REGEX = r'\$\{state\.([^}]+)\}'

# File type constants
FILE_TYPE_DATA = "data"
FILE_TYPE_UPLOAD = "upload"
ALLOWED_FILE_TYPES = [FILE_TYPE_DATA, FILE_TYPE_UPLOAD]
DEFAULT_FILE_TYPE = FILE_TYPE_UPLOAD


# Support email
SUPPORT_EMAIL = "contact@litmuscheck.com"

COMPOSE_USER="user"
COMPOSE_AGENT="agent"

COMPOSE_AGENT_SIGN_IN="sign-in"
COMPOSE_AGENT_SIGN_UP="sign-up"

# Dummy suite ID for signin/signup agents when suite_id is not provided
DUMMY_SUITE_ID = "00000000-0000-0000-0000-000000000000"

# TRIAGE CATEGORIES
TRIAGE_CATEGORIES = {
    'RAISE_BUG': 'raise_bug',
    'UPDATE_SCRIPT': 'update_script', 
    'CANNOT_CONCLUDE': 'cannot_conclude',
    'RETRY_WITHOUT_CHANGES': 'retry_without_changes',
    'SUCCESSFUL_ON_RETRY': 'successful_on_retry'
}

# TRIAGE SUB CATEGORIES
TRIAGE_SUB_CATEGORIES = {
    'ADD_NEW_STEP': 'add_new_step',
    'REMOVE_STEP': 'remove_step',
    'REPLACE_STEP': 'replace_step',
    'RE_GENERATE_SCRIPT': 're_generate_script'
}

# Kubernetes Resource Specifications
KUBERNETES_CPU_REQUEST = "500m"
KUBERNETES_MEMORY_REQUEST = "1Gi"
KUBERNETES_CPU_LIMIT = "1"
KUBERNETES_MEMORY_LIMIT = "2Gi"

# Tag filter conditions
TAG_FILTER_CONDITION_CONTAINS_ANY = "contains_any"
TAG_FILTER_CONDITION_DOES_NOT_CONTAIN_ANY = "does_not_contain_any"
ALLOWED_TAG_FILTER_CONDITIONS = [TAG_FILTER_CONDITION_CONTAINS_ANY, TAG_FILTER_CONDITION_DOES_NOT_CONTAIN_ANY]

# Tag validation regex - only alphanumerics, underscores, and hyphens
TAG_VALIDATION_REGEX = r'^[a-zA-Z0-9_-]+$'