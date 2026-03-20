from enum import Enum
from django.contrib.auth.models import AbstractUser
from django.db import models

from users.enums import UserStatus
from users.models.base import USER_STATUS_CHOICES

class MBTIType(models.TextChoices):
    ISTJ = "ISTJ", "Inspector"
    ISFJ = "ISFJ", "Protector"
    INFJ = "INFJ", "Counselor"
    INTJ = "INTJ", "Mastermind"
    ISTP = "ISTP", "Crafter"
    ISFP = "ISFP", "Composer"
    INFP = "INFP", "Healer"
    INTP = "INTP", "Architect"
    ESTP = "ESTP", "Dynamo"
    ESFP = "ESFP", "Performer"
    ENFP = "ENFP", "Champion"
    ENTP = "ENTP", "Visionary"
    ESTJ = "ESTJ", "Supervisor"
    ESFJ = "ESFJ", "Provider"
    ENFJ = "ENFJ", "Teacher"
    ENTJ = "ENTJ", "Commander"


class Hobby(models.Model):
    name = models.CharField(max_length=100, unique=True)

class Interest(models.Model):
    name = models.CharField(max_length=100, unique=True)

class Favorite(models.Model):
    name = models.CharField(max_length=100, unique=True)

class Music(models.Model):
    name = models.CharField(max_length=100, unique=True)

class Work(models.Model):
    name = models.CharField(max_length=150, unique=True)

class School(models.Model):
    name = models.CharField(max_length=150, unique=True)
    
class Achievement(models.Model):
    name = models.CharField(max_length=150, unique=True)

class SocialCause(models.Model):
    name = models.CharField(max_length=150, unique=True)

class LifestyleTag(models.Model):
    name = models.CharField(max_length=100, unique=True)


class MBTIType(models.TextChoices):
    ISTJ = "ISTJ", "Inspector"
    ISFJ = "ISFJ", "Protector"
    INFJ = "INFJ", "Counselor"
    INTJ = "INTJ", "Mastermind"
    ISTP = "ISTP", "Crafter"
    ISFP = "ISFP", "Composer"
    INFP = "INFP", "Healer"
    INTP = "INTP", "Architect"
    ESTP = "ESTP", "Dynamo"
    ESFP = "ESFP", "Performer"
    ENFP = "ENFP", "Champion"
    ENTP = "ENTP", "Visionary"
    ESTJ = "ESTJ", "Supervisor"
    ESFJ = "ESFJ", "Provider"
    ENFJ = "ENFJ", "Teacher"
    ENTJ = "ENTJ", "Commander"


class LoveLanguage(models.TextChoices):
    WORDS = "Words", "Words of Affirmation"
    ACTS = "Acts", "Acts of Service"
    TIME = "Time", "Quality Time"
    GIFTS = "Gifts", "Receiving Gifts"
    TOUCH = "Touch", "Physical Touch"


class User(AbstractUser):
    status = models.CharField(
        max_length=20,
        choices=USER_STATUS_CHOICES,
        default=UserStatus.ACTIVE.value,
        help_text="Account status",
    )
    bio = models.TextField(max_length=500, blank=True)
    profile_picture = models.ImageField(upload_to="profile_pics/", blank=True, null=True)
    cover_photo = models.ImageField(upload_to="covers/", blank=True, null=True)
    date_of_birth = models.DateField(blank=True, null=True)
    phone_number = models.CharField(max_length=15, blank=True)
    is_verified = models.BooleanField(default=False)

    # Lifestyle fields (pre-defined choices)
    hobbies = models.ManyToManyField("Hobby", blank=True, related_name="users")
    interests = models.ManyToManyField("Interest", blank=True, related_name="users")
    favorites = models.ManyToManyField("Favorite", blank=True, related_name="users")
    favorite_music = models.ManyToManyField("Music", blank=True, related_name="users")
    works = models.ManyToManyField("Work", blank=True, related_name="users")
    schools = models.ManyToManyField("School", blank=True, related_name="users")
    achievements = models.ManyToManyField("Achievement", blank=True, related_name="users")
    causes = models.ManyToManyField("SocialCause", blank=True, related_name="users")
    lifestyle_tags = models.ManyToManyField("LifestyleTag", blank=True, related_name="users")

    # Personality & relationship fields
    personality_type = models.CharField(
        max_length=4,
        choices=MBTIType.choices,
        null=True,
        blank=True,
        help_text="User personality type (MBTI)"
    )
    love_language = models.CharField(
        max_length=20,
        choices=LoveLanguage.choices,
        null=True,
        blank=True,
        help_text="Primary love language"
    )
    relationship_goal = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        help_text="User's relationship goal (friendship, dating, long-term)"
    )

    # Location auto-fetched from Android app
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    location = models.CharField(max_length=200, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "users"
