import uuid
import json
import ast
from database import db


class Test(db.Model):
    __tablename__ = 'test'
    # add fields for functionlog
    # create autogenreated primary key as UUID for functionlog
    id = db.Column(db.String(255), primary_key=True, default=str(uuid.uuid4()), unique=True)
    name = db.Column(db.String(255))
    description = db.Column(db.Text)
    goal = db.Column(db.Text)
    instructions = db.Column(db.Text)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    modified_at = db.Column(db.DateTime, server_default=db.func.now(), server_onupdate=db.func.now())
    status = db.Column(db.String(255))
    playwright_instructions = db.Column(db.Text, default=None)
    #selectors = db.Column(db.Text, default=None)  # Store selectors as JSON
    last_run = db.Column(db.DateTime, default=None)
    last_run_status = db.Column(db.String(32), default=None)
    last_run_mode = db.Column(db.String(16), default=None)
    # add a test suite id as a foreign key
    suite_id = db.Column(db.String(255), db.ForeignKey('suite.suite_id'))
    suite = db.relationship('Suite', back_populates='tests')
    custom_test_id = db.Column(db.String(255), nullable=True)

    # add a field for has_test_data
    has_test_data = db.Column(db.Boolean, default=False)
    file_id = db.Column(db.String(255), db.ForeignKey('file.file_id'))
    file = db.relationship('File', back_populates='tests')
    tags = db.Column(db.Text)  # Tags stored as JSON string like ['tag1', 'tag2', 'tag3']
    
    def __repr__(self):
        return '<Test {}>'.format(self.id)

    def _safe_parse(self, raw):
        """Parse JSON or Python dict string safely."""
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            try:
                return ast.literal_eval(raw)
            except Exception:
                return None

    def _stringify_keys(self, data):
        """Convert all dict keys to strings recursively."""
        if isinstance(data, dict):
            return {str(k): self._stringify_keys(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._stringify_keys(i) for i in data]
        return data

    def serialize(self):
        # Parse instructions
        parsed_instructions = self._safe_parse(self.instructions)
        if parsed_instructions is None:
            parsed_instructions = []

        # Convert 'id' int value to string
        for idx, instruction in enumerate(parsed_instructions):
            if isinstance(instruction, dict) and 'id' in instruction:          # convert id to string if it is int
                instruction['id'] = str(instruction['id'])
            elif isinstance(instruction, dict) and 'id' not in instruction:    # if id is not in instruction, add it
                instruction['id'] = str(idx)

        # Parse playwright instructions
        parsed_playwright = self._safe_parse(self.playwright_instructions)
        if parsed_playwright is None:
            parsed_playwright = {}

        parsed_playwright = self._stringify_keys(parsed_playwright)
        playwright_str = json.dumps(parsed_playwright)

        test_data = {
            'id': self.id,
            'custom_test_id': self.custom_test_id,
            'name': self.name,
            'description': self.description,
            'goal': self.goal,
            'instructions': parsed_instructions,
            'suite_id': self.suite_id,
            'created_at': self.created_at,
            'modified_at': self.modified_at,
            'status': self.status,
            'playwright_instructions': playwright_str,
            'last_run': self.last_run,
            'last_run_status': self.last_run_status,
            'last_run_mode': self.last_run_mode,
            'has_test_data': self.has_test_data,
            'file_id': self.file_id,
            'tags': json.loads(self.tags) if self.tags else []
        }
        return test_data