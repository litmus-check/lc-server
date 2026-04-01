# create a test suite model which has a many to many relationship with the test model

from sqlalchemy import Column, Integer, String, Table, ForeignKey, func, select
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import relationship
from database import db
from .Test import Test
import uuid
import json
from utils.utils_constants import DEFAULT_PLAYWRIGHT_CONFIG

class Suite(db.Model):
    __tablename__ = 'suite'

    suite_id = db.Column(db.String(255), primary_key=True, default=str(uuid.uuid4()), unique=True)
    org_id = Column(String, nullable=False)
    created_at = Column(db.DateTime, default=db.func.now())
    modified_at = Column(db.DateTime, server_default=db.func.now(), server_onupdate=db.func.now())
    name = Column(String, nullable=False)
    description = Column(String, nullable=False)
    sign_in_url = Column(String, nullable=False)
    username = Column(String, nullable=False)
    password = Column(String, nullable=False)
    config = Column(db.Text, default=json.dumps(DEFAULT_PLAYWRIGHT_CONFIG))  # Playwright browser configuration
    master_tags = db.Column(db.Text)  # Master tags stored as JSON string - master set of all tags from all tests in the suite
    heal_test = db.Column(db.Boolean, default=False)
    triage = db.Column(db.Boolean, default=True)
    # add a one to many relationship with the test model
    tests = relationship('Test', back_populates='suite', cascade="all, delete-orphan")
    # create a hybrid property that keeps track of the number of tests in the suite
    @hybrid_property
    def total_tests(self):
        return len(self.tests)

    @total_tests.expression
    def total_tests(cls):
        return select(func.count()).select_from(Test).where(Test.suite_id == cls.suite_id).label('total_tests')

    def __repr__(self):
        return f'<Suite {self.name}>'

    def serialize(self):
        return {
            'suite_id': self.suite_id,
            'name': self.name,
            'description': self.description,
            'sign_in_url': self.sign_in_url,
            'username': self.username,
            'password': self.password,
            'config': json.loads(self.config) if self.config else DEFAULT_PLAYWRIGHT_CONFIG,
            'created_at': self.created_at,
            'modified_at': self.modified_at,
            'tests': [test.serialize() for test in self.tests],
            'total_tests': self.total_tests,
            'org_id': self.org_id,
            'master_tags': json.loads(self.master_tags) if self.master_tags else [],
            'heal_test': self.heal_test,
            'triage': self.triage
        }
