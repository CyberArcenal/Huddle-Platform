# global_utils/pagination.py

import logging
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

logger = logging.getLogger(__name__)


class BasePagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100

    def get_paginated_response(self, data):
        response = {
            "count": self.page.paginator.count,
            "page": self.page.number,
            "hasNext": self.page.has_next(),
            "hasPrev": self.page.has_previous(),
            "next": self.get_next_link(),
            "previous": self.get_previous_link(),
            "results": data,
        }
        logger.debug(response)
        return Response(response)
    def get_paginated_error(self, data=None, message=None, status=False):
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


# Reuse BasePagination for all specific paginators
class StandardResultsSetPagination(BasePagination):
    pass


class AdminPanelPagination(BasePagination):
    pass


class AnalyticsPagination(BasePagination):
    pass


class EventsPagination(BasePagination):
    pass


class GroupsPagination(BasePagination):
    pass


class SearchPagination(BasePagination):
    pass


class StoriesPagination(BasePagination):
    pass


class UsersPagination(BasePagination):
    pass


class NotificationPagination(BasePagination):
    pass


class MessagingPagination(BasePagination):
    pass





