# global_utils/cursor_pagination.py

import logging
from rest_framework.response import Response

logger = logging.getLogger(__name__)


class CursorPagination:
    """
    Cursor-based pagination that returns a next_cursor.
    Designed for feeds where items are fetched from a merged list (not a queryset).
    """
    page_size = 20
    max_page_size = 100
    page_size_query_param = "limit"   # use 'limit' as param name

    def __init__(self):
        self.next_cursor = None
        self.items = []

    def paginate_queryset(self, items, next_cursor, request, view=None):
        """
        Store the paginated items and cursor for later serialization.
        Returns the items (unchanged) for compatibility.
        """
        self.items = items
        self.next_cursor = next_cursor
        self.request = request
        return items

    def get_paginated_response(self, data):
        """
        Return a response formatted similarly to BasePagination.
        Fields:
        - count: number of items in this page
        - hasNext: boolean indicating if there are more items
        - hasPrev: always false for forward cursor pagination
        - next_cursor: the cursor to use for the next page
        - results: the actual data
        """
        has_next = self.next_cursor is not None
        response = {
            "count": len(self.items),
            "hasNext": has_next,
            "hasPrev": False,
            "next_cursor": self.next_cursor,
            "results": data,
        }
        logger.debug(response)
        return Response(response)