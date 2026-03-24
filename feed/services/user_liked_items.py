# feed/services/user_liked_items.py

from typing import List, Dict, Any, Tuple
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from feed.services.reaction import ReactionService
from feed.utils.reaction import can_view_content


# Map model class name (lowercase) to feed 'type' keys used by SINGLE_ITEM_SERIALIZER
MODEL_NAME_TO_FEED_TYPE = {
    "post": "post",
    "reel": "reel",
    "userimage": "user_image",
    "user_image": "user_image",
    "share": "share",
    "comment": "comment",
    # add other mappings as needed
}


class UserLikedItemsService:
    @staticmethod
    def get_liked_items(
        target_user,
        requester,
        page: int = 1,
        page_size: int = 20
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Returns a page of liked items formatted for the feed:
        Each row is {"type": "<feed_type>", "item": <model instance>}

        - Pages reactions at DB level (if ReactionService exposes a queryset).
        - Batch-fetches content objects per content type to avoid N+1 queries.
        - Applies can_view_content filtering.
        - Returns (rows, total_count).
        """

        # normalize paging
        page = max(int(page) if page else 1, 1)
        page_size = max(int(page_size) if page_size else 20, 1)
        offset = (page - 1) * page_size

        # 1) Try to get a queryset from ReactionService for efficient DB pagination
        try:
            reactions_qs = ReactionService.get_user_reactions_queryset(user=target_user)
        except AttributeError:
            # Fallback: ReactionService only returns list
            reactions = ReactionService.get_user_reactions(user=target_user, limit=None, offset=0)
            reactions = sorted(reactions, key=lambda r: r.created_at, reverse=True)
            total = len(reactions)
            page_reactions = reactions[offset:offset + page_size]
        else:
            total = reactions_qs.count()
            page_reactions = list(reactions_qs.order_by('-created_at')[offset:offset + page_size])

        if not page_reactions:
            return [], total

        # 2) Group page reactions by content_type_id for batch fetching
        grouped = {}
        for r in page_reactions:
            grouped.setdefault(r.content_type_id, []).append(r)

        # 3) Batch fetch objects for each content type
        objects_map = {}  # (ct_id, object_id) -> instance
        for ct_id, reactions_list in grouped.items():
            try:
                ct = ContentType.objects.get_for_id(ct_id)
            except ContentType.DoesNotExist:
                continue

            model_class = ct.model_class()
            if not model_class:
                continue

            object_ids = [r.object_id for r in reactions_list]
            qs = model_class.objects.filter(id__in=object_ids)

            # Prefetch/select related to reduce N+1 in serializers.
            # Adjust these to match your actual relations.
            try:
                qs = qs.select_related('user')
            except Exception:
                pass
            try:
                qs = qs.prefetch_related('media')
            except Exception:
                pass

            for obj in qs:
                objects_map[(ct_id, obj.id)] = obj

        # 4) Build feed rows preserving reaction order and applying privacy checks
        rows: List[Dict[str, Any]] = []
        for reaction in page_reactions:
            key = (reaction.content_type_id, reaction.object_id)
            obj = objects_map.get(key)
            if not obj:
                continue

            # Privacy check: skip if requester cannot view
            try:
                allowed = can_view_content(requester, obj)
            except Exception:
                # If helper missing or fails, be conservative and skip
                allowed = False

            if not allowed:
                continue

            model_name = obj.__class__.__name__.lower()
            feed_type = MODEL_NAME_TO_FEED_TYPE.get(model_name, model_name)

            rows.append({
                "type": feed_type,
                "item": obj,
            })

        return rows, total
