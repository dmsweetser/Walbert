"""
Authorization manager implementation
"""

import logging


class AuthorizationManager:
    """Handles user authorization for sensitive operations"""
    def __init__(self):
        self.logger = logging.getLogger('walbert.authorization')

    def request_authorization(self, layer_name: str, action_description: str) -> bool:
        """Request user authorization for an action with enhanced logging"""
        self.logger.info(f"Authorization request - Layer: {layer_name}, Action: {action_description}")
        print(f"\n[Authorization Request]")
        print(f"Layer: {layer_name}")
        print(f"Action: {action_description}")
        print("Do you authorize this action? (yes/no): ", end="")

        try:
            response = input().strip().lower()
            authorized = response == "yes"
            self.logger.info(f"Authorization {'granted' if authorized else 'denied'} for {layer_name}")
            return authorized
        except Exception as e:
            self.logger.error(f"Authorization input error: {e}")
            return False
