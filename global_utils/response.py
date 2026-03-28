from typing import List, Optional

from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework import status

import logging

logger = logging.getLogger(__name__)

def _success(data: dict={}, message: str='success', status:int=status.HTTP_200_OK) -> Response:
    # logger.debug(f"Response: {data} Status: {status}")
    return Response({'status': True, 'message': message, 'data': data}, status=status)

def _error(data: list=[], message: str='error', status:int=status.HTTP_404_NOT_FOUND) -> Response:
    # logger.debug(f"Response: {data} Status: {status}")
    return Response({'status': False, 'message': message, 'data': data}, status=status)

class CustomPagination(PageNumberPagination):
    from rest_framework import status

    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100

    def get_paginated_response(
        self,
        data: Optional[List[dict]] = None,
        message: Optional[str] = None,
        success: bool = True,
        response_status: int = status.HTTP_200_OK,
        clean_pagination: bool = False,
        **kwargs,
    ) -> Response:
        if data is None:
            data = []

        pagination_data = {
            "next": self.get_next_link(),
            "previous": self.get_previous_link(),
            "count": self.page.paginator.count,
            "current_page": self.page.number,
            "total_pages": self.page.paginator.num_pages,
            "page_size": self.get_page_size(self.request),
        }

        if clean_pagination:
            pagination_data = {k: v for k, v in pagination_data.items() if v is not None}
            
        response_data = {
            "status": success,
            "message": message or "Success",
            "pagination": pagination_data,
            "data": data,
        }
        
        # Merge extra kwargs into response_data
        if kwargs:
            response_data.update(kwargs)
            
        return Response(response_data, status=response_status)


    def get_paginated_error(self, data=None, message=None, status=False) -> Response:
        if data is None:
            data = []

        response_data = {
            "status": status,
            "message": message or "Error",
            "pagination": {
                "next": False,
                "previous": False,
                "count": 0,
                "current_page": 1,
                "total_pages": 0,
                "page_size": 0,
            },
            "data": data,
        }
        return Response(response_data)
    
    








class CursorPagination:
    """
    Cursor-based pagination that returns a next_cursor.
    """
    page_size = 10
    max_page_size = 100
    page_size_query_param = 'limit'   # use 'limit' as param name

    def __init__(self):
        self.next_cursor = None
        self.items = []

    def paginate_queryset(self, items, next_cursor, request, view=None):
        """
        Store the items and next_cursor for later serialization.
        """
        self.items = items
        self.next_cursor = next_cursor
        self.request = request
        return items

    def get_paginated_response(self, data=None, message=None, status=True, response_status=200) -> Response:
        if data is None:
            data = []
        response_data = {
            "status": status,
            "message": message or "Success",
            "pagination": {
                "next_cursor": self.next_cursor,
                "count": len(self.items),               # number of items in this page
                "page_size": self.page_size,
            },
            "data": data,
        }
        return Response(response_data, status=response_status)
