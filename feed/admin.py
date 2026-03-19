# # feed/admin.py

# from django.contrib import admin
# from .models import Post, Comment, Reaction


# class CommentInline(admin.TabularInline):
#     """Inline for comments under a post."""
#     model = Comment
#     extra = 0
#     raw_id_fields = ('user', 'parent_comment')
#     readonly_fields = ('created_at',)


# @admin.register(Post)
# class PostAdmin(admin.ModelAdmin):
#     list_display = ('id', 'user', 'post_type', 'privacy', 'is_deleted', 'created_at')
#     list_filter = ('post_type', 'privacy', 'is_deleted', 'created_at')
#     search_fields = ('content', 'user__username')
#     raw_id_fields = ('user',)
#     date_hierarchy = 'created_at'
#     readonly_fields = ('created_at', 'updated_at')
#     inlines = [CommentInline]


# @admin.register(Comment)
# class CommentAdmin(admin.ModelAdmin):
#     list_display = ('id', 'post', 'user', 'parent_comment', 'is_deleted', 'created_at')
#     list_filter = ('is_deleted', 'created_at')
#     search_fields = ('content', 'user__username')
#     raw_id_fields = ('post', 'user', 'parent_comment')
#     date_hierarchy = 'created_at'
#     readonly_fields = ('created_at',)


# @admin.register(Reaction)
# class ReactionAdmin(admin.ModelAdmin):
#     list_display = ('id', 'user', 'content_type', 'object_id', 'created_at')
#     list_filter = ('content_type', 'created_at')
#     search_fields = ('user__username',)
#     raw_id_fields = ('user',)
#     date_hierarchy = 'created_at'
#     readonly_fields = ('created_at',)