import uuid
import json
from database import db
from sqlalchemy import Column, String, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship


class Environment(db.Model):
    __tablename__ = 'environment'

    environment_id = db.Column(db.String(255), primary_key=True, default=str(uuid.uuid4()), unique=True)
    environment_name = db.Column(db.String(255), nullable=False)
    suite_id = db.Column(db.String(255), db.ForeignKey('suite.suite_id', ondelete='CASCADE'), nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    modified_at = db.Column(db.DateTime, server_default=db.func.now(), server_onupdate=db.func.now())
    variables = db.Column(db.Text)  # Variables stored in key-value pair as JSON string
    
    # Relationship with Suite
    suite = relationship('Suite')

    def __repr__(self):
        return f'<Environment {self.environment_name}>'

    def serialize(self):
        return {
            'environment_id': self.environment_id,
            'environment_name': self.environment_name,
            'suite_id': self.suite_id,
            'created_at': self.created_at,
            'modified_at': self.modified_at,
            'variables': json.loads(self.variables) if self.variables else {}
        }
