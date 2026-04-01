import logging
from logging.handlers import TimedRotatingFileHandler
from dotenv import load_dotenv, find_dotenv
import os

load_dotenv(find_dotenv("app.env"))

if os.getenv("LOG_FILE_NAME"):
    FILE_NAME = os.getenv("LOG_FILE_NAME")
else:
    FILE_NAME = "logs/app.log"

def get_logger():
    # handle exception trace logging
    if not os.path.exists('logs'):
        os.makedirs('logs')
    
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter('[%(asctime)s] %(name)s %(levelname)s [%(filename)s %(lineno)d] %(message)s')
    file_handler = TimedRotatingFileHandler(FILE_NAME, when="midnight", interval=1, backupCount=7, encoding='utf-8')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    return logger

def redirect_sqlalchemy_logs():
    logging.getLogger('sqlalchemy').handlers.clear()
    logging.getLogger('sqlalchemy').addHandler(logging.getLogger(__name__).handlers[0])
    logging.getLogger('sqlalchemy').setLevel(logging.DEBUG)

    
logger = get_logger()

