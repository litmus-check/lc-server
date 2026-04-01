import traceback
from models.Test import Test
from models.Suite import Suite
from log_config.logger import logger

def is_user_authenticated(current_user, test_id=None, suite_id=None):
    try:
        org_id = None
        if suite_id:
            # If not present, fetch from the database
            suite_obj = Suite.query.filter_by(suite_id=suite_id).first()
            return not suite_obj or (current_user['org_id'] == suite_obj.org_id)

        if test_id:
            test_obj = Test.query.filter_by(id=test_id).first()
            if not test_obj or not test_obj.suite:
                return False
            return current_user['org_id'] == test_obj.suite.org_id

        return False
        
    except Exception as e:
        logger.error("Unable to authenticate user, " + str(e))
        logger.debug(traceback.format_exc())
        return False