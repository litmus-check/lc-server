import json
from datetime import datetime
from database import db

class Schedule(db.Model):
    __tablename__ = 'schedules'

    id = db.Column(db.String(36), primary_key=True)
    suite_id = db.Column(db.String(36), nullable=False)
    org_id = db.Column(db.String(255), nullable=False)
    environment_id = db.Column(db.String(255), db.ForeignKey('environment.environment_id'), nullable=True)
    run_every_hours = db.Column(db.Integer, nullable=False)
    start_date_time = db.Column(db.DateTime, nullable=False)
    config = db.Column(db.Text)  # Playwright browser configuration
    tag_filter = db.Column(db.Text)  # Tag filter stored as JSON string
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "schedule_details": {
                "run_every_hours": self.run_every_hours,
                "start_date_time": self.start_date_time.isoformat()
            },
            "config": json.loads(self.config) if self.config else None,
            "environment_id": self.environment_id,
            "tag_filter": json.loads(self.tag_filter) if self.tag_filter else {}
        } 