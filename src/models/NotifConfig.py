# Notification configuration model for storing email notification settings

from sqlalchemy import Column, String, DateTime
from database import db
import uuid

class NotifConfig(db.Model):
    __tablename__ = 'notif_config'

    id = Column(String, primary_key=True, default=str(uuid.uuid4()))
    suite_id = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=db.func.now())
    modified_at = Column(DateTime, server_default=db.func.now(), server_onupdate=db.func.now())
    channel = Column(String, nullable=False)
    recipients = Column(String, nullable=False)

    def serialize(self):
        return {
            'id': self.id,
            'suite_id': self.suite_id,
            'channel': self.channel,
            'recipients': self.recipients,
            'created_at': self.created_at,
            'modified_at': self.modified_at
        }
        
