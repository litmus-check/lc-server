import uuid
from database import db
from sqlalchemy.orm import relationship
from utils.utils_constants import DEFAULT_FILE_TYPE

class File(db.Model):
    __tablename__ = 'file'
    
    file_id = db.Column(db.String(255), primary_key=True, default=str(uuid.uuid4()), unique=True)
    file_name = db.Column(db.String(255), nullable=False)
    file_url = db.Column(db.String(255), nullable=False)
    type = db.Column(db.String(255), nullable=False, default=DEFAULT_FILE_TYPE)
    suite_id = db.Column(db.String(255), db.ForeignKey('suite.suite_id'), nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    modified_at = db.Column(db.DateTime, server_default=db.func.now(), server_onupdate=db.func.now())
    user_id = db.Column(db.String(255), nullable=True)
    
    # Relationship with Suite
    suite = relationship('Suite', backref='files')
    
    # Relationship with Test
    tests = relationship('Test', back_populates='file')
    
    def __repr__(self):
        return f'<File {self.file_name}>'
    
    def serialize(self):
        return {
            'file_id': self.file_id,
            'file_name': self.file_name,
            'file_url': self.file_url,
            'type': self.type,
            'suite_id': self.suite_id,
            'created_at': self.created_at,
            'modified_at': self.modified_at,
            'user_id': self.user_id
        } 