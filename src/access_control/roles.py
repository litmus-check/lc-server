from access_control.operation_constants import *

# Available roles
VIEWER = "viewer"
ADMIN = "admin"
USER = "user"
AVAILABLE_ROLES = [VIEWER, ADMIN, USER]

ROLES = {
    VIEWER: {
        "permissions": [
            SUITE_GET,
            SUITE_GET_ALL,
            SUITE_RUN,
            SUITERUN_GET,
            SUITERUN_GET_BY_SUITE,
            SUITE_FILE_GET,
            SUITE_FILE_GET_BY_SUITE,
            SUITE_FILE_DOWNLOAD,
            TEST_RUN,
            TEST_GET,
            TEST_GET_ALL,
            TESTRUN_GET,
            TESTRUN_GET_ALL,
            CREDITS_GET,
            ENVIRONMENT_GET,
            ENVIRONMENT_GET_BY_SUITE,
            SCHEDULE_GET_BY_SUITE,
            NOTIFICATION_RECIPIENTS_GET_BY_SUITE,
            ELEMENT_STORE_GET_BY_SUITE,
            ELEMENT_GET_BY_SUITE,
            TEST_SEGMENT_GET,
            TEST_SEGMENT_GET_BY_SUITE,
            ORG_RATE_LIMIT_GET,
            SUITE_GET_TAGS,
            HEALING_SUGGESTION_GET_BY_SUITERUN,
        ]
    },
    ADMIN: {
        "permissions": [
        ]
    },
    USER: {
        "permissions": [
        ]
    }
}

