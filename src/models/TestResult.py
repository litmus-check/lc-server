import json
from flask_sqlalchemy import SQLAlchemy
from database import db
import uuid
from utils.utils_constants import DEFAULT_PLAYWRIGHT_CONFIG

class TestResult(db.Model):
    __tablename__ = 'test_result'
    
    testrun_id = db.Column(db.String(255), primary_key=True, default=str(uuid.uuid4()), unique=True)
    test_id = db.Column(db.String(255), db.ForeignKey('test.id'), nullable=False)
    suite_run_id = db.Column(db.String(255), nullable=True)
    test = db.relationship('Test', backref=db.backref('test_result', cascade='all, delete-orphan'), lazy=True)
    output = db.Column(db.Text)
    status = db.Column(db.String(32))
    created_date = db.Column(db.DateTime, default=db.func.current_timestamp())
    start_date = db.Column(db.DateTime)
    end_date = db.Column(db.DateTime)
    gif_url = db.Column(db.String(255))
    trace_url = db.Column(db.String(255))
    mode = db.Column(db.String(16))
    config = db.Column(db.Text, default=json.dumps(DEFAULT_PLAYWRIGHT_CONFIG))  # Playwright browser configuration
    retries = db.Column(db.Integer, default=0)
    logs = db.Column(db.Text)
    data_row_index = db.Column(db.Integer)
    environment_variables = db.Column(db.Text)  # Environment variables stored as JSON string
    environment_name = db.Column(db.String(255), default='Custom env variables')

    
    def __repr__(self):
        return '<TestResult {}>'.format(self.testrun_id)
    
    def serialize(self):
        testrun_data = {
            'testrun_id': self.testrun_id,
            'test_id': self.test_id,
            'suite_run_id': self.suite_run_id,
            'output': self.output,
            'status': self.status,
            'created_date': self.created_date,
            'start_date': self.start_date,
            'end_date': self.end_date,
            'gif_url': self.gif_url,
            'trace_url': self.trace_url,
            'mode': self.mode,
            'config': json.loads(self.config) if self.config else DEFAULT_PLAYWRIGHT_CONFIG,
            'retries': self.retries,
            'logs': json.loads(self.logs) if self.logs else None,
            'data_row_index': self.data_row_index,
            'environment_variables': json.loads(self.environment_variables) if self.environment_variables else {}
        }
        return testrun_data