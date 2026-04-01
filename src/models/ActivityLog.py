from database import db
from datetime import datetime, timezone

class ActivityLog(db.Model):
    __tablename__ = 'activity_log'
    
    log_id = db.Column(db.String(255), primary_key=True)  # unique id for the activity log
    reference_id = db.Column(db.String(255), nullable=True)  # testrun_id or compose_id
    mode = db.Column(db.String(255), nullable=False)  # script or compose
    environment = db.Column(db.String(255), nullable=False)  # litmus_cloud or browserbase
    trigger = db.Column(db.String(255), nullable=False)  # manual or scheduled
    start_date = db.Column(db.DateTime(timezone=True))
    end_date = db.Column(db.DateTime(timezone=True), nullable=True)
    executed_seconds = db.Column(db.Integer, nullable=True, default=0)
    ai_credits = db.Column(db.Float, nullable=True, default=0.0)  # AI credits consumed
    user_id = db.Column(db.String(255), nullable=True)
    org_id = db.Column(db.String(255), nullable=False)
    
    def __repr__(self):
        return '<ActivityLog {}>'.format(self.log_id)
    
    def serialize(self):
        return {
            'log_id': self.log_id,
            'reference_id': self.reference_id,
            'mode': self.mode,
            'environment': self.environment,
            'trigger': self.trigger,
            'start_date': self.start_date,
            'end_date': self.end_date,
            'executed_seconds': self.executed_seconds,
            'ai_credits': self.ai_credits,
            'user_id': self.user_id,
            'org_id': self.org_id
        } 