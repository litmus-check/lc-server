import time
from database import db
from log_config.logger import logger    


def retry_db_operation(func, retries=3, delay=1):
    for attempt in range(retries):
        try:
            # Try executing the DB operation
            return func()
        except Exception as e:
            logger.info(f"DB operation failed: {e}")
            db.session.rollback()
            if attempt == retries - 1:
                raise  # If the last attempt failed, raise the exception
            time.sleep(delay)  
        except Exception as e:
            raise e  