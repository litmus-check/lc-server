from flask_sqlalchemy import SQLAlchemy
from database import db
import uuid
import json
from utils.utils_constants import DEFAULT_PLAYWRIGHT_CONFIG

class SuiteRun(db.Model):
    __tablename__ = 'suite_run'
    
    suite_run_id = db.Column(db.String(255), primary_key=True, default=str(uuid.uuid4()), unique=True)
    suite_id = db.Column(db.String(255))
    created_date = db.Column(db.DateTime, default=db.func.now())
    start_date = db.Column(db.DateTime)
    end_date = db.Column(db.DateTime)
    success_count = db.Column(db.Integer, default=0)
    failure_count = db.Column(db.Integer, default=0)
    skipped_count = db.Column(db.Integer, default=0)
    error_count = db.Column(db.Integer, default=0)
    total_tests = db.Column(db.Integer, default=0)
    triage_count = db.Column(db.Integer, default=0)
    config = db.Column(db.Text, default=json.dumps(DEFAULT_PLAYWRIGHT_CONFIG))  # Playwright browser configuration
    error_messages = db.Column(db.Text, default=json.dumps({}))
    status = db.Column(db.String(32))
    environment_variables = db.Column(db.Text)  # Environment variables stored as JSON string
    environment_name = db.Column(db.String(255))
    triage_status = db.Column(db.String(32))
    triage_result = db.Column(db.Text)
    tag_filter = db.Column(db.Text)  # Tag filter stored as JSON string

    def __repr__(self):
        return f'<SuiteRun {self.suite_run_id}>'

    def serialize(self):
        return {
            'suite_run_id': self.suite_run_id,
            'suite_id': self.suite_id,
            'created_date': self.created_date,
            'start_date': self.start_date,
            'end_date': self.end_date,
            'success_count': self.success_count,
            'skipped_count': self.skipped_count,
            'failure_count': self.failure_count,
            'total_tests': self.total_tests,
            'error_count': self.error_count,
            'triage_count': self.triage_count,
            'config': json.loads(self.config) if self.config else DEFAULT_PLAYWRIGHT_CONFIG,
            'status': self.status,
            'error_messages': json.loads(self.error_messages) if self.error_messages else {},
            'environment_variables': json.loads(self.environment_variables) if self.environment_variables else {},
            'environment_name': self.environment_name,
            'triage_status': self.triage_status,
            'triage_result': json.loads(self.triage_result) if self.triage_result else [],
            'tag_filter': json.loads(self.tag_filter) if self.tag_filter else {}
        }

