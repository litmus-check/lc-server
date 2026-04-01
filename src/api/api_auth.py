import datetime
import os

import jwt
from flask import Blueprint, jsonify, request
from werkzeug.security import check_password_hash, generate_password_hash

from log_config.logger import logger
from access_control.roles import USER
from database import db
from models.User import User
from security.auth import token_required


api_auth = Blueprint("api_auth", __name__, url_prefix="/api/v1")


def _build_access_token_for_user(user: User) -> str:
    secret = os.getenv("JWT_SECRET_KEY")
    if not secret:
        raise ValueError("JWT_SECRET_KEY is not configured")

    expiry_hours = int(os.getenv("JWT_EXPIRY_HOURS", "24"))
    now = datetime.datetime.now(datetime.timezone.utc)

    payload = {
        "email": user.email,
        "user_id": user.user_id,
        "org_id": user.org_id,
        "role": user.role,
        "iat": now,
        "exp": now + datetime.timedelta(hours=expiry_hours),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


@api_auth.route("/signup", methods=["POST"])
def signup():
    try:
        body = request.get_json(silent=True) or {}
        email = body.get("email")
        password = body.get("password")

        if not email or not password:
            return jsonify({"error": "email and password are required"}), 400

        if len(password) < 8:
            return jsonify({"error": "password must be at least 8 characters"}), 400

        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            return jsonify({"error": "User already exists"}), 409

        default_org_id = os.getenv("DEFAULT_ORG_ID", "default-org")
        default_role = os.getenv("DEFAULT_USER_ROLE", USER)

        user = User(
            email=email,
            password_hash=generate_password_hash(password),
            org_id=default_org_id,
            role=default_role,
        )
        db.session.add(user)
        db.session.commit()

        access_token = _build_access_token_for_user(user)
        return jsonify({"accessToken": access_token}), 201
    except Exception as exc:
        db.session.rollback()
        logger.error(f"Error in signup endpoint: {exc}")
        return jsonify({"error": "Internal server error"}), 500


@api_auth.route("/login", methods=["POST"])
def login():
    try:
        body = request.get_json(silent=True) or {}
        email = body.get("email")
        password = body.get("password")

        if not email or not password:
            return jsonify({"error": "email and password are required"}), 400

        user = User.query.filter_by(email=email).first()
        if not user or not check_password_hash(user.password_hash, password):
            return jsonify({"error": "Invalid credentials"}), 401

        access_token = _build_access_token_for_user(user)
        return jsonify({"accessToken": access_token}), 200
    except Exception as exc:
        logger.error(f"Error in login endpoint: {exc}")
        return jsonify({"error": "Internal server error"}), 500


@api_auth.route("/user", methods=["GET"])
@token_required()
def get_current_user(current_user):
    return jsonify(current_user), 200

