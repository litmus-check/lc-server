import uuid
import json
from database import db
from utils.utils_constants import ELEMENT_DESCRIPTION_MAX_LENGTH


class Element(db.Model):
    __tablename__ = 'element'

    id = db.Column(db.String(255), primary_key=True, default=lambda: str(uuid.uuid4()))
    element_id = db.Column(db.String(255), index=True)
    suite_id = db.Column(db.String(255), db.ForeignKey('suite.suite_id', ondelete='CASCADE'), nullable=False)
    element_description = db.Column(db.String(ELEMENT_DESCRIPTION_MAX_LENGTH))
    element_prompt = db.Column(db.String(255))
    store_name = db.Column(db.String(255), nullable=True)
    selectors = db.Column(db.Text)  # Stored as JSON string
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    modified_at = db.Column(db.DateTime, server_default=db.func.now(), server_onupdate=db.func.now())

    # Create suite relationship
    suite = db.relationship('Suite')

    def __repr__(self):
        return f'<Element {self.element_id}>'

    def serialize(self):
        return {
            'element_id': self.element_id,
            'suite_id': self.suite_id,
            'element_description': self.element_description,
            'element_prompt': self.element_prompt,
            'store_name': self.store_name,
            'selectors': json.loads(self.selectors) if self.selectors else [],
            'created_at': self.created_at,
            'modified_at': self.modified_at,
        }


