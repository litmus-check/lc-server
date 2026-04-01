import traceback
from security.authenticate import is_user_authenticated
from database import db
from models.Test import Test
from models.Suite import Suite
from sqlalchemy.orm import joinedload
from models.TestResult import TestResult
from log_config.logger import logger
from access_control.roles import ADMIN

# Get all the test logs of a test
def get_testrun_result(current_user, test_id, suite_run_id, page_num, limit):
    logger.info("Get test logs service called")
    try:
        # If test_id and suite_run_id is not provided, return all the test logs pagewise
        if not test_id: 
            if not suite_run_id:
                if current_user.get('role') != ADMIN:
                    # Filter by org_id for non-admin users
                    test_logs = TestResult.query.join(Test, TestResult.test_id == Test.id).join(Suite, Test.suite_id == Suite.suite_id).filter(Suite.org_id == current_user.get('org_id')).order_by(TestResult.start_date.desc()).paginate(page=page_num, per_page=limit)
                else:
                    test_logs = TestResult.query.order_by(TestResult.start_date.desc()).paginate(page=page_num, per_page=limit)
            else:
                if current_user.get('role') != ADMIN:
                    # Filter by org_id for non-admin users
                    test_logs = TestResult.query.join(Test, TestResult.test_id == Test.id).join(Suite, Test.suite_id == Suite.suite_id).filter(Suite.org_id == current_user.get('org_id'),TestResult.suite_run_id == suite_run_id).order_by(TestResult.start_date.desc()).paginate(page=page_num, per_page=limit)
                else:
                    test_logs = TestResult.query.filter(TestResult.suite_run_id == suite_run_id).order_by(TestResult.start_date.desc()).paginate(page=page_num, per_page=limit)
        else:
            if current_user.get('role') != ADMIN:
                # Filter by org_id for non-admin users
                test_logs = TestResult.query.join(Test, TestResult.test_id == Test.id).join(Suite, Test.suite_id == Suite.suite_id).filter(Suite.org_id == current_user.get('org_id'), Test.id == test_id).order_by(TestResult.start_date.desc()).paginate(page=page_num, per_page=limit)
            else:
                test_logs = TestResult.query.join(Test, TestResult.test_id == Test.id).join(Suite, Test.suite_id == Suite.suite_id).filter(Test.id==test_id).order_by(TestResult.start_date.desc()).paginate(page=page_num, per_page=limit)

        response = {}
        if suite_run_id:
            response['suite_run_id'] = suite_run_id
        if test_id:
            response['test_id'] = test_id
        response['testruns'] = []
        for test_log in test_logs.items:
            new_resp = {}
            new_resp['testrun_id'] = test_log.testrun_id
            new_resp['test_id'] = test_log.test_id
            new_resp['output'] = test_log.output
            new_resp['status'] = test_log.status
            new_resp['start_date'] = test_log.start_date
            new_resp['end_date'] = test_log.end_date
            new_resp['gif_url'] = test_log.gif_url
            new_resp['trace_url'] = test_log.trace_url
            new_resp['mode'] = test_log.mode
            new_resp['retries'] = test_log.retries
            new_resp['data_row_index'] = test_log.data_row_index
            response['testruns'].append(new_resp)

        response['metadata'] = {
            'page_number': test_logs.page,
            'total_pages': test_logs.pages,
            'total_records': test_logs.total,
            'page_size': len(test_logs.items)
        }
            
        return response, 200
    except Exception as e:
        logger.error(f"Error in get_test_usagalogs: {str(e)}")
        logger.debug(traceback.format_exc())
        response = {
            "error": "Internal server error"
        }
        return response, 500

def get_testrun_result_by_runid(current_user, testrun_id):
    logger.info("Get test run results by run id called")
    try:
        test_log = TestResult.query.filter_by(testrun_id=testrun_id).first()
        if not test_log or (current_user.get('role') != ADMIN and not is_user_authenticated(current_user, suite_id=None, test_id=test_log.test_id)):
            response = {
                "error": f"Test run with id {testrun_id} not found or user does not have access to it"
            }
            return response, 404
        response = test_log.serialize()
        return response, 200
    except Exception as e:
        logger.error(f"Error in get_test_usagalogs: {str(e)}")
        logger.debug(traceback.format_exc())
        response = {
            "error": "Internal server error"
        }
        return response, 500
    
# method to get the test run results by suite run id
def get_testrun_result_by_suite_run_id(suite_run_id, page_num, limit):
    logger.info("Get test run results by suite run id called")
    try:
        #Join with test table to get test name
        test_run_results = TestResult.query.filter_by(suite_run_id=suite_run_id).options(joinedload(TestResult.test)).order_by(TestResult.start_date.desc()).paginate(page=page_num, per_page=limit, error_out=False)
        
        return test_run_results
    except Exception as e:
        logger.error(f"Error in get_test_usagalogs: {str(e)}")
        logger.debug(traceback.format_exc())
