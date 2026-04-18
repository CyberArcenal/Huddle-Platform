# users/management/commands/load_personality_questions.py

from django.core.management.base import BaseCommand
from users.models import PersonalityQuestion

class Command(BaseCommand):
    help = 'Delete existing personality questions and load new ones from personality_type_questionare.py'

    def handle(self, *args, **options):
        # 1. Delete all existing questions (cascade will remove related responses)
        deleted_count, _ = PersonalityQuestion.objects.all().delete()
        self.stdout.write(self.style.WARNING(f'Deleted {deleted_count} existing questions.'))

        # 2. Import the new questions data
        from users.utils.personality_type_questionare import questions_data

        # 3. Create new questions
        created_count = 0
        for idx, q in enumerate(questions_data):
            obj = PersonalityQuestion.objects.create(
                text=q['text'],
                dimension=q['dimension'],
                direction=q['direction'],
                order=idx,
                is_active=True
            )
            created_count += 1
            self.stdout.write(self.style.SUCCESS(f'Added: {q["text"][:50]}...'))

        self.stdout.write(self.style.SUCCESS(f'\n✅ Successfully loaded {created_count} new personality questions.'))