import os
from dotenv import load_dotenv, find_dotenv
from flask_sqlalchemy import SQLAlchemy


db = SQLAlchemy()

load_dotenv(find_dotenv('app.env'), override=True)

database = os.getenv("DB_NAME")
user = os.getenv("DB_USER")
password = os.getenv("DB_PASSWORD")
host = os.getenv("DB_HOST")
port = os.getenv("DB_PORT")

db_url = "postgresql://" + user + ":" + password + "@" + host + ":" + port + "/" + database
