import uuid
from database import db
from sqlalchemy.orm import relationship


class ElementStore(db.Model):
    __tablename__ = 'element_store'

    store_id = db.Column(db.String(255), primary_key=True, default=lambda: str(uuid.uuid4()), unique=True)
    store_name = db.Column(db.String(255), nullable=False)
    store_description = db.Column(db.String(255))
    suite_id = db.Column(db.String(255), db.ForeignKey('suite.suite_id', ondelete='CASCADE'), nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    modified_at = db.Column(db.DateTime, server_default=db.func.now(), server_onupdate=db.func.now())

    # Create suite relationship
    suite = db.relationship('Suite')

    def __repr__(self):
        return f'<ElementStore {self.store_id}>'

    def serialize(self):
        return {
            'store_id': self.store_id,
            'store_name': self.store_name,
            'store_description': self.store_description,
            'suite_id': self.suite_id,
            'created_at': self.created_at,
            'modified_at': self.modified_at,
        }


