import logging

from rest_framework.pagination import PageNumberPagination, Response

logger = logging.getLogger(__name__)


class StandardResultsSetPagination(PageNumberPagination):
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


class AdminPanelPagination(PageNumberPagination):
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


class AnalyticsPagination(PageNumberPagination):
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


class EventsPagination(PageNumberPagination):
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


class GroupsPagination(PageNumberPagination):
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


class SearchPagination(PageNumberPagination):
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


class StoriesPagination(PageNumberPagination):
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


class UsersPagination(PageNumberPagination):
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


class NotificationPagination(PageNumberPagination):
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


class MessagingPagination(PageNumberPagination):
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
