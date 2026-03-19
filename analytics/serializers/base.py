from rest_framework import serializers
import datetime

# All utility serializers remain exactly as they were, except the model serializers are removed.
# Below is a truncated version showing only the utility ones (kept intact).

class PlatformAnalyticsSummarySerializer(serializers.Serializer):
    period_days = serializers.IntegerField()
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    avg_total_users = serializers.FloatField()
    avg_active_users = serializers.FloatField()
    active_user_percentage = serializers.FloatField()
    total_new_posts = serializers.IntegerField()
    total_new_groups = serializers.IntegerField()
    total_messages = serializers.IntegerField()
    peak_active_users = serializers.IntegerField()
    peak_new_posts = serializers.IntegerField()
    min_active_users = serializers.IntegerField()
    user_growth = serializers.IntegerField()
    user_growth_rate = serializers.FloatField()
    active_days = serializers.IntegerField()
    inactive_days = serializers.IntegerField()
    avg_posts_per_day = serializers.FloatField()
    avg_messages_per_day = serializers.FloatField()
    avg_groups_per_day = serializers.FloatField()

class PlatformHealthSerializer(serializers.Serializer):
    overall_health_score = serializers.FloatField()
    health_status = serializers.CharField()
    component_scores = serializers.DictField(child=serializers.FloatField())
    summary = PlatformAnalyticsSummarySerializer()
    recommendations = serializers.ListField(child=serializers.CharField())

class PlatformTrendSerializer(serializers.Serializer):
    date = serializers.DateField()
    value = serializers.FloatField()
    moving_average = serializers.FloatField()
    trend = serializers.CharField()

class PlatformTopDaySerializer(serializers.Serializer):
    date = serializers.DateField()
    total_users = serializers.IntegerField()
    active_users = serializers.IntegerField()
    new_posts = serializers.IntegerField()
    new_groups = serializers.IntegerField()
    total_messages = serializers.IntegerField()

class PlatformCorrelationSerializer(serializers.Serializer):
    correlation = serializers.FloatField()
    strength = serializers.CharField()
    direction = serializers.CharField()
    metric1 = serializers.CharField()
    metric2 = serializers.CharField()
    period_days = serializers.IntegerField()
    data_points = serializers.IntegerField()
    interpretation = serializers.CharField()

class DailyReportSerializer(serializers.Serializer):
    date = serializers.DateField()
    daily_metrics = serializers.DictField()
    changes = serializers.DictField()
    user_activity = serializers.DictField()
    active_user_rate = serializers.FloatField()
    messages_per_active_user = serializers.FloatField()
    report_generated_at = serializers.DateTimeField()

class UserAnalyticsSummarySerializer(serializers.Serializer):
    period_days = serializers.IntegerField()
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    total_posts = serializers.IntegerField()
    total_likes_received = serializers.IntegerField()
    total_comments_received = serializers.IntegerField()
    total_new_followers = serializers.IntegerField()
    total_stories_posted = serializers.IntegerField()
    avg_posts_per_day = serializers.FloatField()
    avg_likes_per_day = serializers.FloatField()
    avg_comments_per_day = serializers.FloatField()
    max_posts_day = serializers.IntegerField()
    max_likes_day = serializers.IntegerField()
    active_days = serializers.IntegerField()
    engagement_rate = serializers.FloatField()
    follower_growth_rate = serializers.FloatField()
    total_interactions = serializers.IntegerField()
    avg_interactions_per_post = serializers.FloatField()
    inactive_days = serializers.IntegerField()

class UserTrendSerializer(serializers.Serializer):
    date = serializers.DateField()
    value = serializers.IntegerField()

class UserEngagementSerializer(serializers.Serializer):
    total_posts = serializers.IntegerField()
    total_likes = serializers.IntegerField()
    total_comments = serializers.IntegerField()
    total_engagement = serializers.IntegerField()
    daily_engagement = serializers.FloatField()
    engagement_trend = serializers.CharField()
    most_engaged_day = serializers.DictField()
    least_engaged_day = serializers.DictField()
    avg_likes_per_post = serializers.FloatField()
    avg_comments_per_post = serializers.FloatField()

class UserTopDaySerializer(serializers.Serializer):
    date = serializers.DateField()
    posts_count = serializers.IntegerField()
    likes_received = serializers.IntegerField()
    comments_received = serializers.IntegerField()
    new_followers = serializers.IntegerField()
    stories_posted = serializers.IntegerField()

class UserCompareSerializer(serializers.Serializer):
    period_days = serializers.IntegerField()
    user1 = serializers.DictField()
    user2 = serializers.DictField()
    comparisons = serializers.DictField()
    engagement_comparison = serializers.DictField()
    summary = serializers.DictField()