from django.utils import timezone
from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.db import transaction, IntegrityError
from django.db.models import Sum, Avg, Count, F, Q, Max, Min
from typing import Optional, List, Dict, Any, Tuple
from ..models import UserAnalytics, User
import datetime


class UserAnalyticsService:
    """Service for UserAnalytics model operations"""
    
    @staticmethod
    def get_or_create_daily_analytics(user: User, date: Optional[datetime.date] = None) -> UserAnalytics:
        """Get or create daily analytics record for a user"""
        if date is None:
            date = timezone.now().date()
        
        try:
            analytics, created = UserAnalytics.objects.get_or_create(
                user=user,
                date=date,
                defaults={
                    'posts_count': 0,
                    'likes_received': 0,
                    'comments_received': 0,
                    'new_followers': 0,
                    'stories_posted': 0
                }
            )
            return analytics
        except IntegrityError as e:
            # Handle race condition
            return UserAnalytics.objects.get(user=user, date=date)
    
    @staticmethod
    def increment_posts_count(user: User, count: int = 1, date: Optional[datetime.date] = None) -> UserAnalytics:
        """Increment posts count for a user"""
        analytics = UserAnalyticsService.get_or_create_daily_analytics(user, date)
        analytics.posts_count = F('posts_count') + count
        analytics.save()
        analytics.refresh_from_db()
        return analytics
    
    @staticmethod
    def increment_likes_received(user: User, count: int = 1, date: Optional[datetime.date] = None) -> UserAnalytics:
        """Increment likes received count for a user"""
        analytics = UserAnalyticsService.get_or_create_daily_analytics(user, date)
        analytics.likes_received = F('likes_received') + count
        analytics.save()
        analytics.refresh_from_db()
        return analytics
    
    @staticmethod
    def increment_comments_received(user: User, count: int = 1, date: Optional[datetime.date] = None) -> UserAnalytics:
        """Increment comments received count for a user"""
        analytics = UserAnalyticsService.get_or_create_daily_analytics(user, date)
        analytics.comments_received = F('comments_received') + count
        analytics.save()
        analytics.refresh_from_db()
        return analytics
    
    @staticmethod
    def increment_new_followers(user: User, count: int = 1, date: Optional[datetime.date] = None) -> UserAnalytics:
        """Increment new followers count for a user"""
        analytics = UserAnalyticsService.get_or_create_daily_analytics(user, date)
        analytics.new_followers = F('new_followers') + count
        analytics.save()
        analytics.refresh_from_db()
        return analytics
    
    @staticmethod
    def increment_stories_posted(user: User, count: int = 1, date: Optional[datetime.date] = None) -> UserAnalytics:
        """Increment stories posted count for a user"""
        analytics = UserAnalyticsService.get_or_create_daily_analytics(user, date)
        analytics.stories_posted = F('stories_posted') + count
        analytics.save()
        analytics.refresh_from_db()
        return analytics
    
    @staticmethod
    def get_user_daily_analytics(
        user: User,
        date: datetime.date
    ) -> Optional[UserAnalytics]:
        """Get daily analytics for a user on specific date"""
        try:
            return UserAnalytics.objects.get(user=user, date=date)
        except UserAnalytics.DoesNotExist:
            return None
    
    @staticmethod
    def get_user_analytics_range(
        user: User,
        start_date: datetime.date,
        end_date: datetime.date,
        include_empty_days: bool = False
    ) -> List[UserAnalytics]:
        """Get user analytics within a date range"""
        analytics = UserAnalytics.objects.filter(
            user=user,
            date__gte=start_date,
            date__lte=end_date
        ).order_by('date')
        
        if include_empty_days:
            # Create missing days with zero values
            all_dates = []
            current_date = start_date
            while current_date <= end_date:
                all_dates.append(current_date)
                current_date += datetime.timedelta(days=1)
            
            existing_dates = {a.date for a in analytics}
            missing_dates = [d for d in all_dates if d not in existing_dates]
            
            result = list(analytics)
            for date in missing_dates:
                result.append(UserAnalytics(
                    user=user,
                    date=date,
                    posts_count=0,
                    likes_received=0,
                    comments_received=0,
                    new_followers=0,
                    stories_posted=0
                ))
            
            result.sort(key=lambda x: x.date)
            return result
        
        return list(analytics)
    
    @staticmethod
    def get_user_recent_analytics(
        user: User,
        days: int = 30,
        limit: int = 30
    ) -> List[UserAnalytics]:
        """Get recent analytics for a user"""
        start_date = timezone.now().date() - datetime.timedelta(days=days)
        return UserAnalyticsService.get_user_analytics_range(
            user=user,
            start_date=start_date,
            end_date=timezone.now().date()
        )[-limit:]  # Get last 'limit' days
    
    @staticmethod
    def get_user_analytics_summary(
        user: User,
        days: int = 30
    ) -> Dict[str, Any]:
        """Get summarized analytics for a user over a period"""
        start_date = timezone.now().date() - datetime.timedelta(days=days)
        
        analytics = UserAnalytics.objects.filter(
            user=user,
            date__gte=start_date
        ).aggregate(
            total_posts=Sum('posts_count'),
            total_likes_received=Sum('likes_received'),
            total_comments_received=Sum('comments_received'),
            total_new_followers=Sum('new_followers'),
            total_stories_posted=Sum('stories_posted'),
            avg_posts_per_day=Avg('posts_count'),
            avg_likes_per_day=Avg('likes_received'),
            avg_comments_per_day=Avg('comments_received'),
            max_posts_day=Max('posts_count'),
            max_likes_day=Max('likes_received'),
            active_days=Count('date', filter=Q(posts_count__gt=0))
        )
        
        # Calculate engagement rate
        total_interactions = (analytics.get('total_likes_received', 0) or 0) + \
                            (analytics.get('total_comments_received', 0) or 0)
        total_posts = analytics.get('total_posts', 0) or 0
        
        if total_posts > 0:
            avg_engagement_per_post = total_interactions / total_posts
        else:
            avg_engagement_per_post = 0
        
        # Calculate growth metrics
        previous_period_start = start_date - datetime.timedelta(days=days)
        previous_period_end = start_date - datetime.timedelta(days=1)
        
        previous_followers = UserAnalytics.objects.filter(
            user=user,
            date__gte=previous_period_start,
            date__lte=previous_period_end
        ).aggregate(total=Sum('new_followers'))['total'] or 0
        
        current_followers = analytics.get('total_new_followers', 0) or 0
        
        if previous_followers > 0:
            follower_growth_rate = ((current_followers - previous_followers) / previous_followers) * 100
        else:
            follower_growth_rate = current_followers * 100 if current_followers > 0 else 0
        
        return {
            'period_days': days,
            'start_date': start_date,
            'end_date': timezone.now().date(),
            'total_posts': analytics['total_posts'] or 0,
            'total_likes_received': analytics['total_likes_received'] or 0,
            'total_comments_received': analytics['total_comments_received'] or 0,
            'total_new_followers': analytics['total_new_followers'] or 0,
            'total_stories_posted': analytics['total_stories_posted'] or 0,
            'avg_posts_per_day': analytics['avg_posts_per_day'] or 0,
            'avg_likes_per_day': analytics['avg_likes_per_day'] or 0,
            'avg_comments_per_day': analytics['avg_comments_per_day'] or 0,
            'max_posts_day': analytics['max_posts_day'] or 0,
            'max_likes_day': analytics['max_likes_day'] or 0,
            'active_days': analytics['active_days'] or 0,
            'engagement_rate': avg_engagement_per_post,
            'follower_growth_rate': follower_growth_rate,
            'total_interactions': total_interactions,
            'avg_interactions_per_post': avg_engagement_per_post,
            'inactive_days': days - (analytics['active_days'] or 0)
        }
    
    @staticmethod
    def get_user_trends(
        user: User,
        metric: str,
        days: int = 30
    ) -> List[Dict[str, Any]]:
        """Get trend data for a specific metric"""
        valid_metrics = ['posts_count', 'likes_received', 'comments_received', 'new_followers', 'stories_posted']
        if metric not in valid_metrics:
            raise ValidationError(f"Metric must be one of {valid_metrics}")
        
        start_date = timezone.now().date() - datetime.timedelta(days=days)
        
        analytics = UserAnalytics.objects.filter(
            user=user,
            date__gte=start_date
        ).values('date').annotate(
            value=Sum(metric)
        ).order_by('date')
        
        return [
            {
                'date': item['date'],
                'value': item['value'] or 0
            }
            for item in analytics
        ]
    
    @staticmethod
    def get_user_engagement_metrics(
        user: User,
        days: int = 7
    ) -> Dict[str, Any]:
        """Get engagement metrics for a user"""
        start_date = timezone.now().date() - datetime.timedelta(days=days)
        
        # Get analytics data
        analytics = UserAnalytics.objects.filter(
            user=user,
            date__gte=start_date
        )
        
        if not analytics.exists():
            return {
                'total_engagement': 0,
                'daily_engagement': 0,
                'engagement_trend': 'stable',
                'most_engaged_day': None,
                'least_engaged_day': None
            }
        
        # Calculate totals
        total_posts = analytics.aggregate(total=Sum('posts_count'))['total'] or 0
        total_likes = analytics.aggregate(total=Sum('likes_received'))['total'] or 0
        total_comments = analytics.aggregate(total=Sum('comments_received'))['total'] or 0
        
        total_engagement = total_likes + total_comments
        
        # Calculate daily average
        day_count = min(days, analytics.count())
        daily_engagement = total_engagement / day_count if day_count > 0 else 0
        
        # Find most and least engaged days
        most_engaged = analytics.order_by('-likes_received', '-comments_received').first()
        least_engaged = analytics.order_by('likes_received', 'comments_received').first()
        
        # Calculate trend (simple: compare first half vs second half)
        half_point = day_count // 2
        first_half = analytics.order_by('date')[:half_point]
        second_half = analytics.order_by('date')[half_point:]
        
        first_half_engagement = sum([a.likes_received + a.comments_received for a in first_half])
        second_half_engagement = sum([a.likes_received + a.comments_received for a in second_half])
        
        if first_half_engagement > 0:
            trend_percentage = ((second_half_engagement - first_half_engagement) / first_half_engagement) * 100
            if trend_percentage > 10:
                trend = 'increasing'
            elif trend_percentage < -10:
                trend = 'decreasing'
            else:
                trend = 'stable'
        else:
            trend = 'increasing' if second_half_engagement > 0 else 'stable'
        
        return {
            'total_posts': total_posts,
            'total_likes': total_likes,
            'total_comments': total_comments,
            'total_engagement': total_engagement,
            'daily_engagement': daily_engagement,
            'engagement_trend': trend,
            'most_engaged_day': {
                'date': most_engaged.date if most_engaged else None,
                'likes': most_engaged.likes_received if most_engaged else 0,
                'comments': most_engaged.comments_received if most_engaged else 0
            },
            'least_engaged_day': {
                'date': least_engaged.date if least_engaged else None,
                'likes': least_engaged.likes_received if least_engaged else 0,
                'comments': least_engaged.comments_received if least_engaged else 0
            },
            'avg_likes_per_post': total_likes / total_posts if total_posts > 0 else 0,
            'avg_comments_per_post': total_comments / total_posts if total_posts > 0 else 0
        }
    
    @staticmethod
    def get_top_performing_days(
        user: User,
        metric: str = 'likes_received',
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get top performing days for a user"""
        valid_metrics = ['posts_count', 'likes_received', 'comments_received', 'new_followers']
        if metric not in valid_metrics:
            raise ValidationError(f"Metric must be one of {valid_metrics}")
        
        top_days = UserAnalytics.objects.filter(
            user=user,
            **{f'{metric}__gt': 0}
        ).order_by(f'-{metric}')[:limit]
        
        return [
            {
                'date': day.date,
                metric: getattr(day, metric),
                'posts_count': day.posts_count,
                'likes_received': day.likes_received,
                'comments_received': day.comments_received,
                'new_followers': day.new_followers,
                'stories_posted': day.stories_posted
            }
            for day in top_days
        ]
    
    @staticmethod
    def compare_users_analytics(
        user1: User,
        user2: User,
        days: int = 30
    ) -> Dict[str, Any]:
        """Compare analytics between two users"""
        start_date = timezone.now().date() - datetime.timedelta(days=days)
        
        # Get analytics for both users
        user1_analytics = UserAnalyticsService.get_user_analytics_summary(user1, days)
        user2_analytics = UserAnalyticsService.get_user_analytics_summary(user2, days)
        
        # Calculate comparisons
        comparisons = {}
        metrics = ['total_posts', 'total_likes_received', 'total_comments_received', 
                  'total_new_followers', 'total_stories_posted']
        
        for metric in metrics:
            val1 = user1_analytics.get(metric, 0)
            val2 = user2_analytics.get(metric, 0)
            
            if val1 + val2 > 0:
                percentage = (val1 / (val1 + val2)) * 100
            else:
                percentage = 50
            
            comparisons[metric] = {
                'user1': val1,
                'user2': val2,
                'user1_percentage': percentage,
                'user2_percentage': 100 - percentage,
                'difference': val1 - val2
            }
        
        # Calculate engagement comparison
        engagement1 = user1_analytics.get('total_interactions', 0)
        engagement2 = user2_analytics.get('total_interactions', 0)
        
        return {
            'period_days': days,
            'user1': {
                'id': user1.id,
                'username': user1.username,
                'analytics': user1_analytics
            },
            'user2': {
                'id': user2.id,
                'username': user2.username,
                'analytics': user2_analytics
            },
            'comparisons': comparisons,
            'engagement_comparison': {
                'user1_engagement': engagement1,
                'user2_engagement': engagement2,
                'difference': engagement1 - engagement2
            },
            'summary': {
                'more_active': user1 if user1_analytics['active_days'] > user2_analytics['active_days'] else user2,
                'higher_engagement': user1 if engagement1 > engagement2 else user2,
                'faster_growth': user1 if user1_analytics['follower_growth_rate'] > user2_analytics['follower_growth_rate'] else user2
            }
        }
    
    @staticmethod
    def cleanup_old_analytics(days_to_keep: int = 365) -> int:
        """Delete analytics older than specified days"""
        cutoff_date = timezone.now().date() - datetime.timedelta(days=days_to_keep)
        
        old_analytics = UserAnalytics.objects.filter(date__lt=cutoff_date)
        count = old_analytics.count()
        old_analytics.delete()
        
        return count