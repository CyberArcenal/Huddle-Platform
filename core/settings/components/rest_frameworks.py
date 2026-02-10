REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "accounts.authentications.IsAuthenticatedAndNotBlacklisted",
    ],
    "EXCEPTION_HANDLER": "global_utils.exceptionHandler.custom_exception_handler",
    "DEFAULT_PAGINATION_CLASS": "global_utils.response.CustomPagination",
    "PAGE_SIZE": 20,
}
