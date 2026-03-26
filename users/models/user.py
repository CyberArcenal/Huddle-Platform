from enum import Enum
from django.contrib.auth.models import AbstractUser
from django.db import models

from feed.models.post import POST_PRIVACY_TYPES
from users.enums import UserStatus
from users.models.utilities import USER_STATUS_CHOICES


class ProfileImageTypeEnum(str, Enum):
    PROFILE = "profile"
    COVER = "cover"


PROFILE_IMAGE_TYPE_CHOICES = [
    ("profile", "Profile Picture"),
    ("cover", "Cover Photo"),
]


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


class RelationshipGoal(models.TextChoices):
    FRIENDSHIP = "Friendship", "Friendship"
    DATING = "Dating", "Dating"
    LONG_TERM = "LongTerm", "Long-term Relationship"
    MARRIAGE = "Marriage", "Marriage"


class UserQuerySet(models.QuerySet):
    def active(self):
        return self.filter(status=UserStatus.ACTIVE.value)

    def not_suspended(self):
        return self.exclude(
            status__in=[
                UserStatus.SUSPENDED.value,
                UserStatus.RESTRICTED.value,
                UserStatus.DELETED.value,
            ]
        )

    def suspended(self):
        return self.filter(status=UserStatus.SUSPENDED.value)

    def restricted(self):
        return self.filter(status=UserStatus.RESTRICTED.value)

    def deleted(self):
        return self.filter(status=UserStatus.DELETED.value)


class ActiveUserManager(models.Manager):
    def get_queryset(self):
        return UserQuerySet(self.model, using=self._db).active()

    def active(self):
        return self.get_queryset()

    # expose other helpers from the queryset if needed
    def not_suspended(self):
        return UserQuerySet(self.model, using=self._db).not_suspended()


class User(AbstractUser):
    status = models.CharField(
        max_length=20,
        choices=USER_STATUS_CHOICES,
        default=UserStatus.ACTIVE.value,
        help_text="Account status",
    )
    bio = models.TextField(max_length=500, blank=True)
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
    achievements = models.ManyToManyField(
        "Achievement", blank=True, related_name="users"
    )
    causes = models.ManyToManyField("SocialCause", blank=True, related_name="users")
    lifestyle_tags = models.ManyToManyField(
        "LifestyleTag", blank=True, related_name="users"
    )
    
    # Keep default manager for admin/migrations
    objects = models.Manager()
    # Add active_objects for convenience (returns only active users)
    active_objects = ActiveUserManager()

    # Personality & relationship fields
    personality_type = models.CharField(
        max_length=4,
        choices=MBTIType.choices,
        null=True,
        blank=True,
        help_text="User personality type (MBTI)",
    )
    love_language = models.CharField(
        max_length=20,
        choices=LoveLanguage.choices,
        null=True,
        blank=True,
        help_text="Primary love language",
    )
    relationship_goal = models.CharField(
        max_length=50,
        choices=RelationshipGoal.choices,
        null=True,
        blank=True,
        help_text="User's relationship goal",
    )

    # Location auto-fetched from Android app
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    location = models.CharField(max_length=200, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "users"


class UserImage(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="user_images/")
    privacy = models.CharField(
        max_length=10, choices=POST_PRIVACY_TYPES, default="followers"
    )
    image_type = models.CharField(max_length=20, choices=PROFILE_IMAGE_TYPE_CHOICES)
    caption = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "user_images"
        unique_together = ("user", "image_type")
