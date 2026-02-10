from django.utils import timezone
from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.db import transaction, IntegrityError
from django.db.models import Sum, Avg, Count, F, Q, Max, Min, StdDev, Variance
from typing import Optional, List, Dict, Any, Tuple
from ..models import PlatformAnalytics, UserAnalytics, User
import datetime


class PlatformAnalyticsService:
    """Service for PlatformAnalytics model operations"""
    
    @staticmethod
    def get_or_create_daily_analytics(date: Optional[datetime.date] = None) -> PlatformAnalytics:
        """Get or create daily platform analytics record"""
        if date is None:
            date = timezone.now().date()
        
        try:
            analytics, created = PlatformAnalytics.objects.get_or_create(
                date=date,
                defaults={
                    'total_users': 0,
                    'active_users': 0,
                    'new_posts': 0,
                    'new_groups': 0,
                    'total_messages': 0
                }
            )
            return analytics
        except IntegrityError as e:
            # Handle race condition
            return PlatformAnalytics.objects.get(date=date)
    
    @staticmethod
    def update_total_users(count: int, date: Optional[datetime.date] = None) -> PlatformAnalytics:
        """Update total users count"""
        analytics = PlatformAnalyticsService.get_or_create_daily_analytics(date)
        analytics.total_users = count
        analytics.save()
        return analytics
    
    @staticmethod
    def update_active_users(count: int, date: Optional[datetime.date] = None) -> PlatformAnalytics:
        """Update active users count"""
        analytics = PlatformAnalyticsService.get_or_create_daily_analytics(date)
        analytics.active_users = count
        analytics.save()
        return analytics
    
    @staticmethod
    def increment_new_posts(count: int = 1, date: Optional[datetime.date] = None) -> PlatformAnalytics:
        """Increment new posts count"""
        analytics = PlatformAnalyticsService.get_or_create_daily_analytics(date)
        analytics.new_posts = F('new_posts') + count
        analytics.save()
        analytics.refresh_from_db()
        return analytics
    
    @staticmethod
    def increment_new_groups(count: int = 1, date: Optional[datetime.date] = None) -> PlatformAnalytics:
        """Increment new groups count"""
        analytics = PlatformAnalyticsService.get_or_create_daily_analytics(date)
        analytics.new_groups = F('new_groups') + count
        analytics.save()
        analytics.refresh_from_db()
        return analytics
    
    @staticmethod
    def increment_total_messages(count: int = 1, date: Optional[datetime.date] = None) -> PlatformAnalytics:
        """Increment total messages count"""
        analytics = PlatformAnalyticsService.get_or_create_daily_analytics(date)
        analytics.total_messages = F('total_messages') + count
        analytics.save()
        analytics.refresh_from_db()
        return analytics
    
    @staticmethod
    def get_daily_analytics(date: datetime.date) -> Optional[PlatformAnalytics]:
        """Get platform analytics for specific date"""
        try:
            return PlatformAnalytics.objects.get(date=date)
        except PlatformAnalytics.DoesNotExist:
            return None
    
    @staticmethod
    def get_analytics_range(
        start_date: datetime.date,
        end_date: datetime.date,
        include_empty_days: bool = False
    ) -> List[PlatformAnalytics]:
        """Get platform analytics within a date range"""
        analytics = PlatformAnalytics.objects.filter(
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
                result.append(PlatformAnalytics(
                    date=date,
                    total_users=0,
                    active_users=0,
                    new_posts=0,
                    new_groups=0,
                    total_messages=0
                ))
            
            result.sort(key=lambda x: x.date)
            return result
        
        return list(analytics)
    
    @staticmethod
    def get_recent_analytics(days: int = 30, limit: int = 30) -> List[PlatformAnalytics]:
        """Get recent platform analytics"""
        start_date = timezone.now().date() - datetime.timedelta(days=days)
        return PlatformAnalyticsService.get_analytics_range(
            start_date=start_date,
            end_date=timezone.now().date()
        )[-limit:]  # Get last 'limit' days
    
    @staticmethod
    def get_platform_summary(days: int = 30) -> Dict[str, Any]:
        """Get summarized platform analytics over a period"""
        start_date = timezone.now().date() - datetime.timedelta(days=days)
        
        analytics = PlatformAnalytics.objects.filter(
            date__gte=start_date
        ).aggregate(
            avg_total_users=Avg('total_users'),
            avg_active_users=Avg('active_users'),
            total_new_posts=Sum('new_posts'),
            total_new_groups=Sum('new_groups'),
            total_messages=Sum('total_messages'),
            peak_active_users=Max('active_users'),
            peak_new_posts=Max('new_posts'),
            min_active_users=Min('active_users'),
            avg_daily_growth=Avg(F('total_users') - F('total_users'))  # Placeholder, would need previous day data
        )
        
        # Calculate active user percentage
        avg_total_users = analytics.get('avg_total_users', 0) or 0
        avg_active_users = analytics.get('avg_active_users', 0) or 0
        
        if avg_total_users > 0:
            active_user_percentage = (avg_active_users / avg_total_users) * 100
        else:
            active_user_percentage = 0
        
        # Calculate growth trends (simplified)
        first_day = PlatformAnalytics.objects.filter(
            date__gte=start_date
        ).order_by('date').first()
        
        last_day = PlatformAnalytics.objects.filter(
            date__gte=start_date
        ).order_by('-date').first()
        
        if first_day and last_day:
            user_growth = last_day.total_users - first_day.total_users
            user_growth_rate = (user_growth / first_day.total_users * 100) if first_day.total_users > 0 else 0
        else:
            user_growth = 0
            user_growth_rate = 0
        
        # Calculate activity metrics
        active_days = PlatformAnalytics.objects.filter(
            date__gte=start_date,
            active_users__gt=0
        ).count()
        
        return {
            'period_days': days,
            'start_date': start_date,
            'end_date': timezone.now().date(),
            'avg_total_users': avg_total_users,
            'avg_active_users': avg_active_users,
            'active_user_percentage': active_user_percentage,
            'total_new_posts': analytics['total_new_posts'] or 0,
            'total_new_groups': analytics['total_new_groups'] or 0,
            'total_messages': analytics['total_messages'] or 0,
            'peak_active_users': analytics['peak_active_users'] or 0,
            'peak_new_posts': analytics['peak_new_posts'] or 0,
            'min_active_users': analytics['min_active_users'] or 0,
            'user_growth': user_growth,
            'user_growth_rate': user_growth_rate,
            'active_days': active_days,
            'inactive_days': days - active_days,
            'avg_posts_per_day': (analytics['total_new_posts'] or 0) / days if days > 0 else 0,
            'avg_messages_per_day': (analytics['total_messages'] or 0) / days if days > 0 else 0,
            'avg_groups_per_day': (analytics['total_new_groups'] or 0) / days if days > 0 else 0
        }
    
    @staticmethod
    def get_platform_trends(
        metric: str,
        days: int = 30,
        moving_average: int = 7
    ) -> List[Dict[str, Any]]:
        """Get trend data for a specific platform metric"""
        valid_metrics = ['total_users', 'active_users', 'new_posts', 'new_groups', 'total_messages']
        if metric not in valid_metrics:
            raise ValidationError(f"Metric must be one of {valid_metrics}")
        
        start_date = timezone.now().date() - datetime.timedelta(days=days + moving_average)
        
        analytics = PlatformAnalytics.objects.filter(
            date__gte=start_date
        ).values('date').annotate(
            value=Sum(metric)
        ).order_by('date')
        
        # Convert to list and calculate moving average
        data = list(analytics)
        result = []
        
        for i in range(moving_average, len(data)):
            current_date = data[i]['date']
            current_value = data[i]['value'] or 0
            
            # Calculate moving average
            window = data[i-moving_average:i]
            window_avg = sum([d['value'] or 0 for d in window]) / moving_average
            
            result.append({
                'date': current_date,
                'value': current_value,
                'moving_average': window_avg,
                'trend': 'up' if current_value > window_avg else 'down' if current_value < window_avg else 'stable'
            })
        
        return result
    
    @staticmethod
    def get_platform_health_metrics(days: int = 7) -> Dict[str, Any]:
        """Get platform health metrics"""
        summary = PlatformAnalyticsService.get_platform_summary(days)
        
        # Calculate health scores (0-100)
        # Active user score
        active_user_score = min(100, (summary['active_user_percentage'] / 50) * 100)
        
        # Growth score
        growth_score = min(100, max(0, summary['user_growth_rate'] * 10))
        
        # Activity score
        activity_days_ratio = summary['active_days'] / days if days > 0 else 0
        activity_score = activity_days_ratio * 100
        
        # Content creation score
        avg_posts_per_day = summary['avg_posts_per_day']
        posts_score = min(100, avg_posts_per_day * 10)  # Adjust multiplier as needed
        
        # Engagement score (simplified)
        messages_per_user = summary['avg_messages_per_day'] / summary['avg_active_users'] if summary['avg_active_users'] > 0 else 0
        engagement_score = min(100, messages_per_user * 20)  # Adjust multiplier as needed
        
        # Overall health score
        overall_health = (
            active_user_score * 0.3 +
            growth_score * 0.25 +
            activity_score * 0.2 +
            posts_score * 0.15 +
            engagement_score * 0.1
        )
        
        # Determine health status
        if overall_health >= 80:
            health_status = 'excellent'
        elif overall_health >= 60:
            health_status = 'good'
        elif overall_health >= 40:
            health_status = 'fair'
        elif overall_health >= 20:
            health_status = 'poor'
        else:
            health_status = 'critical'
        
        return {
            'overall_health_score': overall_health,
            'health_status': health_status,
            'component_scores': {
                'active_users': active_user_score,
                'growth': growth_score,
                'activity': activity_score,
                'content_creation': posts_score,
                'engagement': engagement_score
            },
            'summary': summary,
            'recommendations': PlatformAnalyticsService.get_health_recommendations(health_status, summary)
        }
    
    @staticmethod
    def get_health_recommendations(health_status: str, summary: Dict[str, Any]) -> List[str]:
        """Get recommendations based on platform health"""
        recommendations = []
        
        if health_status == 'critical':
            recommendations.extend([
                "Immediate attention needed: User growth is negative",
                "Consider promotional campaigns to attract new users",
                "Review platform stability and user experience"
            ])
        
        if summary['active_user_percentage'] < 30:
            recommendations.append(
                f"Low active user rate ({summary['active_user_percentage']:.1f}%). "
                "Consider improving user engagement features."
            )
        
        if summary['avg_posts_per_day'] < 10:
            recommendations.append(
                f"Low content creation rate ({summary['avg_posts_per_day']:.1f} posts/day). "
                "Consider incentives for content creation."
            )
        
        if summary['active_days'] / summary['period_days'] < 0.7:
            recommendations.append(
                "Platform has inactive days. Consider daily engagement features."
            )
        
        return recommendations
    
    @staticmethod
    def get_top_performing_days(
        metric: str = 'active_users',
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get top performing days for the platform"""
        valid_metrics = ['total_users', 'active_users', 'new_posts', 'new_groups', 'total_messages']
        if metric not in valid_metrics:
            raise ValidationError(f"Metric must be one of {valid_metrics}")
        
        top_days = PlatformAnalytics.objects.filter(
            **{f'{metric}__gt': 0}
        ).order_by(f'-{metric}')[:limit]
        
        return [
            {
                'date': day.date,
                metric: getattr(day, metric),
                'total_users': day.total_users,
                'active_users': day.active_users,
                'new_posts': day.new_posts,
                'new_groups': day.new_groups,
                'total_messages': day.total_messages
            }
            for day in top_days
        ]
    
    @staticmethod
    def get_correlation_analysis(
        metric1: str,
        metric2: str,
        days: int = 30
    ) -> Dict[str, Any]:
        """Analyze correlation between two metrics"""
        valid_metrics = ['total_users', 'active_users', 'new_posts', 'new_groups', 'total_messages']
        if metric1 not in valid_metrics or metric2 not in valid_metrics:
            raise ValidationError(f"Metrics must be one of {valid_metrics}")
        
        start_date = timezone.now().date() - datetime.timedelta(days=days)
        
        data = PlatformAnalytics.objects.filter(
            date__gte=start_date
        ).values('date', metric1, metric2).order_by('date')
        
        if len(data) < 2:
            return {
                'correlation': 0,
                'strength': 'insufficient_data',
                'message': 'Not enough data for correlation analysis'
            }
        
        # Calculate simple correlation (Pearson's r simplified)
        values1 = [d[metric1] or 0 for d in data]
        values2 = [d[metric2] or 0 for d in data]
        
        # Calculate means
        mean1 = sum(values1) / len(values1)
        mean2 = sum(values2) / len(values2)
        
        # Calculate covariance and variances
        covariance = sum((v1 - mean1) * (v2 - mean2) for v1, v2 in zip(values1, values2)) / len(values1)
        variance1 = sum((v - mean1) ** 2 for v in values1) / len(values1)
        variance2 = sum((v - mean2) ** 2 for v in values2) / len(values2)
        
        # Calculate correlation
        if variance1 > 0 and variance2 > 0:
            correlation = covariance / (variance1 ** 0.5 * variance2 ** 0.5)
        else:
            correlation = 0
        
        # Interpret correlation
        abs_corr = abs(correlation)
        if abs_corr >= 0.7:
            strength = 'strong'
        elif abs_corr >= 0.4:
            strength = 'moderate'
        elif abs_corr >= 0.2:
            strength = 'weak'
        else:
            strength = 'negligible'
        
        direction = 'positive' if correlation > 0 else 'negative' if correlation < 0 else 'none'
        
        return {
            'correlation': correlation,
            'strength': strength,
            'direction': direction,
            'metric1': metric1,
            'metric2': metric2,
            'period_days': days,
            'data_points': len(data),
            'interpretation': f"{direction.capitalize()} {strength} correlation between {metric1} and {metric2}"
        }
    
    @staticmethod
    def generate_daily_report(date: Optional[datetime.date] = None) -> Dict[str, Any]:
        """Generate daily platform analytics report"""
        if date is None:
            date = timezone.now().date()
        
        # Get daily analytics
        daily = PlatformAnalyticsService.get_daily_analytics(date)
        
        if not daily:
            daily = PlatformAnalytics(
                date=date,
                total_users=0,
                active_users=0,
                new_posts=0,
                new_groups=0,
                total_messages=0
            )
        
        # Get previous day for comparison
        prev_date = date - datetime.timedelta(days=1)
        prev_daily = PlatformAnalyticsService.get_daily_analytics(prev_date)
        
        # Calculate changes
        changes = {}
        metrics = ['total_users', 'active_users', 'new_posts', 'new_groups', 'total_messages']
        
        for metric in metrics:
            current = getattr(daily, metric)
            previous = getattr(prev_daily, metric) if prev_daily else 0
            
            change = current - previous
            change_percentage = (change / previous * 100) if previous > 0 else (100 if current > 0 else 0)
            
            changes[metric] = {
                'current': current,
                'previous': previous,
                'change': change,
                'change_percentage': change_percentage,
                'trend': 'up' if change > 0 else 'down' if change < 0 else 'stable'
            }
        
        # Get user analytics summary for the day
        user_activity = UserAnalytics.objects.filter(date=date).aggregate(
            total_posts=Sum('posts_count'),
            total_likes=Sum('likes_received'),
            total_comments=Sum('comments_received'),
            active_users_count=Count('user', distinct=True)
        )
        
        return {
            'date': date,
            'daily_metrics': {
                'total_users': daily.total_users,
                'active_users': daily.active_users,
                'new_posts': daily.new_posts,
                'new_groups': daily.new_groups,
                'total_messages': daily.total_messages
            },
            'changes': changes,
            'user_activity': user_activity,
            'active_user_rate': (daily.active_users / daily.total_users * 100) if daily.total_users > 0 else 0,
            'messages_per_active_user': (daily.total_messages / daily.active_users) if daily.active_users > 0 else 0,
            'report_generated_at': timezone.now()
        }
    
    @staticmethod
    def cleanup_old_analytics(days_to_keep: int = 730) -> int:
        """Delete platform analytics older than specified days"""
        cutoff_date = timezone.now().date() - datetime.timedelta(days=days_to_keep)
        
        old_analytics = PlatformAnalytics.objects.filter(date__lt=cutoff_date)
        count = old_analytics.count()
        old_analytics.delete()
        
        return count