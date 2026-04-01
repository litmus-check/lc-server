import os
import sentry_sdk
import subprocess
from flask import Flask
from database import db_url, db
from log_config.logger import logger
from dotenv import load_dotenv, find_dotenv

from utils.utils_constants import *

from app_factory import get_app, initialize_services

app = get_app()
initialize_services()

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=6010)