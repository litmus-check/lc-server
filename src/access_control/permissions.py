import traceback
from log_config.logger import logger
from access_control.roles import ROLES, ADMIN, USER


def has_action_permission(current_user: dict, operation: str) -> tuple[str, int]:
    """
    Check if the user has the required permissions for an operation.
    Args:
        current_user (dict): The current user details containing role information
        operation (str): The operation to check permissions for (e.g., "suite:get")
    Returns:
        tuple[str, int]: (result, status_code)
            - result: Message if user has permission, Error message otherwise
            - status_code: 200 if successful, 403 if forbidden, 500 if error
    """
    try:
        logger.info(f"Checking permission for operation: {operation}")
        logger.info(f"Current user: {current_user}")
        role = current_user.get("role")
        if not role:
            logger.warning("User does not have a role assigned")
            return "User does not have a role assigned", 403
        
        if role not in ROLES:
            logger.warning(f"User has invalid role: {role}")
            return "User has invalid role", 403
        
        role_config = ROLES[role]

        # TODO: Bypass admin, user roles check for now
        if role in [ADMIN, USER]:
            return "User has permission", 200
        
        # Check if role has explicit permissions (for roles like viewer)
        if role_config.get("permissions"):
            has_permission = operation in role_config["permissions"]
            if not has_permission:
                logger.info(f"Permission denied for role '{role}' and operation '{operation}' - operation not in permissions list")
                return f"Permission denied - operation not allowed for this role", 401
        
        # If operation is not in permissions, return permission denied
        logger.info(f"Permission granted for role '{role}' and operation '{operation}'")
        return "User has permission", 200
        
    except Exception as e:
        logger.error(f"Error in has_action_permission: {e}")
        logger.debug(traceback.format_exc())
        return "Internal server error", 500
