from django.apps import AppConfig




class FeedConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "feed"
    
    def ready(self):
        import feed.signals.post   # noqa
        from feed.tasks.reel import delete_corrupted_reels
        # Dry run muna
        result = delete_corrupted_reels.dry_run = True
        print(result)

        # Actual deletion
        delete_corrupted_reels.delay()   # kung Celery
        # o synchronous:
        delete_corrupted_reels(soft_delete=True, dry_run=False)
