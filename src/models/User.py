import uuid
from database import db


class User(db.Model):
    __tablename__ = "user"

    user_id = db.Column(
        db.String(255),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        unique=True,
    )
    email = db.Column(db.String(255), nullable=False, unique=True, index=True)
    password_hash = db.Column(db.Text, nullable=False)
    org_id = db.Column(db.String(255), nullable=False, default="default-org")
    role = db.Column(db.String(50), nullable=False, default="user")
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(
        db.DateTime,
        server_default=db.func.now(),
        server_onupdate=db.func.now(),
    )

    def serialize(self):
        return {
            "user_id": self.user_id,
            "email": self.email,
            "org_id": self.org_id,
            "role": self.role,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

