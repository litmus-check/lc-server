import uuid
import json
from database import db


class HealingSuggestion(db.Model):
    __tablename__ = 'healing_suggestions'

    id = db.Column(db.String(255), primary_key=True, default=lambda: str(uuid.uuid4()), unique=True)
    suite_id = db.Column(db.String(255), db.ForeignKey('suite.suite_id', ondelete='CASCADE'), nullable=False)
    suite_run_id = db.Column(db.String(255), nullable=False)
    test_id = db.Column(db.String(255), db.ForeignKey('test.id', ondelete='CASCADE'), nullable=False)
    failed_test_run_id = db.Column(db.String(255), nullable=False)
    triage_result = db.Column(db.Text)  # Stored as JSON string
    updated_test = db.Column(db.Text)  # Stored as JSON string (Complete new test object after user accepted the suggestion)
    reasoning = db.Column(db.Text)  # Reasoning from the agent on why the healing is accurate
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    status = db.Column(db.String(32))  # Status of the healing suggestion
    current_test = db.Column(db.Text)  # JSON format (Current test object before the healing)
    suggested_test = db.Column(db.Text)  # JSON format (Suggested test object)

    # Create relationships
    suite = db.relationship('Suite')
    test = db.relationship('Test')

    def __repr__(self):
        return f'<HealingSuggestion {self.id}>'

    def serialize(self):
        return {
            'id': self.id,
            'suite_id': self.suite_id,
            'suite_run_id': self.suite_run_id,
            'test_id': self.test_id,
            'failed_test_run_id': self.failed_test_run_id,
            'triage_result': json.loads(self.triage_result) if self.triage_result else None,
            'updated_test': json.loads(self.updated_test) if self.updated_test else None,
            'reasoning': self.reasoning,
            'created_at': self.created_at,
            'status': self.status,
            'current_test': json.loads(self.current_test) if self.current_test else None,
            'suggested_test': json.loads(self.suggested_test) if self.suggested_test else None
        }

