from django.db import models
from cloudinary.models import CloudinaryField, CloudinaryResource
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils.text import slugify
from django.utils import timezone
from django.contrib.auth.models import User


TEMPLATE_CHOICES = (
    ("profile_update", "Profile Update"),
    ("profile_picture_changed", "Profile Picture Changed"),
    ("cover_photo_changed", "Cover Photo Changed"),
    ("new_message", "New Message"),
    ("mention_notification", "Mention Notification"),
    ("tag_notification", "Tag Notification"),
    ("new_like", "New Like"),
    ("new_comment", "New Comment"),
    ("comment_reply", "Comment Reply"),
    ("new_share", "New Share"),
    ("reaction_update", "Reaction Update"),
    ("friend_request", "Friend Request"),
    ("friend_request_accepted", "Friend Request Accepted"),
    ("group_invitation", "Group Invitation"),
    ("group_post_notification", "Group Post Notification"),
    ("event_invitation", "Event Invitation"),
    ("event_reminder", "Event Reminder"),
    ("follower_milestone", "Follower Milestone"),
    ("post_milestone", "Post Milestone"),
    ("achievement_badge", "Achievement Badge"),
    ("login_alert", "Login Alert"),
    ("two_factor_enabled", "Two-Factor Authentication Enabled"),
    ("two_factor_disabled", "Two-Factor Authentication Disabled"),
    ("security_alert", "Security Alert"),
)


class EmailTemplate(models.Model):

    name = models.CharField(max_length=100, choices=TEMPLATE_CHOICES, unique=True)
    subject = models.CharField(max_length=200)
    content = models.TextField(
        help_text="Use {{ subscriber.email }} for dynamic content"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)
