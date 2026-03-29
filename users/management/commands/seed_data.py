import random
from datetime import datetime, timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from faker import Faker

# ----------------------------------------------------------------------
# Imports for all models (adjust app labels if necessary)
# ----------------------------------------------------------------------
from admin_pannel.models.admin_log import AdminLog
from admin_pannel.models.reported_content import ReportedContent
from analytics.models.platform_analytics import PlatformAnalytics
from analytics.models.user_analytics import UserAnalytics
from analytics.models.trend_score import ObjectTrendScore
from audit.models.base import AuditLog
from dating.models.dating_message import DatingMessage
from dating.models.dating_preference import DatingPreference
from dating.models.match import Match
from events.models import Event
from events.models.event_analytics import EventAnalytics
from events.models.event_attendance import EventAttendance
from feed.models.bookmark import ObjectBookmark
from feed.models.comment import Comment
from feed.models.media import Media, MediaVariant
from feed.models.post import Post, POST_TYPES, POST_PRIVACY_TYPES
from feed.models.reaction import Reaction, REACTION_TYPES
from feed.models.reel import Reel
from feed.models.share import Share
from feed.models.view import ObjectView
from groups.models.group import Group, GROUP_PRIVACY_CHOICES, GROUP_TYPE_CHOICES
from groups.models.member import GroupMember, GROUP_ROLE_CHOICES
from messaging.models.conversation import Conversation
from messaging.models.message import Message
from notifications.models.email_template import EmailTemplate
from notifications.models.notification import Notification
from notifications.models.notify_log import NotifyLog
from search.models.search_history import SearchHistory
from stories.models.story import Story
from stories.models.highlight import StoryHighlight
from users.models import (
    UserFollow, BlockedUser, Friendship, MutedUser,
    BlacklistedAccessToken, SecurityLog, UserSecuritySettings,
    LoginSession, LoginCheckpoint, OtpRequest, UserActivity,
    Hobby, Interest, Favorite, Music, Work, School,
    Achievement, SocialCause, LifestyleTag, MBTIType, LoveLanguage,
    UserImage
)
from users.models.utilities import ACTION_TYPES, USER_STATUS_CHOICES, OTP_TYPES
User = get_user_model()
fake = Faker()


def make_aware(dt):
    """Ensure datetime is timezone-aware (assumes UTC)."""
    if dt is None:
        return None
    if timezone.is_naive(dt):
        return timezone.make_aware(dt, timezone.get_default_timezone())
    return dt


class Command(BaseCommand):
    help = "Seeds the database with sample data for development"

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete all existing data before seeding",
        )

    def handle(self, *args, **options):
        try:
            with transaction.atomic():
                if options["clear"]:
                    self.stdout.write("Clearing existing data...")
                    # Order matters to avoid FK constraints
                    models_to_delete = [
                        # First, models with many dependencies
                        MediaVariant,
                        Media,
                        Share,
                        Reaction,
                        Reel,
                        Notification,
                        SearchHistory,
                        EventAttendance,
                        EventAnalytics,
                        Event,
                        StoryHighlight,
                        Story,
                        Message,
                        Conversation,
                        Comment,
                        Post,
                        GroupMember,
                        Group,
                        UserFollow,
                        BlockedUser,
                        Friendship,
                        MutedUser,
                        UserActivity,
                        OtpRequest,
                        LoginCheckpoint,
                        LoginSession,
                        UserSecuritySettings,
                        SecurityLog,
                        BlacklistedAccessToken,
                        AdminLog,
                        ReportedContent,
                        ObjectBookmark,
                        ObjectTrendScore,
                        ObjectView,
                        NotifyLog,
                        EmailTemplate,
                        DatingMessage,
                        Match,
                        DatingPreference,
                        UserImage,
                        PlatformAnalytics,
                        UserAnalytics,
                        AuditLog,
                        # Base models
                        Hobby,
                        Interest,
                        Favorite,
                        Music,
                        Work,
                        School,
                        Achievement,
                        SocialCause,
                        LifestyleTag,
                        User,
                    ]
                    # Filter out None in case some models aren't defined
                    models_to_delete = [m for m in models_to_delete if m is not None]
                    for model in models_to_delete:
                        model.objects.all().delete()
                    self.stdout.write(self.style.SUCCESS("Database cleared."))

                self.stdout.write("Seeding data...")
                self.seed_base_models()
                self.seed_users()
                self.seed_user_images()
                self.seed_follows()
                self.seed_blocked()
                self.seed_friendships()
                self.seed_muted()
                self.seed_groups()
                self.seed_posts(count=500)
                self.seed_post_media()          # updated to use GenericFK
                self.seed_media_variants()
                self.seed_comments()
                self.seed_reactions()
                self.seed_reels()
                self.seed_reel_media()
                self.seed_shares(count=300)
                self.seed_conversations()
                self.seed_messages()
                self.seed_stories()
                self.seed_story_highlights()
                self.seed_events()
                self.seed_event_attendances()
                self.seed_event_analytics()
                self.seed_admin_logs()
                self.seed_reported_content()
                self.seed_notifications()
                self.seed_search_history()
                self.seed_user_activity()
                self.seed_user_security_settings()
                self.seed_login_sessions()
                self.seed_login_checkpoints()
                self.seed_otp_requests()
                self.seed_blacklisted_tokens()
                self.seed_security_logs()
                self.seed_dating_preferences()
                self.seed_matches()
                self.seed_dating_messages()
                self.seed_analytics()               # platform & user analytics
                self.seed_object_bookmarks()
                self.seed_object_trend_scores()
                self.seed_object_views()
                self.seed_email_templates()
                self.seed_notify_logs()
                self.seed_audit_logs()
                self.stdout.write(self.style.SUCCESS("Database seeded successfully!"))
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"Error occurred, transaction rolled back: {e}")
            )
            raise

    # ------------------------------------------------------------------
    # Seeding helpers
    # ------------------------------------------------------------------
    def seed_base_models(self, count=5):
        """Seed lookup tables for user preferences."""
        self.stdout.write("Seeding base models...")
        models_to_seed = [
            (Hobby, "hobby"),
            (Interest, "interest"),
            (Favorite, "favorite"),
            (Music, "music"),
            (Work, "work"),
            (School, "school"),
            (Achievement, "achievement"),
            (SocialCause, "social_cause"),
            (LifestyleTag, "lifestyle_tag"),
        ]
        for model, name_prefix in models_to_seed:
            existing = model.objects.count()
            if existing < count:
                for i in range(count - existing):
                    model.objects.create(name=fake.unique.word().capitalize())
        self.stdout.write("Base models seeded.")

    def seed_users(self, count=20):
        self.stdout.write("Creating users...")
        users = []
        for i in range(count):
            username = fake.user_name() + str(i)
            email = fake.email()
            date_joined = make_aware(
                fake.date_time_between(start_date="-2y", end_date="-30d")
            )
            last_login = make_aware(
                fake.date_time_between(start_date="-30d", end_date="now")
            )
            user = User(
                username=username,
                email=email,
                bio=fake.text(max_nb_chars=200),
                date_of_birth=fake.date_of_birth(minimum_age=18, maximum_age=80),
                phone_number=fake.phone_number()[:15],
                is_verified=random.choice([True, False]),
                status=random.choice([choice[0] for choice in USER_STATUS_CHOICES]),
                personality_type=(
                    random.choice([choice[0] for choice in MBTIType.choices])
                    if random.random() > 0.3
                    else None
                ),
                love_language=(
                    random.choice([choice[0] for choice in LoveLanguage.choices])
                    if random.random() > 0.5
                    else None
                ),
                relationship_goal=random.choice(
                    ["friendship", "dating", "long-term", "marriage", None]
                ),
                latitude=random.uniform(-90, 90) if random.random() > 0.5 else None,
                longitude=random.uniform(-180, 180) if random.random() > 0.5 else None,
                location=fake.city() if random.random() > 0.5 else None,
                last_login=last_login,
                date_joined=date_joined,
            )
            user.set_password("password123")
            users.append(user)

        # Create one superuser
        if not User.objects.filter(is_superuser=True).exists():
            admin_joined = timezone.now() - timedelta(days=30)
            admin = User(
                username="admin",
                email="admin@example.com",
                bio="Administrator",
                is_verified=True,
                is_superuser=True,
                is_staff=True,
                status="active",
                date_joined=admin_joined,
                last_login=timezone.now(),
            )
            admin.set_password("admin123")
            users.append(admin)

        User.objects.bulk_create(users, ignore_conflicts=True)

        # Assign many-to-many fields
        all_users = list(User.objects.all())
        model_to_attr = {
            Hobby: "hobbies",
            Interest: "interests",
            Favorite: "favorites",
            Music: "favorite_music",
            Work: "works",
            School: "schools",
            Achievement: "achievements",
            SocialCause: "causes",
            LifestyleTag: "lifestyle_tags",
        }
        for model, attr_name in model_to_attr.items():
            items = list(model.objects.all())
            if items:
                for user in random.sample(all_users, min(10, len(all_users))):
                    try:
                        related_manager = getattr(user, attr_name)
                        related_manager.set(
                            random.sample(items, random.randint(1, min(3, len(items))))
                        )
                    except AttributeError:
                        self.stdout.write(
                            self.style.WARNING(
                                f"User model has no attribute '{attr_name}'. Skipping."
                            )
                        )
        self.stdout.write(f"Created {len(users)} users.")

    def seed_user_images(self, count=40):
        self.stdout.write("Creating user images...")
        users = list(User.objects.all())
        if not users:
            return
        images = []
        for _ in range(count):
            user = random.choice(users)
            img_type = random.choice(["profile", "cover"])
            privacy = random.choice(["public", "followers", "private"])
            created = make_aware(
                fake.date_time_between(start_date="-1y", end_date="now")
            )
            images.append(
                UserImage(
                    user=user,
                    image=None,  # No actual file
                    privacy=privacy,
                    image_type=img_type,
                    caption=fake.sentence(),
                    is_active=True,
                    created_at=created,
                )
            )
        UserImage.objects.bulk_create(images, ignore_conflicts=True)
        self.stdout.write(f"Created {len(images)} user images.")

    def seed_follows(self, count=100):
        self.stdout.write("Creating follows...")
        users = list(User.objects.all())
        follows = []
        for _ in range(count):
            follower, following = random.sample(users, 2)
            if follower != following:
                created = make_aware(
                    fake.date_time_between(start_date="-60d", end_date="now")
                )
                follows.append(
                    UserFollow(follower=follower, following=following, created_at=created)
                )
        UserFollow.objects.bulk_create(follows, ignore_conflicts=True)
        self.stdout.write(f"Created {len(follows)} follows.")

    def seed_blocked(self, count=30):
        self.stdout.write("Creating blocked users...")
        users = list(User.objects.all())
        blocks = []
        for _ in range(count):
            blocker, blocked = random.sample(users, 2)
            if blocker != blocked:
                created = make_aware(
                    fake.date_time_between(start_date="-60d", end_date="now")
                )
                blocks.append(
                    BlockedUser(user=blocker, blocked=blocked, created_at=created)
                )
        BlockedUser.objects.bulk_create(blocks, ignore_conflicts=True)
        self.stdout.write(f"Created {len(blocks)} blocks.")

    def seed_friendships(self, count=80):
        self.stdout.write("Creating friendships...")
        users = list(User.objects.all())
        statuses = ["pending", "accepted", "declined"]
        tags = [
            "normal", "favorite", "pinned", "close", "family",
            "workmate", "bestfriend", "acquaintance"
        ]
        friendships = []
        for _ in range(count):
            from_user, to_user = random.sample(users, 2)
            if from_user != to_user:
                created = make_aware(
                    fake.date_time_between(start_date="-60d", end_date="now")
                )
                friendships.append(
                    Friendship(
                        from_user=from_user,
                        to_user=to_user,
                        created_at=created,
                        status=random.choice(statuses),
                        tag=random.choice(tags)
                    )
                )
        Friendship.objects.bulk_create(friendships, ignore_conflicts=True)
        self.stdout.write(f"Created {len(friendships)} friendships.")

    def seed_muted(self, count=30):
        self.stdout.write("Creating muted users...")
        users = list(User.objects.all())
        mutes = []
        for _ in range(count):
            muter, muted = random.sample(users, 2)
            if muter != muted:
                created = make_aware(
                    fake.date_time_between(start_date="-60d", end_date="now")
                )
                mutes.append(MutedUser(user=muter, muted=muted, created_at=created))
        MutedUser.objects.bulk_create(mutes, ignore_conflicts=True)
        self.stdout.write(f"Created {len(mutes)} mutes.")

    def seed_groups(self, count=15):
        # ... (unchanged from original, but we'll keep it for completeness)
        self.stdout.write("Creating groups...")
        users = list(User.objects.all())
        groups = []
        for _ in range(count):
            creator = random.choice(users)
            created = make_aware(
                fake.date_time_between(start_date="-1y", end_date="-30d")
            )
            group = Group(
                name=fake.catch_phrase()[:50],
                description=fake.text(max_nb_chars=300),
                creator=creator,
                privacy=random.choice([choice[0] for choice in GROUP_PRIVACY_CHOICES]),
                group_type=random.choice([choice[0] for choice in GROUP_TYPE_CHOICES]),
                member_count=0,
                created_at=created,
            )
            groups.append(group)
        Group.objects.bulk_create(groups)

        memberships = []
        for group in groups:
            memberships.append(
                GroupMember(group=group, user=group.creator, role="admin", joined_at=group.created_at)
            )
            for user in random.sample(users, random.randint(3, 10)):
                if user != group.creator:
                    joined = make_aware(
                        fake.date_time_between(start_date=group.created_at, end_date="now")
                    )
                    memberships.append(
                        GroupMember(
                            group=group,
                            user=user,
                            role=random.choice([choice[0] for choice in GROUP_ROLE_CHOICES if choice[0] != "admin"]),
                            joined_at=joined,
                        )
                    )
        GroupMember.objects.bulk_create(memberships, ignore_conflicts=True)
        for group in groups:
            group.member_count = group.memberships.count()
            group.save()
        self.stdout.write(f"Created {len(groups)} groups with members.")

    def seed_posts(self, count=500):
        # ... (unchanged from original, but we'll keep it)
        self.stdout.write("Creating posts...")
        users = list(User.objects.all())
        groups = list(Group.objects.all())
        normal_posts = []
        share_posts = []
        for _ in range(count):
            user = random.choice(users)
            group = random.choice([None] + groups) if groups else None
            post_type = random.choice([choice[0] for choice in POST_TYPES])
            created = make_aware(
                fake.date_time_between(start_date="-90d", end_date="now")
            )
            updated = make_aware(
                fake.date_time_between(start_date=created, end_date="now")
            )
            post = Post(
                user=user,
                group=group,
                shared_post=None,
                content=fake.paragraph(nb_sentences=5),
                post_type=post_type,
                privacy=random.choice([choice[0] for choice in POST_PRIVACY_TYPES]),
                is_deleted=False,
                created_at=created,
                updated_at=updated,
            )
            if post_type == "share":
                share_posts.append(post)
            else:
                normal_posts.append(post)

        Post.objects.bulk_create(normal_posts)
        saved_post_ids = list(Post.objects.values_list('id', flat=True))
        if share_posts:
            for share_post in share_posts:
                if saved_post_ids:
                    share_post.shared_post_id = random.choice(saved_post_ids)
            Post.objects.bulk_create(share_posts)
        self.stdout.write(f"Created {len(normal_posts) + len(share_posts)} posts.")

    def seed_post_media(self, count=200):
        """Create Media entries for posts (using GenericForeignKey)."""
        self.stdout.write("Creating post media...")
        posts = list(Post.objects.filter(post_type__in=["image", "video"]))
        if not posts:
            self.stdout.write("No image/video posts found, skipping.")
            return

        post_ct = ContentType.objects.get_for_model(Post)
        media_list = []
        for _ in range(min(count, len(posts) * 3)):
            post = random.choice(posts)
            order = random.randint(0, 5)
            created = make_aware(
                fake.date_time_between(start_date=post.created_at, end_date="now")
            )
            media_list.append(
                Media(
                    created_by=post.user,
                    content_type=post_ct,
                    object_id=post.id,
                    file=None,
                    order=order,
                    created_at=created,
                )
            )
        Media.objects.bulk_create(media_list)
        self.stdout.write(f"Created {len(media_list)} post media entries.")

    def seed_media_variants(self, count=300):
        """Create variants for existing Media objects."""
        self.stdout.write("Creating media variants...")
        media_objects = list(Media.objects.all())
        if not media_objects:
            self.stdout.write("No media objects found, skipping.")
            return

        variant_types = ["thumbnail", "small", "medium", "large", "video_preview", "video_transcoded"]
        variants = []
        for _ in range(min(count, len(media_objects) * 2)):
            media = random.choice(media_objects)
            vtype = random.choice(variant_types)
            created = make_aware(
                fake.date_time_between(start_date=media.created_at, end_date="now")
            )
            variants.append(
                MediaVariant(
                    media=media,
                    variant_type=vtype,
                    file=None,
                    width=random.randint(200, 1920),
                    height=random.randint(200, 1080),
                    duration=random.uniform(1, 300) if vtype.startswith("video") else None,
                    codec="h264" if vtype.startswith("video") else None,
                    size_bytes=random.randint(1000, 10_000_000),
                    created_at=created,
                )
            )
        MediaVariant.objects.bulk_create(variants, ignore_conflicts=True)
        self.stdout.write(f"Created {len(variants)} media variants.")

    def seed_reel_media(self, count=80):
        """Create Media entries for reels."""
        self.stdout.write("Creating reel media...")
        reels = list(Reel.objects.all())
        if not reels:
            self.stdout.write("No reels found, skipping.")
            return

        reel_ct = ContentType.objects.get_for_model(Reel)
        media_list = []
        for reel in reels:
            # each reel gets 1 media
            created = make_aware(
                fake.date_time_between(start_date=reel.created_at, end_date="now")
            )
            media_list.append(
                Media(
                    created_by=reel.user,
                    content_type=reel_ct,
                    object_id=reel.id,
                    file=None,
                    order=0,
                    created_at=created,
                )
            )
        Media.objects.bulk_create(media_list)
        self.stdout.write(f"Created {len(media_list)} reel media entries.")

    def seed_comments(self, count=200):
        # ... (unchanged, already uses generic relations)
        # (We'll keep as is, but ensure it uses ContentType correctly)
        self.stdout.write("Creating comments...")
        users = list(User.objects.all())
        post_ct = ContentType.objects.get_for_model(Post)
        reel_ct = ContentType.objects.get_for_model(Reel)
        content_types = []
        if Post.objects.exists():
            content_types.append(post_ct)
        if Reel.objects.exists():
            content_types.append(reel_ct)
        if not content_types:
            self.stdout.write("No commentable objects found, skipping.")
            return

        top_comments = []
        for _ in range(count // 2):
            user = random.choice(users)
            ct = random.choice(content_types)
            model_class = ct.model_class()
            obj = random.choice(model_class.objects.all())
            created = make_aware(
                fake.date_time_between(start_date=obj.created_at, end_date="now")
            )
            top_comments.append(
                Comment(
                    user=user,
                    content_type=ct,
                    object_id=obj.id,
                    parent_comment=None,
                    content=fake.sentence(nb_words=15),
                    is_deleted=False,
                    created_at=created,
                )
            )
        Comment.objects.bulk_create(top_comments)

        parents = list(Comment.objects.filter(parent_comment__isnull=True))
        replies = []
        for _ in range(count // 2):
            if not parents:
                break
            user = random.choice(users)
            parent = random.choice(parents)
            ct = parent.content_type
            obj = ct.model_class().objects.get(id=parent.object_id)
            created = make_aware(
                fake.date_time_between(start_date=parent.created_at, end_date="now")
            )
            replies.append(
                Comment(
                    user=user,
                    content_type=ct,
                    object_id=obj.id,
                    parent_comment=parent,
                    content=fake.sentence(nb_words=15),
                    is_deleted=False,
                    created_at=created,
                )
            )
        if replies:
            Comment.objects.bulk_create(replies)
        self.stdout.write(f"Created {len(top_comments) + len(replies)} comments.")

    def seed_reactions(self, count=500):
        # ... (unchanged)
        self.stdout.write("Creating reactions...")
        users = list(User.objects.all())
        models = [Post, Comment, Reel, Story]
        content_types = []
        for model in models:
            if model.objects.exists():
                content_types.append(ContentType.objects.get_for_model(model))
        if not content_types:
            self.stdout.write("No reactable objects found, skipping.")
            return

        reactions = []
        reaction_choices = [choice[0] for choice in REACTION_TYPES]
        seen = set()
        for _ in range(count):
            user = random.choice(users)
            ct = random.choice(content_types)
            model_class = ct.model_class()
            obj_ids = list(model_class.objects.values_list("id", flat=True))
            if not obj_ids:
                continue
            object_id = random.choice(obj_ids)
            key = (user.id, ct.id, object_id)
            if key in seen:
                continue
            seen.add(key)
            created = make_aware(
                fake.date_time_between(start_date="-60d", end_date="now")
            )
            reactions.append(
                Reaction(
                    user=user,
                    content_type=ct,
                    object_id=object_id,
                    reaction_type=random.choice(reaction_choices),
                    created_at=created,
                )
            )
        Reaction.objects.bulk_create(reactions, ignore_conflicts=True)
        self.stdout.write(f"Created {len(reactions)} reactions.")

    def seed_reels(self, count=30):
        # ... (unchanged)
        self.stdout.write("Creating reels...")
        users = list(User.objects.all())
        reels = []
        for _ in range(count):
            user = random.choice(users)
            created = make_aware(
                fake.date_time_between(start_date="-60d", end_date="now")
            )
            updated = make_aware(
                fake.date_time_between(start_date=created, end_date="now")
            )
            reel = Reel(
                user=user,
                caption=fake.sentence(nb_words=10),
                thumbnail=None,
                audio=None,
                duration=random.uniform(5.0, 60.0),
                privacy=random.choice([choice[0] for choice in POST_PRIVACY_TYPES]),
                is_deleted=False,
                created_at=created,
                updated_at=updated,
            )
            reels.append(reel)
        Reel.objects.bulk_create(reels)
        self.stdout.write(f"Created {len(reels)} reels.")

    def seed_shares(self, count=300):
        self.stdout.write("Creating shares...")
        users = list(User.objects.all())
        groups = list(Group.objects.all())
        models = [Post, Comment, Reel, Story]
        content_types = []
        for model in models:
            if model.objects.exists():
                content_types.append(ContentType.objects.get_for_model(model))

        if not content_types:
            self.stdout.write(
                self.style.WARNING("No shareable content found, skipping shares.")
            )
            return

        shares_created = 0
        for _ in range(count):
            user = random.choice(users)
            ct = random.choice(content_types)
            model_class = ct.model_class()
            obj_ids = list(model_class.objects.values_list("id", flat=True))
            if not obj_ids:
                continue
            object_id = random.choice(obj_ids)
            created = make_aware(
                fake.date_time_between(start_date="-30d", end_date="now")
            )
            group = random.choice(groups) if groups and random.random() > 0.7 else None
            share = Share(
                user=user,
                group=group,
                content_type=ct,
                object_id=object_id,
                caption=fake.sentence() if random.random() < 0.7 else "",
                privacy=random.choice(["public", "followers", "private"]),
                is_deleted=False,
                created_at=created,
                updated_at=created + timedelta(hours=random.randint(1, 48)),
            )
            share.save()
            shares_created += 1

        self.stdout.write(f"Created {shares_created} shares.")

    def seed_conversations(self, count=30):
        # ... (unchanged)
        self.stdout.write("Creating conversations...")
        users = list(User.objects.all())
        conversations = []
        for _ in range(count):
            conv_type = random.choice(["direct", "group"])
            name = fake.catch_phrase()[:50] if conv_type == "group" else None
            created = make_aware(
                fake.date_time_between(start_date="-120d", end_date="-30d")
            )
            updated = make_aware(
                fake.date_time_between(start_date=created, end_date="now")
            )
            conv = Conversation(
                name=name,
                conversation_type=conv_type,
                created_at=created,
                updated_at=updated,
            )
            conversations.append(conv)
        Conversation.objects.bulk_create(conversations)
        for conv in conversations:
            if conv.conversation_type == "direct":
                participants = random.sample(users, 2)
            else:
                participants = random.sample(users, random.randint(3, 8))
            conv.participants.set(participants)
        self.stdout.write(f"Created {len(conversations)} conversations.")

    def seed_messages(self, count=500):
        # ... (unchanged)
        self.stdout.write("Creating messages...")
        users = list(User.objects.all())
        conversations = list(Conversation.objects.all())
        messages = []
        for _ in range(count):
            conv = random.choice(conversations)
            participants = list(conv.participants.all())
            if not participants:
                continue
            sender = random.choice(participants)
            created = make_aware(
                fake.date_time_between(start_date=conv.created_at, end_date="now")
            )
            msg = Message(
                conversation=conv,
                sender=sender,
                content=fake.sentence(nb_words=20),
                media=None,
                media_type=None,
                is_read=random.choice([True, False]),
                is_deleted=False,
                created_at=created,
            )
            messages.append(msg)
        Message.objects.bulk_create(messages)
        self.stdout.write(f"Created {len(messages)} messages.")

    def seed_stories(self, count=50):
        # ... (unchanged)
        self.stdout.write("Creating stories...")
        users = list(User.objects.all())
        stories = []
        now = timezone.now()
        for _ in range(count):
            user = random.choice(users)
            story_type = random.choice(["image", "video", "text"])
            expires_at = now + timedelta(hours=random.randint(1, 24))
            created = make_aware(
                fake.date_time_between(start_date="-3d", end_date="now")
            )
            story = Story(
                user=user,
                story_type=story_type,
                content=fake.sentence(nb_words=10) if story_type == "text" else None,
                media_url=None,
                expires_at=expires_at,
                is_active=True,
                created_at=created,
            )
            stories.append(story)
        Story.objects.bulk_create(stories)
        self.stdout.write(f"Created {len(stories)} stories.")

    def seed_story_highlights(self, count=30):
        if StoryHighlight is None:
            self.stdout.write("StoryHighlight model not found, skipping.")
            return
        self.stdout.write("Creating story highlights...")
        users = list(User.objects.all())
        stories = list(Story.objects.all())
        if not stories:
            self.stdout.write("No stories available for highlights.")
            return
        highlights = []
        for _ in range(count):
            user = random.choice(users)
            user_stories = Story.objects.filter(user=user)
            if not user_stories:
                continue
            num_stories = random.randint(1, min(5, user_stories.count()))
            selected_stories = random.sample(list(user_stories), num_stories)
            title = fake.word().capitalize()
            cover = random.choice(selected_stories) if selected_stories else None
            highlight = StoryHighlight(user=user, title=title, cover=cover)
            highlights.append(highlight)
        StoryHighlight.objects.bulk_create(highlights, ignore_conflicts=True)
        for highlight in StoryHighlight.objects.all():
            user_stories = Story.objects.filter(user=highlight.user)
            if user_stories:
                selected = random.sample(list(user_stories), min(3, user_stories.count()))
                highlight.stories.set(selected)
        self.stdout.write(f"Created {len(highlights)} story highlights.")

    def seed_events(self, count=20):
        # ... (unchanged)
        self.stdout.write("Creating events...")
        users = list(User.objects.all())
        groups = list(Group.objects.all())
        events = []
        for _ in range(count):
            organizer = random.choice(users)
            event_type = random.choice(["public", "private", "group"])
            group = random.choice(groups) if event_type == "group" and groups else None
            start = make_aware(
                fake.date_time_between(start_date="-30d", end_date="+60d")
            )
            end = start + timedelta(hours=random.randint(1, 5))
            created = make_aware(
                fake.date_time_between(start_date="-60d", end_date="now")
            )
            event = Event(
                title=fake.catch_phrase()[:100],
                description=fake.text(max_nb_chars=400),
                organizer=organizer,
                group=group,
                event_type=event_type,
                location=fake.city(),
                start_time=start,
                end_time=end,
                max_attendees=random.choice([None, random.randint(10, 100)]),
                attending_count=0,
                maybe_count=0,
                declined_count=0,
                created_at=created,
            )
            events.append(event)
        Event.objects.bulk_create(events)
        self.stdout.write(f"Created {len(events)} events.")

    def seed_event_attendances(self, count=150):
        # ... (unchanged)
        self.stdout.write("Creating event attendances...")
        users = list(User.objects.all())
        events = list(Event.objects.all())
        attendances = []
        for _ in range(count):
            user = random.choice(users)
            event = random.choice(events)
            status = random.choice(["going", "maybe", "declined"])
            joined = make_aware(
                fake.date_time_between(start_date=event.created_at, end_date="now")
            )
            attendances.append(
                EventAttendance(event=event, user=user, status=status, joined_at=joined)
            )
        EventAttendance.objects.bulk_create(attendances, ignore_conflicts=True)
        for event in events:
            event.attending_count = event.attendances.filter(status="going").count()
            event.maybe_count = event.attendances.filter(status="maybe").count()
            event.declined_count = event.attendances.filter(status="declined").count()
            event.save()
        self.stdout.write(f"Created {len(attendances)} attendances.")

    def seed_event_analytics(self, days_back=30):
        self.stdout.write("Creating event analytics...")
        events = Event.objects.all()
        event_analytics = []
        today = timezone.now().date()
        for event in events[:10]:
            for days_ago in range(days_back):
                date = today - timedelta(days=days_ago)
                if date >= event.created_at.date():
                    ea = EventAnalytics(
                        event=event,
                        date=date,
                        rsvp_going_count=random.randint(0, 20),
                        rsvp_maybe_count=random.randint(0, 5),
                        rsvp_declined_count=random.randint(0, 3),
                        rsvp_changes=random.randint(0, 5),
                        created_at=timezone.now(),
                        updated_at=timezone.now(),
                    )
                    event_analytics.append(ea)
        EventAnalytics.objects.bulk_create(event_analytics, ignore_conflicts=True)
        self.stdout.write("Event analytics seeded.")

    def seed_admin_logs(self, count=50):
        # ... (unchanged)
        self.stdout.write("Creating admin logs...")
        admins = User.objects.filter(is_superuser=True)
        if not admins:
            admins = User.objects.all()[:1]
        users = list(User.objects.all())
        logs = []
        for _ in range(count):
            admin = random.choice(admins)
            action = random.choice(["user_ban", "user_warn", "post_remove", "group_remove", "content_review"])
            target_user = random.choice(users) if random.random() < 0.7 else None
            target_id = random.randint(1, 1000) if not target_user else None
            created = make_aware(
                fake.date_time_between(start_date="-90d", end_date="now")
            )
            log = AdminLog(
                admin_user=admin,
                action=action,
                target_user=target_user,
                target_id=target_id,
                reason=fake.sentence(),
                created_at=created,
            )
            logs.append(log)
        AdminLog.objects.bulk_create(logs)
        self.stdout.write(f"Created {len(logs)} admin logs.")

    def seed_reported_content(self, count=40):
        # ... (unchanged)
        self.stdout.write("Creating reported content...")
        users = list(User.objects.all())
        if not users:
            return
        reportable_models = [
            (Post, Post.objects.all()),
            (Comment, Comment.objects.all()),
            (User, User.objects.all()),
            (Group, Group.objects.all()),
        ]
        reportable_models = [(model, qs) for model, qs in reportable_models if qs.exists()]
        if not reportable_models:
            self.stdout.write("No reportable objects found, skipping.")
            return
        reports = []
        statuses = ["pending", "reviewed", "resolved", "dismissed"]
        for _ in range(count):
            reporter = random.choice(users)
            model, qs = random.choice(reportable_models)
            content_type = ContentType.objects.get_for_model(model)
            obj = random.choice(qs)
            created = make_aware(
                fake.date_time_between(start_date="-60d", end_date="now")
            )
            resolved = None
            if random.random() < 0.5:
                resolved = make_aware(
                    fake.date_time_between(start_date=created, end_date="now")
                )
            report = ReportedContent(
                reporter=reporter,
                content_type=content_type,
                object_id=obj.id,
                reason=fake.sentence(),
                status=random.choice(statuses),
                created_at=created,
                resolved_at=resolved,
            )
            reports.append(report)
        ReportedContent.objects.bulk_create(reports)
        self.stdout.write(f"Created {len(reports)} reports.")

    def seed_notifications(self, count=300):
        # ... (unchanged)
        self.stdout.write("Creating notifications...")
        users = list(User.objects.all())
        actors = list(User.objects.all())
        notifications = []
        for _ in range(count):
            user = random.choice(users)
            actor = random.choice([a for a in actors if a != user])
            ntype = random.choice(["like", "comment", "follow", "message", "group_invite", "event_reminder"])
            created = make_aware(
                fake.date_time_between(start_date="-30d", end_date="now")
            )
            notif = Notification(
                user=user,
                actor=actor,
                notification_type=ntype,
                message=fake.sentence(),
                is_read=random.choice([True, False]),
                related_id=random.randint(1, 500),
                related_model=random.choice(["post", "comment", "group", "event"]),
                created_at=created,
            )
            notifications.append(notif)
        Notification.objects.bulk_create(notifications)
        self.stdout.write(f"Created {len(notifications)} notifications.")

    def seed_search_history(self, count=100):
        # ... (unchanged)
        self.stdout.write("Creating search history...")
        users = list(User.objects.all()) + [None]
        searches = []
        for _ in range(count):
            user = random.choice(users) if random.random() < 0.8 else None
            searched = make_aware(
                fake.date_time_between(start_date="-60d", end_date="now")
            )
            search = SearchHistory(
                user=user,
                query=fake.word(),
                search_type=random.choice(["all", "users", "groups", "posts"]),
                results_count=random.randint(0, 50),
                searched_at=searched,
            )
            searches.append(search)
        SearchHistory.objects.bulk_create(searches)
        self.stdout.write(f"Created {len(searches)} search records.")

    def seed_user_activity(self, count=200):
        # ... (unchanged)
        self.stdout.write("Creating user activities...")
        users = list(User.objects.all())
        action_choices = [choice[0] for choice in ACTION_TYPES]
        activities = []
        for _ in range(count):
            user = random.choice(users)
            timestamp = make_aware(
                fake.date_time_between(start_date="-30d", end_date="now")
            )
            activity = UserActivity(
                user=user,
                action=random.choice(action_choices),
                description=fake.sentence(),
                ip_address=fake.ipv4(),
                user_agent=fake.user_agent(),
                timestamp=timestamp,
                location=fake.city(),
                metadata={},
            )
            activities.append(activity)
        UserActivity.objects.bulk_create(activities)
        self.stdout.write(f"Created {len(activities)} user activities.")

    def seed_user_security_settings(self):
        self.stdout.write("Creating user security settings...")
        users = list(User.objects.all())
        settings_list = []
        for user in users:
            settings_list.append(
                UserSecuritySettings(
                    user=user,
                    two_factor_enabled=random.choice([True, False]),
                    recovery_email=user.email if random.random() > 0.5 else None,
                    recovery_phone=user.phone_number if random.random() > 0.5 else None,
                    alert_on_new_device=random.choice([True, False]),
                    alert_on_password_change=random.choice([True, False]),
                    alert_on_failed_login=random.choice([True, False]),
                )
            )
        UserSecuritySettings.objects.bulk_create(settings_list, ignore_conflicts=True)
        self.stdout.write("User security settings created.")

    def seed_login_sessions(self, count=100):
        self.stdout.write("Creating login sessions...")
        users = list(User.objects.all())
        sessions = []
        for _ in range(count):
            user = random.choice(users)
            created = make_aware(
                fake.date_time_between(start_date="-90d", end_date="now")
            )
            expires = created + timedelta(days=random.randint(1, 30))
            last_used = make_aware(
                fake.date_time_between(start_date=created, end_date="now")
            )
            session = LoginSession(
                user=user,
                device_name=fake.word() + " " + fake.random_element(["Mobile", "Web", "Tablet"]),
                user_agent=fake.user_agent(),
                ip_address=fake.ipv4(),
                created_at=created,
                last_used=last_used,
                expires_at=expires,
                is_active=random.choice([True, False]),
                refresh_token=fake.uuid4(),
                access_token=fake.uuid4(),
            )
            sessions.append(session)
        LoginSession.objects.bulk_create(sessions)
        self.stdout.write(f"Created {len(sessions)} login sessions.")

    def seed_login_checkpoints(self, count=50):
        self.stdout.write("Creating login checkpoints...")
        users = list(User.objects.all())
        checkpoints = []
        for _ in range(count):
            user = random.choice(users) if random.random() > 0.3 else None
            email = user.email if user else fake.email()
            created = make_aware(
                fake.date_time_between(start_date="-30d", end_date="now")
            )
            expires = created + timedelta(minutes=random.randint(5, 30))
            checkpoints.append(
                LoginCheckpoint(
                    user=user,
                    email=email,
                    token=fake.uuid4(),
                    created_at=created,
                    expires_at=expires,
                    is_used=random.choice([True, False]),
                )
            )
        LoginCheckpoint.objects.bulk_create(checkpoints)
        self.stdout.write(f"Created {len(checkpoints)} login checkpoints.")

    def seed_otp_requests(self, count=100):
        self.stdout.write("Creating OTP requests...")
        users = list(User.objects.all())
        otp_types = [choice[0] for choice in OTP_TYPES]
        requests = []
        for _ in range(count):
            user = random.choice(users) if random.random() > 0.3 else None
            otp_type = random.choice(otp_types)
            created = make_aware(
                fake.date_time_between(start_date="-30d", end_date="now")
            )
            expires = created + timedelta(minutes=random.randint(5, 30))
            request = OtpRequest(
                user=user,
                otp_code=str(random.randint(100000, 999999)),
                email=user.email if user and otp_type == "email" else fake.email(),
                phone=user.phone_number if user and otp_type == "phone" else fake.phone_number(),
                created_at=created,
                expires_at=expires,
                is_used=random.choice([True, False]),
                attempt_count=random.randint(0, 5),
                type=otp_type,
                is_email_delivered=random.choice([True, False]),
                is_phone_delivered=random.choice([True, False]),
            )
            requests.append(request)
        OtpRequest.objects.bulk_create(requests)
        self.stdout.write(f"Created {len(requests)} OTP requests.")

    def seed_blacklisted_tokens(self, count=80):
        self.stdout.write("Creating blacklisted tokens...")
        users = list(User.objects.all())
        tokens = []
        for _ in range(count):
            user = random.choice(users)
            expires = make_aware(
                fake.date_time_between(start_date="-30d", end_date="+30d")
            )
            created = make_aware(
                fake.date_time_between(start_date="-60d", end_date="now")
            )
            tokens.append(
                BlacklistedAccessToken(
                    jti=fake.uuid4(),
                    user=user,
                    expires_at=expires,
                    created_at=created,
                )
            )
        BlacklistedAccessToken.objects.bulk_create(tokens)
        self.stdout.write(f"Created {len(tokens)} blacklisted tokens.")

    def seed_security_logs(self, count=150):
        self.stdout.write("Creating security logs...")
        users = list(User.objects.all())
        event_types = [
            "login", "logout", "password_change", "2fa_enabled",
            "2fa_disabled", "failed_login"
        ]
        logs = []
        for _ in range(count):
            user = random.choice(users)
            created = make_aware(
                fake.date_time_between(start_date="-60d", end_date="now")
            )
            logs.append(
                SecurityLog(
                    user=user,
                    event_type=random.choice(event_types),
                    ip_address=fake.ipv4(),
                    user_agent=fake.user_agent(),
                    created_at=created,
                    details=fake.sentence(),
                    is_deleted=random.choice([True, False]),
                )
            )
        SecurityLog.objects.bulk_create(logs)
        self.stdout.write(f"Created {len(logs)} security logs.")

    def seed_dating_preferences(self):
        self.stdout.write("Creating dating preferences...")
        users = list(User.objects.all())
        prefs = []
        for user in users:
            if random.random() > 0.7:  # only some users have dating preferences
                continue
            prefs.append(
                DatingPreference(
                    user=user,
                    preferred_age_min=random.randint(18, 30),
                    preferred_age_max=random.randint(25, 50),
                    preferred_gender=random.choice(["male", "female", "other", None]),
                    max_distance_km=random.randint(10, 500),
                    personality_match=random.choice([True, False]),
                    love_language_match=random.choice([True, False]),
                    relationship_goal_match=random.choice([True, False]),
                )
            )
        DatingPreference.objects.bulk_create(prefs, ignore_conflicts=True)
        self.stdout.write("Dating preferences seeded.")

    def seed_matches(self, count=50):
        self.stdout.write("Creating matches...")
        users = list(User.objects.all())
        matches = []
        for _ in range(count):
            user1, user2 = random.sample(users, 2)
            created = make_aware(
                fake.date_time_between(start_date="-60d", end_date="now")
            )
            matches.append(
                Match(
                    user1=user1,
                    user2=user2,
                    created_at=created,
                    is_active=random.choice([True, False])
                )
            )
        Match.objects.bulk_create(matches, ignore_conflicts=True)
        self.stdout.write(f"Created {len(matches)} matches.")

    def seed_dating_messages(self, count=200):
        self.stdout.write("Creating dating messages...")
        matches = list(Match.objects.filter(is_active=True))
        if not matches:
            self.stdout.write("No active matches, skipping.")
            return
        messages = []
        for _ in range(count):
            match = random.choice(matches)
            sender = random.choice([match.user1, match.user2])
            receiver = match.user2 if sender == match.user1 else match.user1
            created = make_aware(
                fake.date_time_between(start_date=match.created_at, end_date="now")
            )
            messages.append(
                DatingMessage(
                    sender=sender,
                    receiver=receiver,
                    content=fake.sentence(),
                    created_at=created,
                    is_read=random.choice([True, False]),
                )
            )
        DatingMessage.objects.bulk_create(messages)
        self.stdout.write(f"Created {len(messages)} dating messages.")

    def seed_analytics(self):
        # UserAnalytics
        self.stdout.write("Creating user analytics...")
        users = list(User.objects.all())
        today = timezone.now().date()
        user_analytics = []
        for user in users[:10]:  # limit to 10 users for speed
            for days_ago in range(30):
                date = today - timedelta(days=days_ago)
                ua = UserAnalytics(
                    user=user,
                    date=date,
                    posts_count=random.randint(0, 5),
                    likes_received=random.randint(0, 20),
                    comments_received=random.randint(0, 10),
                    new_followers=random.randint(0, 8),
                    stories_posted=random.randint(0, 3),
                    recorded_at=timezone.now(),
                )
                user_analytics.append(ua)
        UserAnalytics.objects.bulk_create(user_analytics, ignore_conflicts=True)

        # PlatformAnalytics
        self.stdout.write("Creating platform analytics...")
        platform_analytics = []
        for days_ago in range(30):
            date = today - timedelta(days=days_ago)
            pa = PlatformAnalytics(
                date=date,
                total_users=User.objects.count(),
                active_users=random.randint(50, 200),
                new_posts=random.randint(10, 50),
                new_groups=random.randint(1, 10),
                total_messages=random.randint(100, 500),
                recorded_at=timezone.now(),
                pending_reports=random.randint(0, 10),
                reviewed_reports=random.randint(0, 5),
                resolved_reports=random.randint(0, 5),
                dismissed_reports=random.randint(0, 3),
                active_stories=random.randint(5, 30),
            )
            platform_analytics.append(pa)
        PlatformAnalytics.objects.bulk_create(platform_analytics, ignore_conflicts=True)
        self.stdout.write("Analytics seeded.")

    def seed_object_bookmarks(self, count=150):
        if ObjectBookmark is None:
            return
        self.stdout.write("Creating object bookmarks...")
        users = list(User.objects.all())
        models = [Post, Reel, Story]
        content_types = []
        for model in models:
            if model.objects.exists():
                content_types.append(ContentType.objects.get_for_model(model))
        if not content_types:
            return
        bookmarks = []
        seen = set()
        for _ in range(count):
            user = random.choice(users)
            ct = random.choice(content_types)
            model_class = ct.model_class()
            obj_ids = list(model_class.objects.values_list("id", flat=True))
            if not obj_ids:
                continue
            object_id = random.choice(obj_ids)
            key = (user.id, ct.id, object_id)
            if key in seen:
                continue
            seen.add(key)
            created = make_aware(
                fake.date_time_between(start_date="-60d", end_date="now")
            )
            bookmarks.append(
                ObjectBookmark(
                    user=user,
                    content_type=ct,
                    object_id=object_id,
                    created_at=created,
                )
            )
        ObjectBookmark.objects.bulk_create(bookmarks, ignore_conflicts=True)
        self.stdout.write(f"Created {len(bookmarks)} bookmarks.")

    def seed_object_trend_scores(self, count=200):
        if ObjectTrendScore is None:
            return
        self.stdout.write("Creating object trend scores...")
        models = [Post, Reel, Comment]
        content_types = []
        for model in models:
            if model.objects.exists():
                content_types.append(ContentType.objects.get_for_model(model))
        if not content_types:
            return
        scores = []
        for ct in content_types:
            model_class = ct.model_class()
            for obj in model_class.objects.all():
                if random.random() > 0.5:
                    continue
                score_val = random.uniform(0, 100)
                calculated = make_aware(
                    fake.date_time_between(start_date="-30d", end_date="now")
                )
                scores.append(
                    ObjectTrendScore(
                        content_type=ct,
                        object_id=obj.id,
                        score=score_val,
                        calculated_at=calculated,
                    )
                )
        ObjectTrendScore.objects.bulk_create(scores, ignore_conflicts=True)
        self.stdout.write(f"Created {len(scores)} trend scores.")

    def seed_object_views(self, count=500):
        if ObjectView is None:
            return
        self.stdout.write("Creating object views...")
        users = list(User.objects.all()) + [None]
        models = [Post, Reel, Story]
        content_types = []
        for model in models:
            if model.objects.exists():
                content_types.append(ContentType.objects.get_for_model(model))
        if not content_types:
            return
        views = []
        seen = set()
        for _ in range(count):
            user = random.choice(users) if random.random() < 0.8 else None
            ct = random.choice(content_types)
            model_class = ct.model_class()
            obj_ids = list(model_class.objects.values_list("id", flat=True))
            if not obj_ids:
                continue
            object_id = random.choice(obj_ids)
            if user:
                key = (user.id, ct.id, object_id)
                if key in seen:
                    continue
                seen.add(key)
            viewed_at = make_aware(
                fake.date_time_between(start_date="-60d", end_date="now")
            )
            duration = random.randint(0, 300)
            views.append(
                ObjectView(
                    user=user,
                    content_type=ct,
                    object_id=object_id,
                    viewed_at=viewed_at,
                    duration_seconds=duration,
                )
            )
        ObjectView.objects.bulk_create(views, ignore_conflicts=True)
        self.stdout.write(f"Created {len(views)} object views.")

    def seed_email_templates(self):
        if EmailTemplate is None:
            return
        self.stdout.write("Creating email templates...")
        templates = [
            ("profile_update", "Your profile was updated", "Hello {{ subscriber.email }}, your profile has been updated."),
            ("new_message", "You have a new message", "Hello {{ subscriber.email }}, you have a new message."),
            ("new_like", "Someone liked your post", "Hello {{ subscriber.email }}, your post got a like."),
            ("friend_request", "New friend request", "Hello {{ subscriber.email }}, you have a new friend request."),
            ("login_alert", "New login detected", "Hello {{ subscriber.email }}, a new login was detected."),
        ]
        for name, subject, content in templates:
            EmailTemplate.objects.get_or_create(
                name=name,
                defaults={"subject": subject, "content": content}
            )
        self.stdout.write("Email templates seeded.")

    def seed_notify_logs(self, count=100):
        if NotifyLog is None:
            return
        self.stdout.write("Creating notify logs...")
        users = list(User.objects.all())
        statuses = ["queued", "sent", "failed", "resend"]
        logs = []
        for _ in range(count):
            recipient = random.choice(users).email if users else fake.email()
            subject = fake.sentence(nb_words=5)
            payload = fake.paragraph()
            log_type = random.choice(["profile_update", "new_message", "new_like", "friend_request"])
            status = random.choice(statuses)
            sent_at = make_aware(
                fake.date_time_between(start_date="-30d", end_date="now")
            ) if status == "sent" else None
            logs.append(
                NotifyLog(
                    recipient_email=recipient,
                    subject=subject,
                    payload=payload,
                    type=log_type,
                    status=status,
                    channel="email",
                    priority="normal",
                    sent_at=sent_at,
                    created_at=timezone.now() - timedelta(days=random.randint(0, 30)),
                )
            )
        NotifyLog.objects.bulk_create(logs)
        self.stdout.write(f"Created {len(logs)} notify logs.")

    def seed_audit_logs(self, count=100):
        self.stdout.write("Creating audit logs...")
        users = list(User.objects.all())
        actions = ["CREATE", "UPDATE", "DELETE", "SOFT_DELETE", "RESTORE", "LOGIN", "LOGOUT", "CUSTOM"]
        logs = []
        for _ in range(count):
            user = random.choice(users) if random.random() < 0.8 else None
            created = make_aware(
                fake.date_time_between(start_date="-90d", end_date="now")
            )
            logs.append(
                AuditLog(
                    user=user,
                    action=random.choice(actions),
                    model_name=random.choice(["User", "Post", "Group", "Comment"]),
                    record_id=random.randint(1, 1000),
                    old_data={},
                    new_data={},
                    ip_address=fake.ipv4(),
                    created_at=created,
                    message=fake.sentence(),
                )
            )
        AuditLog.objects.bulk_create(logs)
        self.stdout.write(f"Created {len(logs)} audit logs.")