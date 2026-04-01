# Operation constants for access control
# Format: RESOURCE_ACTION

# Test operations
TEST_CREATE = "test:create"
TEST_GET = "test:get"
TEST_GET_ALL = "test:get_all"
TEST_UPDATE = "test:update"
TEST_DELETE = "test:delete"
TEST_RUN = "test:run"
TEST_RUN_AI = "test:run_ai"
TEST_GET_SCRIPT = "test:get_script"
TEST_CREATE_FROM_COMPOSE = "test:create_from_compose"
TEST_UPDATE_FROM_COMPOSE = "test:update_from_compose"

# Test run operations
TESTRUN_GET = "test_run:get"
TESTRUN_GET_ALL = "test_run:get_all"
TESTRUN_GET_LIVE_URLS = "test_run:get_live_urls"

# Suite operations
SUITE_CREATE = "suite:create"
SUITE_GET = "suite:get"
SUITE_GET_ALL = "suite:get_all"
SUITE_UPDATE = "suite:update"
SUITE_DELETE = "suite:delete"
SUITE_RUN = "suite:run"
SUITE_GET_TAGS = "suite:get_tags"

# Suite file operations
SUITE_FILE_CREATE = "suite_file:create"
SUITE_FILE_GET = "suite_file:get"
SUITE_FILE_GET_BY_SUITE = "suite_file:get_by_suite"
SUITE_FILE_UPDATE = "suite_file:update"
SUITE_FILE_DELETE = "suite_file:delete"
SUITE_FILE_DOWNLOAD = "suite_file:download"

# Suite run operations
SUITERUN_GET = "suite_run:get"
SUITERUN_GET_BY_SUITE = "suite_run:get_by_suite"

# Healing suggestion operations
HEALING_SUGGESTION_GET_BY_SUITERUN = "healing_suggestion:get_by_suite_run"
HEALING_SUGGESTION_UPDATE = "healing_suggestion:update"

# Compose operations
COMPOSE_CREATE = "compose:create"
COMPOSE_RUN = "compose:run"
COMPOSE_GET = "compose:get"
COMPOSE_CLOSE = "compose:close"
COMPOSE_GET_LIVE_URLS = "compose:get_live_urls"

# Environment operations
ENVIRONMENT_CREATE = "environment:create"
ENVIRONMENT_GET = "environment:get"
ENVIRONMENT_GET_BY_SUITE = "environment:get_by_suite"
ENVIRONMENT_UPDATE = "environment:update"
ENVIRONMENT_DELETE = "environment:delete"

# Element operations
ELEMENT_CREATE = "element:create"
ELEMENT_GET_BY_SUITE = "element:get_by_suite"
ELEMENT_UPDATE = "element:update"
ELEMENT_DELETE = "element:delete"
ELEMENT_MERGE = "element:merge"

# Credits operations
CREDITS_GET = "credits:get"
CREDITS_GET_BY_ORG_ID = "credits:get_by_org_id"
CREDITS_UPDATE = "credits:update"
CREDITS_CREATE = "credits:create"
CREDITS_LIST_LOW = "credits:list_low"

# Org queue/rate limit operations
ORG_RATE_LIMIT_GET = "org_rate_limit:get"
ORG_RATE_LIMIT_UPDATE = "org_rate_limit:update"

# Schedule operations
SCHEDULE_CREATE = "schedule:create"
SCHEDULE_GET_BY_SUITE = "schedule:get_by_suite"
SCHEDULE_UPDATE = "schedule:update"
SCHEDULE_DELETE = "schedule:delete"

# Goal operations
GOAL_CREATE = "goal:create"
GOAL_GET = "goal:get"
GOAL_CREATE_SIGN_IN_FLOW = "goal:create_sign_in_flow"
GOAL_CREATE_SIGN_UP_FLOW = "goal:create_sign_up_flow"


# Notification operations
NOTIFICATION_RECIPIENTS_GET_BY_SUITE = "notification:recipients_get_by_suite"
NOTIFICATION_RECIPIENTS_CREATE = "notification:recipients_create"
NOTIFICATION_RECIPIENTS_UPDATE = "notification:recipients_update"

# Test plan operations
TEST_PLAN_GENERATE = "test_plan:generate"
TEST_PLAN_CREATE_BULK_TESTS = "test_plan:create_bulk_tests"

# Element store operations
ELEMENT_STORE_CREATE = "element_store:create"
ELEMENT_STORE_GET_BY_SUITE = "element_store:get_by_suite"
ELEMENT_STORE_UPDATE = "element_store:update"
ELEMENT_STORE_DELETE = "element_store:delete"

# Test segment operations
TEST_SEGMENT_CREATE = "test_segment:create"
TEST_SEGMENT_GET = "test_segment:get"
TEST_SEGMENT_GET_BY_SUITE = "test_segment:get_by_suite"
TEST_SEGMENT_UPDATE = "test_segment:update"
TEST_SEGMENT_DELETE = "test_segment:delete"

# Triage operations
PLAYWRIGHT_TRIAGE = "pw:triage"
TRIAGE_GET_ACTIVITY = "pw:triage:get_activity"
