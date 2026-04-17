from django.core.management.base import BaseCommand
from users.models import PersonalityQuestion

class Command(BaseCommand):
    help = 'Load personality quiz questions from personality_type_questionare.py'

    def handle(self, *args, **options):
        # Import the questions data (adjust path as needed)
        from users.utils.personality_type_questionare import questions_data
        for idx, q in enumerate(questions_data):
            obj, created = PersonalityQuestion.objects.get_or_create(
                text=q['text'],
                dimension=q['dimension'],
                direction=q['direction'],
                defaults={'order': idx}
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'Added: {q["text"][:50]}'))
            else:
                self.stdout.write(f'Already exists: {q["text"][:50]}')