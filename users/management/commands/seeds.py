# users/seeds.py

from users.models import (
    PersonalityQuestion,
    Hobby, Interest, Favorite, Music,
    SocialCause, LifestyleTag, Achievement,
    Work, School
)
from users.utils.personality_type_questionare import questions_data

# -------------------------------
# Seed data for static lookup tables
# -------------------------------

HOBBY_DATA = [
    "Reading", "Gaming", "Hiking", "Photography", "Cooking",
    "Painting", "Dancing", "Singing", "Gardening", "Fishing",
    "Yoga", "Meditation", "Running", "Cycling", "Swimming"
]

INTEREST_DATA = [
    "Technology", "Science", "Art", "History", "Politics",
    "Fashion", "Travel", "Food", "Sports", "Music",
    "Movies", "Books", "Business", "Psychology", "Education"
]

FAVORITE_DATA = [
    "Coffee", "Pizza", "Sushi", "Beach", "Mountains",
    "Summer", "Winter", "Cats", "Dogs", "Jazz",
    "Rock Music", "Science Fiction", "Fantasy", "Comedy", "Action Movies"
]

MUSIC_DATA = [
    "Pop", "Rock", "Hip Hop", "Jazz", "Classical",
    "Electronic", "Country", "Reggae", "Blues", "Metal",
    "R&B", "Soul", "Funk", "Punk", "Indie"
]

SOCIAL_CAUSE_DATA = [
    "Climate Change", "Education for All", "Animal Welfare",
    "Mental Health Awareness", "Human Rights", "Poverty Alleviation",
    "Gender Equality", "Clean Water", "Renewable Energy",
    "Anti-Racism", "LGBTQ+ Rights", "Disaster Relief"
]

LIFESTYLE_TAG_DATA = [
    "Minimalist", "Vegan", "Fitness Enthusiast", "Night Owl",
    "Early Riser", "Remote Worker", "Digital Nomad", "Pet Lover",
    "Plant Parent", "Bookworm", "Adventurer", "Foodie"
]

ACHIEVEMENT_DATA = [
    "Graduated College", "Ran a Marathon", "Published Author",
    "Started a Business", "Learned a Language", "Volunteer Award",
    "Coding Bootcamp", "Art Exhibition", "Music Album", "Charity Fundraiser"
]

WORK_DATA = [
    "Software Engineer", "Doctor", "Teacher", "Artist", "Entrepreneur",
    "Nurse", "Lawyer", "Chef", "Designer", "Writer",
    "Scientist", "Accountant", "Architect", "Musician", "Photographer"
]

SCHOOL_DATA = [
    "Computer Science", "Medicine", "Business Administration",
    "Fine Arts", "Engineering", "Psychology", "Law",
    "Education", "Nursing", "Biology", "Chemistry", "Physics"
]


def seed_personality_questions():
    """Load MBTI questions from the existing data file."""
    for idx, q in enumerate(questions_data):
        PersonalityQuestion.objects.get_or_create(
            text=q['text'],
            dimension=q['dimension'],
            direction=q['direction'],
            defaults={'order': idx}
        )

def seed_lookup_model(model, data_list, name_field='name'):
    """Generic seeder for models that only have a name field."""
    for name in data_list:
        model.objects.get_or_create(**{name_field: name})

def seed_all_predefined_data():
    """Call this function to seed everything."""
    seed_personality_questions()
    seed_lookup_model(Hobby, HOBBY_DATA)
    seed_lookup_model(Interest, INTEREST_DATA)
    seed_lookup_model(Favorite, FAVORITE_DATA)
    seed_lookup_model(Music, MUSIC_DATA)
    seed_lookup_model(SocialCause, SOCIAL_CAUSE_DATA)
    seed_lookup_model(LifestyleTag, LIFESTYLE_TAG_DATA)
    seed_lookup_model(Achievement, ACHIEVEMENT_DATA)
    seed_lookup_model(Work, WORK_DATA)
    seed_lookup_model(School, SCHOOL_DATA)