# search/admin.py

from django.contrib import admin
from .models import SearchHistory


@admin.register(SearchHistory)
class SearchHistoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'query', 'search_type', 'results_count', 'searched_at')
    list_filter = ('search_type', 'searched_at')
    search_fields = ('query', 'user__username')
    raw_id_fields = ('user',)
    date_hierarchy = 'searched_at'
    readonly_fields = ('searched_at',)