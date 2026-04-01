from database import db
import uuid


class CliActivity(db.Model):
    __tablename__ = 'cli_activity'
    
    id = db.Column(db.String(255), primary_key=True, default=lambda: str(uuid.uuid4()), unique=True)
    org_id = db.Column(db.String(255), nullable=False, index=True)
    apikey_name = db.Column(db.String(255), nullable=False, index=True)
    triage_calls = db.Column(db.Integer, nullable=False, default=0)
    created_date = db.Column(db.DateTime, server_default=db.func.now())
    modified_date = db.Column(db.DateTime, server_default=db.func.now(), server_onupdate=db.func.now())
    
    # Create a unique constraint on org_id and apikey_name combination
    __table_args__ = (db.UniqueConstraint('org_id', 'apikey_name', name='_org_apikey_uc'),)
    
    def __repr__(self):
        return f'<CliActivity org_id={self.org_id} apikey_name={self.apikey_name} triage_calls={self.triage_calls}>'
    
    def serialize(self):
        return {
            'id': self.id,
            'org_id': self.org_id,
            'apikey_name': self.apikey_name,
            'triage_calls': self.triage_calls,
            'created_date': self.created_date.isoformat() if self.created_date else None,
            'modified_date': self.modified_date.isoformat() if self.modified_date else None
        }

