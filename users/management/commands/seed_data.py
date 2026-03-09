import random
from datetime import datetime, timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.db import transaction
from faker import Faker

# Import all models from your apps
from admin_pannel.models.base import AdminLog, ReportedContent
from events.models.event_analytics import EventAnalytics
from feed.models.base import Comment, Like, Post
from users.models import (
    UserFollow, BlacklistedAccessToken, SecurityLog, UserSecuritySettings,
    LoginSession, LoginCheckpoint, OtpRequest, UserActivity
)
from groups.models import Group, GroupMember
from messaging.models import Conversation, Message
from stories.models import Story, StoryView
from events.models import Event, EventAttendance
from notifications.models import Notification
from search.models import SearchHistory
from analytics.models import UserAnalytics, PlatformAnalytics

User = get_user_model()
fake = Faker()

# Helper to make a naive datetime aware (assumes UTC)
def make_aware(dt):
    if timezone.is_naive(dt):
        return timezone.make_aware(dt, timezone.get_default_timezone())
    return dt

class Command(BaseCommand):
    help = 'Seeds the database with sample data for development'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Delete all existing data before seeding',
        )

    def handle(self, *args, **options):
        try:
            with transaction.atomic():
                if options['clear']:
                    self.stdout.write('Clearing existing data...')
                    # Order matters to avoid FK constraints
                    models_to_delete = [
                        EventAnalytics, PlatformAnalytics, UserAnalytics,
                        Notification, SearchHistory, AdminLog, ReportedContent,
                        EventAttendance, Event, StoryView, Story,
                        Message, Conversation, Like, Comment, Post,
                        GroupMember, Group, UserFollow,
                        UserActivity, OtpRequest, LoginCheckpoint, LoginSession,
                        UserSecuritySettings, SecurityLog, BlacklistedAccessToken,
                        User
                    ]
                    for model in models_to_delete:
                        model.objects.all().delete()
                    self.stdout.write(self.style.SUCCESS('Database cleared.'))

                self.stdout.write('Seeding data...')
                self.seed_users()
                self.seed_follows()
                self.seed_groups()
                self.seed_posts()
                self.seed_comments()
                self.seed_likes()
                self.seed_conversations()
                self.seed_messages()
                self.seed_stories()
                self.seed_story_views()
                self.seed_events()
                self.seed_event_attendances()
                self.seed_admin_logs()
                self.seed_reported_content()
                self.seed_notifications()
                self.seed_search_history()
                self.seed_analytics()
                self.stdout.write(self.style.SUCCESS('Database seeded successfully!'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error occurred, transaction rolled back: {e}'))
            raise

    def seed_users(self, count=20):
        self.stdout.write('Creating users...')
        users = []
        for i in range(count):
            username = fake.user_name() + str(i)
            email = fake.email()
            # Generate aware datetimes
            date_joined = make_aware(fake.date_time_between(start_date='-2y', end_date='-30d'))
            last_login = make_aware(fake.date_time_between(start_date='-30d', end_date='now'))
            user = User(
                username=username,
                email=email,
                bio=fake.text(max_nb_chars=200),
                date_of_birth=fake.date_of_birth(minimum_age=18, maximum_age=80),
                phone_number=fake.phone_number()[:15],
                is_verified=random.choice([True, False]),
                status=random.choice(['active', 'restricted', 'suspended', 'deleted']),
                profile_picture=None,
                cover_photo=None,
                last_login=last_login,
                date_joined=date_joined,
            )
            user.set_password('password123')
            users.append(user)
        # Create one superuser
        if not User.objects.filter(is_superuser=True).exists():
            admin_joined = timezone.now() - timedelta(days=30)
            admin = User(
                username='admin',
                email='admin@example.com',
                bio='Administrator',
                is_verified=True,
                is_superuser=True,
                is_staff=True,
                status='active',
                date_joined=admin_joined,
                last_login=timezone.now(),
            )
            admin.set_password('admin123')
            users.append(admin)
        User.objects.bulk_create(users, ignore_conflicts=True)
        self.stdout.write(f'Created {len(users)} users.')

    def seed_follows(self, count=100):
        self.stdout.write('Creating follows...')
        users = list(User.objects.all())
        follows = []
        for _ in range(count):
            follower, following = random.sample(users, 2)
            if follower != following and not UserFollow.objects.filter(follower=follower, following=following).exists():
                created = make_aware(fake.date_time_between(start_date='-60d', end_date='now'))
                follows.append(UserFollow(
                    follower=follower,
                    following=following,
                    created_at=created
                ))
        UserFollow.objects.bulk_create(follows, ignore_conflicts=True)
        self.stdout.write(f'Created {len(follows)} follows.')

    def seed_groups(self, count=15):
        self.stdout.write('Creating groups...')
        users = list(User.objects.all())
        groups = []
        for _ in range(count):
            creator = random.choice(users)
            created = make_aware(fake.date_time_between(start_date='-1y', end_date='-30d'))
            group = Group(
                name=fake.catch_phrase()[:50],
                description=fake.text(max_nb_chars=300),
                creator=creator,
                privacy=random.choice(['public', 'private', 'secret']),
                member_count=0,
                created_at=created,
            )
            groups.append(group)
        Group.objects.bulk_create(groups)
        # Add members
        memberships = []
        for group in groups:
            # Add creator as admin
            memberships.append(GroupMember(
                group=group,
                user=group.creator,
                role='admin',
                joined_at=group.created_at
            ))
            # Add random members
            for user in random.sample(users, random.randint(3, 10)):
                if user != group.creator:
                    joined = make_aware(fake.date_time_between(start_date=group.created_at, end_date='now'))
                    memberships.append(GroupMember(
                        group=group,
                        user=user,
                        role=random.choice(['moderator', 'member']),
                        joined_at=joined
                    ))
        GroupMember.objects.bulk_create(memberships, ignore_conflicts=True)
        # Update member counts
        for group in groups:
            group.member_count = group.memberships.count()
            group.save()
        self.stdout.write(f'Created {len(groups)} groups with members.')

    def seed_posts(self, count=100):
        self.stdout.write('Creating posts...')
        users = list(User.objects.all())
        posts = []
        for _ in range(count):
            user = random.choice(users)
            post_type = random.choice(['text', 'image', 'video', 'poll'])
            created = make_aware(fake.date_time_between(start_date='-90d', end_date='now'))
            updated = make_aware(fake.date_time_between(start_date=created, end_date='now'))
            post = Post(
                user=user,
                content=fake.paragraph(nb_sentences=5),
                post_type=post_type,
                media_url=None,
                is_public=random.choice([True, False]),
                is_deleted=False,
                created_at=created,
                updated_at=updated,
                # group field removed – Post model does not have it
            )
            posts.append(post)
        Post.objects.bulk_create(posts)
        self.stdout.write(f'Created {len(posts)} posts.')

    def seed_comments(self, count=200):
        self.stdout.write('Creating comments...')
        users = list(User.objects.all())
        posts = list(Post.objects.all())
        if not posts:
            self.stdout.write(self.style.WARNING('No posts found, skipping comments.'))
            return

        # Determine how many top-level comments and replies
        top_level_count = count // 2
        reply_count = count - top_level_count

        top_comments = []
        # 1. Create top-level comments (no parent)
        for _ in range(top_level_count):
            user = random.choice(users)
            post = random.choice(posts)
            created = make_aware(fake.date_time_between(start_date=post.created_at, end_date='now'))
            top_comments.append(Comment(
                post=post,
                user=user,
                parent_comment=None,
                content=fake.sentence(nb_words=15),
                is_deleted=False,
                created_at=created
            ))

        # Bulk insert top-level comments
        Comment.objects.bulk_create(top_comments)
        self.stdout.write(f'Created {len(top_comments)} top-level comments.')

        # Retrieve all top-level comments (now saved) to use as possible parents
        # We also need all posts again, but we already have them.
        # For replies, we can also allow replies to any existing comment (including newly created replies)
        # but to keep it simple, we'll only allow replies to top-level comments.
        parents = list(Comment.objects.filter(parent_comment__isnull=True))

        replies = []
        for _ in range(reply_count):
            if not parents:
                break  # no parents left, stop creating replies
            user = random.choice(users)
            post = random.choice(posts)
            parent = random.choice(parents)
            created = make_aware(fake.date_time_between(start_date=parent.created_at, end_date='now'))
            replies.append(Comment(
                post=post,
                user=user,
                parent_comment=parent,
                content=fake.sentence(nb_words=15),
                is_deleted=False,
                created_at=created
            ))

        # Bulk insert replies
        if replies:
            Comment.objects.bulk_create(replies)
            self.stdout.write(f'Created {len(replies)} replies.')
        else:
            self.stdout.write('No replies created.')

    def seed_likes(self, count=500):
        self.stdout.write('Creating likes...')
        users = list(User.objects.all())
        posts = list(Post.objects.all())
        comments = list(Comment.objects.all())
        stories = list(Story.objects.all()) if Story.objects.exists() else []
        likes = []
        content_types = []
        for _ in range(count):
            user = random.choice(users)
            content_type = random.choice(['post', 'comment', 'story'])
            obj = None
            if content_type == 'post' and posts:
                obj = random.choice(posts)
            elif content_type == 'comment' and comments:
                obj = random.choice(comments)
            elif content_type == 'story' and stories:
                obj = random.choice(stories)
            if obj:
                if (user.id, content_type, obj.id) not in content_types:
                    content_types.append((user.id, content_type, obj.id))
                    created = make_aware(fake.date_time_between(start_date='-60d', end_date='now'))
                    likes.append(Like(
                        user=user,
                        content_type=content_type,
                        object_id=obj.id,
                        created_at=created
                    ))
        Like.objects.bulk_create(likes, ignore_conflicts=True)
        self.stdout.write(f'Created {len(likes)} likes.')

    def seed_conversations(self, count=30):
        self.stdout.write('Creating conversations...')
        users = list(User.objects.all())
        conversations = []
        for _ in range(count):
            conv_type = random.choice(['direct', 'group'])
            name = fake.catch_phrase()[:50] if conv_type == 'group' else None
            created = make_aware(fake.date_time_between(start_date='-120d', end_date='-30d'))
            updated = make_aware(fake.date_time_between(start_date=created, end_date='now'))
            conv = Conversation(
                name=name,
                conversation_type=conv_type,
                created_at=created,
                updated_at=updated
            )
            conversations.append(conv)
        Conversation.objects.bulk_create(conversations)
        # Add participants
        for conv in conversations:
            if conv.conversation_type == 'direct':
                participants = random.sample(users, 2)
            else:
                participants = random.sample(users, random.randint(3, 8))
            conv.participants.set(participants)
        self.stdout.write(f'Created {len(conversations)} conversations.')

    def seed_messages(self, count=500):
        self.stdout.write('Creating messages...')
        users = list(User.objects.all())
        conversations = list(Conversation.objects.all())
        messages = []
        for _ in range(count):
            conv = random.choice(conversations)
            sender = random.choice(conv.participants.all())
            created = make_aware(fake.date_time_between(start_date=conv.created_at, end_date='now'))
            msg = Message(
                conversation=conv,
                sender=sender,
                content=fake.sentence(nb_words=20),
                media=None,
                media_type=None,
                is_read=random.choice([True, False]),
                is_deleted=False,
                created_at=created
            )
            messages.append(msg)
        Message.objects.bulk_create(messages)
        self.stdout.write(f'Created {len(messages)} messages.')

    def seed_stories(self, count=50):
        self.stdout.write('Creating stories...')
        users = list(User.objects.all())
        stories = []
        now = timezone.now()
        for _ in range(count):
            user = random.choice(users)
            story_type = random.choice(['image', 'video', 'text'])
            expires_at = now + timedelta(hours=random.randint(1, 24))
            created = make_aware(fake.date_time_between(start_date='-3d', end_date='now'))
            story = Story(
                user=user,
                story_type=story_type,
                content=fake.sentence(nb_words=10) if story_type == 'text' else None,
                media_url=None,
                expires_at=expires_at,
                is_active=True,
                created_at=created
            )
            stories.append(story)
        Story.objects.bulk_create(stories)
        self.stdout.write(f'Created {len(stories)} stories.')

    def seed_story_views(self, count=200):
        self.stdout.write('Creating story views...')
        users = list(User.objects.all())
        stories = list(Story.objects.all())
        views = []
        for _ in range(count):
            user = random.choice(users)
            story = random.choice(stories)
            if user != story.user:
                viewed = make_aware(fake.date_time_between(start_date=story.created_at, end_date='now'))
                views.append(StoryView(
                    story=story,
                    user=user,
                    viewed_at=viewed
                ))
        StoryView.objects.bulk_create(views, ignore_conflicts=True)
        self.stdout.write(f'Created {len(views)} story views.')

    def seed_events(self, count=20):
        self.stdout.write('Creating events...')
        users = list(User.objects.all())
        groups = list(Group.objects.all())
        events = []
        for _ in range(count):
            organizer = random.choice(users)
            event_type = random.choice(['public', 'private', 'group'])
            group = random.choice(groups) if event_type == 'group' and groups else None
            start = make_aware(fake.date_time_between(start_date='-30d', end_date='+60d'))
            end = start + timedelta(hours=random.randint(1, 5))
            created = make_aware(fake.date_time_between(start_date='-60d', end_date='now'))
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
                created_at=created
            )
            events.append(event)
        Event.objects.bulk_create(events)
        self.stdout.write(f'Created {len(events)} events.')

    def seed_event_attendances(self, count=150):
        self.stdout.write('Creating event attendances...')
        users = list(User.objects.all())
        events = list(Event.objects.all())
        attendances = []
        for _ in range(count):
            user = random.choice(users)
            event = random.choice(events)
            status = random.choice(['going', 'maybe', 'declined'])
            joined = make_aware(fake.date_time_between(start_date=event.created_at, end_date='now'))
            attendances.append(EventAttendance(
                event=event,
                user=user,
                status=status,
                joined_at=joined
            ))
        EventAttendance.objects.bulk_create(attendances, ignore_conflicts=True)
        # Update counts
        for event in events:
            event.attending_count = event.attendances.filter(status='going').count()
            event.maybe_count = event.attendances.filter(status='maybe').count()
            event.declined_count = event.attendances.filter(status='declined').count()
            event.save()
        self.stdout.write(f'Created {len(attendances)} attendances.')

    def seed_admin_logs(self, count=50):
        self.stdout.write('Creating admin logs...')
        admins = User.objects.filter(is_superuser=True)
        if not admins:
            admins = User.objects.all()[:1]  # fallback
        users = list(User.objects.all())
        logs = []
        for _ in range(count):
            admin = random.choice(admins)
            action = random.choice(['user_ban', 'user_warn', 'post_remove', 'group_remove', 'content_review'])
            target_user = random.choice(users) if random.random() < 0.7 else None
            target_id = random.randint(1, 1000) if not target_user else None
            created = make_aware(fake.date_time_between(start_date='-90d', end_date='now'))
            log = AdminLog(
                admin_user=admin,
                action=action,
                target_user=target_user,
                target_id=target_id,
                reason=fake.sentence(),
                created_at=created
            )
            logs.append(log)
        AdminLog.objects.bulk_create(logs)
        self.stdout.write(f'Created {len(logs)} admin logs.')

    def seed_reported_content(self, count=40):
        self.stdout.write('Creating reported content...')
        users = list(User.objects.all())
        reports = []
        statuses = ['pending', 'reviewed', 'resolved', 'dismissed']
        for _ in range(count):
            reporter = random.choice(users)
            content_type = random.choice(['post', 'comment', 'user', 'group'])
            created = make_aware(fake.date_time_between(start_date='-60d', end_date='now'))
            resolved = None
            if random.random() < 0.5:
                resolved = make_aware(fake.date_time_between(start_date=created, end_date='now'))
            report = ReportedContent(
                reporter=reporter,
                content_type=content_type,
                object_id=random.randint(1, 1000),
                reason=fake.sentence(),
                status=random.choice(statuses),
                created_at=created,
                resolved_at=resolved
            )
            reports.append(report)
        ReportedContent.objects.bulk_create(reports)
        self.stdout.write(f'Created {len(reports)} reports.')

    def seed_notifications(self, count=300):
        self.stdout.write('Creating notifications...')
        users = list(User.objects.all())
        actors = list(User.objects.all())
        notifications = []
        for _ in range(count):
            user = random.choice(users)
            actor = random.choice([a for a in actors if a != user])
            ntype = random.choice(['like', 'comment', 'follow', 'message', 'group_invite', 'event_reminder'])
            created = make_aware(fake.date_time_between(start_date='-30d', end_date='now'))
            notif = Notification(
                user=user,
                actor=actor,
                notification_type=ntype,
                message=fake.sentence(),
                is_read=random.choice([True, False]),
                related_id=random.randint(1, 500),
                related_model=random.choice(['post', 'comment', 'group', 'event']),
                created_at=created
            )
            notifications.append(notif)
        Notification.objects.bulk_create(notifications)
        self.stdout.write(f'Created {len(notifications)} notifications.')

    def seed_search_history(self, count=100):
        self.stdout.write('Creating search history...')
        users = list(User.objects.all()) + [None]  # allow anonymous
        searches = []
        for _ in range(count):
            user = random.choice(users) if random.random() < 0.8 else None
            searched = make_aware(fake.date_time_between(start_date='-60d', end_date='now'))
            search = SearchHistory(
                user=user,
                query=fake.word(),
                search_type=random.choice(['all', 'users', 'groups', 'posts']),
                results_count=random.randint(0, 50),
                searched_at=searched
            )
            searches.append(search)
        SearchHistory.objects.bulk_create(searches)
        self.stdout.write(f'Created {len(searches)} search records.')

    def seed_analytics(self):
        self.stdout.write('Creating analytics...')
        # UserAnalytics: daily for each user over last 30 days
        users = list(User.objects.all())
        today = timezone.now().date()
        user_analytics = []
        for user in users[:10]:  # limit to 10 users for speed
            for days_ago in range(30):
                date = today - timedelta(days=days_ago)
                recorded = timezone.now()
                ua = UserAnalytics(
                    user=user,
                    date=date,
                    posts_count=random.randint(0, 5),
                    likes_received=random.randint(0, 20),
                    comments_received=random.randint(0, 10),
                    new_followers=random.randint(0, 8),
                    stories_posted=random.randint(0, 3),
                    recorded_at=recorded
                )
                user_analytics.append(ua)
        UserAnalytics.objects.bulk_create(user_analytics, ignore_conflicts=True)

        # PlatformAnalytics: daily for last 30 days
        platform_analytics = []
        for days_ago in range(30):
            date = today - timedelta(days=days_ago)
            recorded = timezone.now()
            pa = PlatformAnalytics(
                date=date,
                total_users=User.objects.count(),
                active_users=random.randint(50, 200),
                new_posts=random.randint(10, 50),
                new_groups=random.randint(1, 10),
                total_messages=random.randint(100, 500),
                recorded_at=recorded,
                pending_reports=random.randint(0, 10),
                reviewed_reports=random.randint(0, 5),
                resolved_reports=random.randint(0, 5),
                dismissed_reports=random.randint(0, 3),
                active_stories=random.randint(5, 30)
            )
            platform_analytics.append(pa)
        PlatformAnalytics.objects.bulk_create(platform_analytics, ignore_conflicts=True)

        # EventAnalytics: for each event, daily entries
        events = Event.objects.all()
        event_analytics = []
        for event in events[:5]:  # limit to 5 events
            for days_ago in range(10):
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
                        updated_at=timezone.now()
                    )
                    event_analytics.append(ea)
        EventAnalytics.objects.bulk_create(event_analytics, ignore_conflicts=True)
        self.stdout.write('Analytics created.')