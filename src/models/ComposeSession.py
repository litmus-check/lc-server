from datetime import datetime
from database import db
import uuid
import json
from utils.utils_constants import DEFAULT_PLAYWRIGHT_CONFIG

class ComposeSession(db.Model):
    __tablename__ = 'compose_session'

    compose_id = db.Column(db.String(255), primary_key=True, default=str(uuid.uuid4()), unique=True)
    start_date = db.Column(db.DateTime, default=db.func.now())
    end_date = db.Column(db.DateTime)
    status = db.Column(db.String(32), default='running')  # running, success, failed, completed
    browserbase_session_id = db.Column(db.String(255), nullable=True)
    test_id = db.Column(db.String(255), db.ForeignKey('test.id'), nullable=True)
    config = db.Column(db.Text, default=json.dumps(DEFAULT_PLAYWRIGHT_CONFIG))  # Playwright browser configuration
    user_id = db.Column(db.String(255), nullable=False)
    environment = db.Column(db.String(32), nullable=True)
    environment_variables = db.Column(db.Text)  # Environment variables stored as JSON string
    source = db.Column(db.String(32), nullable=True)
    agent_type = db.Column(db.String(255), nullable=True)
    agent_args = db.Column(db.Text, nullable=True)
    test = db.relationship('Test', backref=db.backref('compose_sessions', cascade='all, delete-orphan'), lazy=True)

    def __repr__(self):
        return f'<ComposeSession {self.compose_id}>'

    def serialize(self):
        return {
            'compose_id': self.compose_id,
            'start_date': self.start_date,
            'end_date': self.end_date,
            'status': self.status,
            'test_id': self.test_id,
            'browserbase_session_id': self.browserbase_session_id,
            'user_id': self.user_id,
            'environment': self.environment,
            'config': json.loads(self.config) if self.config else DEFAULT_PLAYWRIGHT_CONFIG,
            'environment_variables': json.loads(self.environment_variables) if self.environment_variables else {},
            'source': self.source,
            'agent_type': self.agent_type,
            'agent_args': json.loads(self.agent_args) if self.agent_args else None
        } 