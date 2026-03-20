from django.utils import timezone
from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.db import transaction, IntegrityError
from django.db.models import Q, Count
from typing import Optional, List, Dict, Any, Tuple

from users.models.user import User
from ..models import AdminLog
import datetime


class AdminLogService:
    """Service for AdminLog model operations"""
    
    @staticmethod
    def log_admin_action(
        admin_user: User,
        action: str,
        reason: str,
        target_user: Optional[User] = None,
        target_id: Optional[int] = None,
        **extra_fields
    ) -> AdminLog:
        """Log an admin action"""
        # Validate action
        valid_actions = [choice[0] for choice in AdminLog.ACTION_CHOICES]
        if action not in valid_actions:
            raise ValidationError(f"Action must be one of {valid_actions}")
        
        # Validate that admin has appropriate permissions
        # (You'll need to integrate with your permission system)
        if not admin_user.is_staff and not admin_user.is_superuser:
            raise ValidationError("Only administrators can perform this action")
        
        # Validate based on action type
        if action in ['user_ban', 'user_warn'] and not target_user:
            raise ValidationError(f"{action} requires a target user")
        
        if action in ['post_remove', 'group_remove'] and not target_id:
            raise ValidationError(f"{action} requires a target ID")
        
        try:
            with transaction.atomic():
                log = AdminLog.objects.create(
                    admin_user=admin_user,
                    action=action,
                    target_user=target_user,
                    target_id=target_id,
                    reason=reason,
                    **extra_fields
                )
                return log
        except IntegrityError as e:
            raise ValidationError(f"Failed to log admin action: {str(e)}")
    
    @staticmethod
    def get_log_by_id(log_id: int) -> Optional[AdminLog]:
        """Retrieve admin log by ID"""
        try:
            return AdminLog.objects.get(id=log_id)
        except AdminLog.DoesNotExist:
            return None
    
    @staticmethod
    def get_admin_logs(
        admin_user: Optional[User] = None,
        action: Optional[str] = None,
        target_user: Optional[User] = None,
        start_date: Optional[datetime.datetime] = None,
        end_date: Optional[datetime.datetime] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[AdminLog]:
        """Get admin logs with filtering options"""
        queryset = AdminLog.objects.select_related('admin_user', 'target_user')
        
        if admin_user:
            queryset = queryset.filter(admin_user=admin_user)
        
        if action:
            queryset = queryset.filter(action=action)
        
        if target_user:
            queryset = queryset.filter(target_user=target_user)
        
        if start_date:
            queryset = queryset.filter(created_at__gte=start_date)
        
        if end_date:
            queryset = queryset.filter(created_at__lte=end_date)
        
        return list(queryset.order_by('-created_at')[offset:offset + limit])
    
    @staticmethod
    def get_recent_admin_actions(
        days: int = 7,
        limit: int = 50
    ) -> List[AdminLog]:
        """Get recent admin actions"""
        time_threshold = timezone.now() - datetime.timedelta(days=days)
        
        return list(
            AdminLog.objects.filter(
                created_at__gte=time_threshold
            ).select_related('admin_user', 'target_user')
            .order_by('-created_at')[:limit]
        )
    
    @staticmethod
    def get_user_admin_logs(
        user: User,
        as_admin: bool = False,
        as_target: bool = True,
        limit: int = 50
    ) -> List[AdminLog]:
        """Get admin logs related to a user (as admin or as target)"""
        queryset = AdminLog.objects.select_related('admin_user', 'target_user')
        
        filters = Q()
        if as_admin:
            filters |= Q(admin_user=user)
        if as_target:
            filters |= Q(target_user=user)
        
        if not filters:
            return []
        
        return list(queryset.filter(filters).order_by('-created_at')[:limit])
    
    @staticmethod
    def get_admin_statistics(
        admin_user: Optional[User] = None,
        days: int = 30
    ) -> Dict[str, Any]:
        """Get statistics about admin actions"""
        time_threshold = timezone.now() - datetime.timedelta(days=days)
        
        queryset = AdminLog.objects.filter(created_at__gte=time_threshold)
        
        if admin_user:
            queryset = queryset.filter(admin_user=admin_user)
        
        # Count by action type
        action_counts = queryset.values('action').annotate(
            count=Count('id')
        ).order_by('-count')
        
        # Count by admin (if no specific admin)
        if not admin_user:
            admin_counts = queryset.values('admin_user__username').annotate(
                count=Count('id')
            ).order_by('-count')[:10]
        else:
            admin_counts = []
        
        # Recent activity
        recent_actions = queryset.order_by('-created_at')[:10]
        
        # Top targets
        top_targets = queryset.exclude(target_user=None).values(
            'target_user__username'
        ).annotate(
            count=Count('id')
        ).order_by('-count')[:10]
        
        # Daily activity
        daily_activity = queryset.extra(
            select={'day': 'date(created_at)'}
        ).values('day').annotate(
            count=Count('id')
        ).order_by('day')
        
        return {
            'period_days': days,
            'total_actions': queryset.count(),
            'action_breakdown': list(action_counts),
            'admin_activity': list(admin_counts),
            'top_targets': list(top_targets),
            'recent_actions': [
                {
                    'id': action.id,
                    'action': action.action,
                    'admin': action.admin_user.username if action.admin_user else None,
                    'target': action.target_user.username if action.target_user else None,
                    'reason': action.reason[:100] + '...' if len(action.reason) > 100 else action.reason,
                    'created_at': action.created_at
                }
                for action in recent_actions
            ],
            'daily_activity': list(daily_activity),
            'most_active_day': max(daily_activity, key=lambda x: x['count']) if daily_activity else None,
            'avg_actions_per_day': queryset.count() / days if days > 0 else 0
        }
    
    @staticmethod
    def ban_user(
        admin_user: User,
        target_user: User,
        reason: str,
        duration_days: Optional[int] = None
    ) -> Tuple[AdminLog, Dict[str, Any]]:
        """Ban a user"""
        # Check if user is already banned (based on your user model)
        if target_user.status == 'suspended' or target_user.status == 'restricted':
            raise ValidationError(f"User {target_user.username} is already banned or restricted")
        
        # Update user status
        from users.services import UserService
        UserService.update_status(target_user, 'suspended')
        
        # Log the action
        log = AdminLogService.log_admin_action(
            admin_user=admin_user,
            action='user_ban',
            target_user=target_user,
            reason=reason
        )
        
        # Create response
        response = {
            'user_id': target_user.id,
            'username': target_user.username,
            'previous_status': 'active',
            'new_status': 'suspended',
            'duration_days': duration_days,
            'banned_at': timezone.now(),
            'banned_by': admin_user.username,
            'reason': reason
        }
        
        return log, response
    
    @staticmethod
    def warn_user(
        admin_user: User,
        target_user: User,
        reason: str,
        severity: str = 'low'  # low, medium, high
    ) -> Tuple[AdminLog, Dict[str, Any]]:
        """Warn a user"""
        # Log the action
        log = AdminLogService.log_admin_action(
            admin_user=admin_user,
            action='user_warn',
            target_user=target_user,
            reason=reason
        )
        
        # You might want to store warnings separately or increment warning count
        response = {
            'user_id': target_user.id,
            'username': target_user.username,
            'warning_severity': severity,
            'warned_at': timezone.now(),
            'warned_by': admin_user.username,
            'reason': reason,
            'warning_count': AdminLogService.get_warning_count(target_user)
        }
        
        return log, response
    
    @staticmethod
    def remove_content(
        admin_user: User,
        content_type: str,
        object_id: int,
        reason: str
    ) -> Tuple[AdminLog, Dict[str, Any]]:
        """Remove content (post, comment, etc.)"""
        # Map content_type to action
        action_map = {
            'post': 'post_remove',
            'group': 'group_remove'
            # Add more as needed
        }
        
        if content_type not in action_map:
            raise ValidationError(f"Cannot remove content of type: {content_type}")
        
        action = action_map[content_type]
        
        # Here you would actually remove the content from your system
        # This is a placeholder - implement based on your content models
        content_removed = True  # Assume success
        
        if not content_removed:
            raise ValidationError(f"Failed to remove {content_type} with ID {object_id}")
        
        # Log the action
        log = AdminLogService.log_admin_action(
            admin_user=admin_user,
            action=action,
            target_id=object_id,
            reason=reason
        )
        
        return log, {
            'content_type': content_type,
            'object_id': object_id,
            'removed_at': timezone.now(),
            'removed_by': admin_user.username,
            'reason': reason
        }
    
    @staticmethod
    def get_warning_count(user: User) -> int:
        """Get number of warnings a user has received"""
        return AdminLog.objects.filter(
            target_user=user,
            action='user_warn'
        ).count()
    
    @staticmethod
    def get_user_ban_history(user: User) -> List[AdminLog]:
        """Get user's ban history"""
        return list(
            AdminLog.objects.filter(
                target_user=user,
                action='user_ban'
            ).order_by('-created_at')
        )
    
    @staticmethod
    def search_admin_logs(
        query: str,
        search_in: List[str] = ['reason', 'admin_username', 'target_username'],
        limit: int = 50
    ) -> List[AdminLog]:
        """Search admin logs"""
        filters = Q()
        
        if 'reason' in search_in:
            filters |= Q(reason__icontains=query)
        
        if 'admin_username' in search_in:
            filters |= Q(admin_user__username__icontains=query)
        
        if 'target_username' in search_in:
            filters |= Q(target_user__username__icontains=query)
        
        return list(
            AdminLog.objects.filter(filters)
            .select_related('admin_user', 'target_user')
            .order_by('-created_at')[:limit]
        )
    
    @staticmethod
    def export_admin_logs(
        start_date: Optional[datetime.datetime] = None,
        end_date: Optional[datetime.datetime] = None,
        format: str = 'json'
    ) -> Dict[str, Any]:
        """Export admin logs for auditing"""
        queryset = AdminLog.objects.select_related('admin_user', 'target_user')
        
        if start_date:
            queryset = queryset.filter(created_at__gte=start_date)
        
        if end_date:
            queryset = queryset.filter(created_at__lte=end_date)
        
        logs = queryset.order_by('-created_at')
        
        if format == 'json':
            data = {
                'exported_at': timezone.now().isoformat(),
                'total_logs': logs.count(),
                'time_range': {
                    'start': start_date.isoformat() if start_date else None,
                    'end': end_date.isoformat() if end_date else None
                },
                'logs': [
                    {
                        'id': log.id,
                        'action': log.action,
                        'admin_user': {
                            'id': log.admin_user.id,
                            'username': log.admin_user.username,
                            'email': log.admin_user.email
                        } if log.admin_user else None,
                        'target_user': {
                            'id': log.target_user.id,
                            'username': log.target_user.username,
                            'email': log.target_user.email
                        } if log.target_user else None,
                        'target_id': log.target_id,
                        'reason': log.reason,
                        'created_at': log.created_at.isoformat()
                    }
                    for log in logs
                ]
            }
            
            return data
        
        # Add other formats (CSV, Excel) as needed
        raise ValueError(f"Unsupported export format: {format}")
    
    @staticmethod
    def cleanup_old_logs(days_to_keep: int = 365) -> int:
        """Delete admin logs older than specified days"""
        cutoff_date = timezone.now() - datetime.timedelta(days=days_to_keep)
        
        old_logs = AdminLog.objects.filter(created_at__lt=cutoff_date)
        count = old_logs.count()
        old_logs.delete()
        
        return count