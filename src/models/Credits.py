import uuid
from datetime import datetime, timedelta, timezone
from database import db
from utils.utils_constants import DEFAULT_BROWSER_MINUTES, DEFAULT_AI_CREDITS
from dateutil.relativedelta import relativedelta

class Credits(db.Model):
    __tablename__ = 'credits'
    
    org_id = db.Column(db.String(255), primary_key=True, unique=True)
    browser_credits = db.Column(db.Integer, nullable=False, default=DEFAULT_BROWSER_MINUTES)  # seconds
    ai_credits = db.Column(db.Float, nullable=False, default=DEFAULT_AI_CREDITS)  # AI credits
    start_date = db.Column(db.DateTime(timezone=True), nullable=True, default=datetime.now(timezone.utc))
    modified_date = db.Column(db.DateTime(timezone=True), nullable=True)
    last_reset_date = db.Column(db.DateTime(timezone=True), nullable=True, default=datetime.now(timezone.utc))  # Database should use UTC
    next_reset_date = db.Column(db.DateTime(timezone=True), nullable=True)
    
    def __init__(self, **kwargs):
        super(Credits, self).__init__(**kwargs)
        # If last_reset_date is None set it to current UTC time
        if self.last_reset_date is None:
            self.last_reset_date = datetime.now(timezone.utc)
            self.next_reset_date = self.calculate_next_reset_date()
    
    def calculate_next_reset_date(self):
        """Calculate next reset date as same date next month"""
        if self.last_reset_date is None:
            return None
        
        """
        Returns the same day of the next month.
        If next month has fewer days, it returns the last valid day.
        """
        try:
            # Add 1 month, keeping day if possible
            next_month = self.last_reset_date + relativedelta(months=1)
            return next_month

        except Exception as e:
            print(f"Error occurred: {e}")
            return None
    
    def __repr__(self):
        return '<Credits {}>'.format(self.org_id)
    
    def serialize(self):
        return {
            'org_id': self.org_id,
            'browser_credits': self.browser_credits,
            'ai_credits': self.ai_credits,
            'start_date': self.start_date,
            'modified_date': self.modified_date,
            'last_reset_date': self.last_reset_date,
            'next_reset_date': self.next_reset_date
        } 