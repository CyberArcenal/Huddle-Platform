# users/apps.py

from django.apps import AppConfig
from django.db.models.signals import post_migrate



class UsersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "users"

    def ready(self):
        import users.signals.user
        import users.signals.login_session
        import users.signals.otp_request
        import users.signals.login_checkpoint

        # Connect post_migrate signal to our seeder
        post_migrate.connect(seed_on_migration, sender=self)

def seed_on_migration(sender, **kwargs):
    """Only seed if tables are empty (first run)."""
    from users.models import PersonalityQuestion, Hobby
    # Avoid re-seeding if data already exists
    if PersonalityQuestion.objects.exists() or Hobby.objects.exists():
        return
    from users.management.commands.seeds import seed_all_predefined_data
    seed_all_predefined_data()