"""
Authorization manager implementation
"""

class AuthorizationManager:
    """Handles user authorization for sensitive operations"""
    @staticmethod
    def request_authorization(layer_name: str, action_description: str) -> bool:
        """Request user authorization for an action"""
        print(f"\n[Authorization Request]")
        print(f"Layer: {layer_name}")
        print(f"Action: {action_description}")
        print("Do you authorize this action? (yes/no): ", end="")
        response = input().strip().lower()
        return response == "yes"
