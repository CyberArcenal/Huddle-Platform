# users/management/commands/seed_user_preferences.py

from django.core.management.base import BaseCommand
from users.models import Hobby, Interest, Favorite, Music, Work, School, Achievement, SocialCause, LifestyleTag

class Command(BaseCommand):
    help = 'Seed user preference lookup tables'

    def handle(self, *args, **options):
        # Hobby
        hobbies = ["Photography", "Cooking", "Gaming", "Hiking", "Reading", "Dancing", "Painting", "Cycling", "Traveling", "Gardening", "Fishing", "Swimming", "Writing", "Yoga", "Running", "Karaoke", "Collecting"]
        for name in hobbies:
            Hobby.objects.get_or_create(name=name)

        # Interest
        interests = ["Technology", "Fashion", "Fitness", "Music", "Movies", "Art", "Science", "Politics", "Spirituality", "Business", "Psychology", "Nature", "Cars", "Sports", "Food", "Self-improvement", "Animals"]
        for name in interests:
            Interest.objects.get_or_create(name=name)

        # Favorite
        favorites = ["Pizza", "Sushi", "Inception", "Harry Potter", "The Beatles", "BTS", "Coffee", "Milktea", "Beach", "Mountains", "Cats", "Dogs", "Summer", "Rain", "Minimalist style"]
        for name in favorites:
            Favorite.objects.get_or_create(name=name)

        # Music
        music_genres = ["Pop", "Rock", "Hip-hop", "K-pop", "Jazz", "Classical", "R&B", "EDM", "Indie", "Alternative", "Metal", "Country", "Reggae", "Blues", "Folk", "Punk", "Disco", "Latin", "Ambient", "Soundtrack"]
        for name in music_genres:
            Music.objects.get_or_create(name=name)

        # Work
        works = ["Software Engineer", "Teacher", "Nurse", "Doctor", "Lawyer", "Accountant", "Architect", "Chef", "Pilot", "Artist", "Musician", "Entrepreneur", "Marketing Manager", "Sales", "Student", "Freelancer", "Virtual Assistant", "Business Owner", "Government Employee", "Engineer", "Designer"]
        for name in works:
            Work.objects.get_or_create(name=name)

        # School (top PH and global)
        schools = ["University of the Philippines", "Ateneo de Manila University", "De La Salle University", "University of Santo Tomas", "Far Eastern University", "Mapúa University", "Polytechnic University of the Philippines", "University of San Carlos", "Mindanao State University", "Harvard University", "Stanford University", "University of Cambridge", "University of Oxford", "MIT"]
        for name in schools:
            School.objects.get_or_create(name=name)

        # Achievement
        achievements = ["Dean's Lister", "Cum Laude", "Leadership Award", "Top Performer", "Published Author", "Competition Winner", "Licensed Professional", "Certified Scrum Master", "Community Service Award", "Sports Champion", "Artist of the Year"]
        for name in achievements:
            Achievement.objects.get_or_create(name=name)

        # SocialCause
        causes = ["Climate Action", "Mental Health Awareness", "Education for All", "Animal Welfare", "Gender Equality", "Anti-poverty", "Human Rights", "Disaster Relief", "Indigenous Rights", "LGBTQ+ Support", "Healthcare Access", "Cyberbullying Prevention", "Ocean Conservation", "Feeding Program"]
        for name in causes:
            SocialCause.objects.get_or_create(name=name)

        # LifestyleTag
        tags = ["Early Riser", "Night Owl", "Minimalist", "Fitness Enthusiast", "Foodie", "Coffee Lover", "Tea Drinker", "Adventurer", "Homebody", "Spiritual", "Career-focused", "Family-oriented", "Pet Lover", "Vegan", "Plantita/Plantito", "Gamer", "Bookworm", "Music Lover", "Movie Buff", "Eco-friendly", "Budget Traveler", "Luxury Traveler"]
        for name in tags:
            LifestyleTag.objects.get_or_create(name=name)

        self.stdout.write(self.style.SUCCESS("All user preference lookup tables seeded successfully."))