REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "users.utils.authentications.IsAuthenticatedAndNotBlacklisted",
    ],
    "EXCEPTION_HANDLER": "global_utils.exceptionHandler.custom_exception_handler",
    "DEFAULT_PAGINATION_CLASS": "global_utils.response.CustomPagination",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "PAGE_SIZE": 20,
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Huddle Platform API",
    "DESCRIPTION": "API for the Huddle social media app",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    # ← ITO ANG MAHALAGA
    "COMPONENT_SPLIT_REQUEST": True,  # ← ginagawa nitong hiwalay ang request at response
    # Optional pero recommended para siguradong multipart
    "COMPONENT_SPLIT_PATCH": True,
    "COMPONENT_NO_READ_ONLY_REQUIRED": True,
}
