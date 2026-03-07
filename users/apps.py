from django.apps import AppConfig


class UsersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "users"
    def ready(self):
        import users.signals.user   # noqa
        import users.signals.login_session
        import users.signals.otp_request      # <-- add this
        import users.signals.login_checkpoint  # <-- add this
