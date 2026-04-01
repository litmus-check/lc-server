import jwt
import os
import traceback
from functools import wraps

from flask import request, jsonify
from dotenv import load_dotenv, find_dotenv


from log_config.logger import logger
from access_control.permissions import has_action_permission
from access_control.roles import USER


load_dotenv(find_dotenv("app.env"))

class AuthError(Exception):
    def __init__(self, error, status_code):
        self.error = error
        self.status_code = status_code

        super().__init__(self.error)

        self.error['status_code'] = self.status_code

        def to_dict(self):
            return self.error

def decode_token(token):
    secret = os.getenv("JWT_SECRET_KEY")
    if not secret:
        raise AuthError({
            "code": "jwt_not_configured",
            "description": "JWT secret is not configured",
        }, 500)

    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        raise AuthError({
            "code": "token_expired",
            "description": "Token is expired",
        }, 401)
    except jwt.InvalidTokenError:
        raise AuthError({
            "code": "invalid_token",
            "description": "Token is invalid",
        }, 401)


def _build_user_details_from_payload(payload):
    return {
        "org_id": payload.get("org_id", os.getenv("DEFAULT_ORG_ID", "default-org")),
        "role": payload.get("role", USER),
        "email": payload.get("email"),
        "user_id": payload.get("user_id", payload.get("email")),
    }

def token_required(operation=None):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            try:
                if 'Authorization' in request.headers:
                    token = request.headers.get('Authorization')
                    token = token.split(' ')[1]
                    if not token:
                        return jsonify({'message': 'Token is missing!'}), 401

                    payload = decode_token(token)
                    user_details = _build_user_details_from_payload(payload)
                else:
                    return jsonify({'message': 'Token is missing!'}), 401    
                
                # Check permissions if operation is specified
                if operation:
                    permission_result, status_code = has_action_permission(user_details, operation)
                    if status_code != 200:
                        return jsonify({'message': permission_result}), status_code
                
            except Exception as e:
                # print traceback
                logger.error(e)
                logger.debug(traceback.format_exc())
                return jsonify({'message': 'Invalid Token!'}), 401
            return f(user_details, *args, **kwargs)
        return decorated
    return decorator

def get_user_details(token):
    try:
        payload = decode_token(token)
        return _build_user_details_from_payload(payload)
    except Exception as e:
        logger.error(f"Error in get_user_details {e}")
        logger.debug(traceback.format_exc())
        return None