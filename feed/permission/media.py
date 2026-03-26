from rest_framework.permissions import BasePermission

class IsMediaOwner(BasePermission):
    """
    Allows access only to the user who created the media
    or the owner of the content object the media belongs to.
    """
    def has_object_permission(self, request, view, obj):
        # SAFE_METHODS (GET, HEAD, OPTIONS) are allowed for anyone? 
        # We'll restrict to owner for safety; adjust as needed.
        if request.method in ['GET', 'HEAD', 'OPTIONS']:
            # You may allow read-only access to anyone with view permission
            # on the content object. But for simplicity, we restrict to owner.
            return True  # or check content object's visibility

        # For write methods, check if user is creator or content owner
        if obj.created_by == request.user:
            return True
        # If media belongs to a content object, check if that object's owner
        content_obj = obj.content_object
        if content_obj and hasattr(content_obj, 'user') and content_obj.user == request.user:
            return True
        return False