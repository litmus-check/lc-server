from database import db


class OrgQueueConfig(db.Model):
    __tablename__ = 'org_queue_config'

    org_id = db.Column(db.String(255), primary_key=True, unique=True, nullable=False)
    queue_name = db.Column(db.String(255), nullable=False)
    rate_limit = db.Column(db.Integer, nullable=False)
    suppress_suite_slack_messages = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.now())
    modified_at = db.Column(db.DateTime, default=db.func.now(), onupdate=db.func.now())
    

    def __repr__(self):
        return f"<QueueConfig org_id={self.org_id} queue_name={self.queue_name}>"

    def serialize(self):
        return {
            'org_id': self.org_id,
            'queue_name': self.queue_name,
            'rate_limit': self.rate_limit,
            'suppress_suite_slack_messages': self.suppress_suite_slack_messages,
            'created_at': self.created_at,
            'modified_at': self.modified_at
        }


