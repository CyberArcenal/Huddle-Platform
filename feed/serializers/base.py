# feed/serializers.py

from rest_framework import serializers
from django.core.exceptions import ValidationError
from typing import Dict, Any, Optional

from feed.models.base import Comment, Like, Post
from feed.services.comment import CommentService
from feed.services.like import LikeService
from feed.services.post import PostService
from users.models.base import User
from users.serializers.user import UserProfileSerializer















