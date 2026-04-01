import uuid
from database import db


class TestSegment(db.Model):
    __tablename__ = 'test_segment'

    segment_id = db.Column(db.String(255), primary_key=True, default=str(uuid.uuid4()), unique=True)
    segment_name = db.Column(db.String(255), nullable=False)
    test_id = db.Column(db.String(255), db.ForeignKey('test.id'), nullable=False)
    suite_id = db.Column(db.String(255), db.ForeignKey('suite.suite_id'), nullable=False)
    start_instruction_id = db.Column(db.String(255), nullable=False)
    end_instruction_id = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    modified_at = db.Column(db.DateTime, server_default=db.func.now(), server_onupdate=db.func.now())

    # Optional relationships for convenience
    test = db.relationship('Test', backref=db.backref('segments', cascade='all, delete-orphan'), lazy=True)
    suite = db.relationship('Suite', backref=db.backref('segments', cascade='all, delete-orphan'), lazy=True)

    def __repr__(self):
        return '<TestSegment {}>'.format(self.segment_id)

    def serialize(self):
        return {
            'segment_id': self.segment_id,
            'segment_name': self.segment_name,
            'test_id': self.test_id,
            'suite_id': self.suite_id,
            'start_instruction_id': self.start_instruction_id,
            'end_instruction_id': self.end_instruction_id,
            'created_at': self.created_at,
            'modified_at': self.modified_at
        }


