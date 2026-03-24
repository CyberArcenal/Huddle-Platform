from rest_framework import serializers
from feed.models.post import POST_TYPES
from feed.models.reaction import REACTION_TYPES
from feed.serializers.comment import CommentDisplaySerializer

class ReactionCountSerializer(serializers.Serializer):
    # dynamic fields per reaction type
    like = serializers.IntegerField(default=0)
    love = serializers.IntegerField(default=0)
    care = serializers.IntegerField(default=0)
    haha = serializers.IntegerField(default=0)
    wow = serializers.IntegerField(default=0)
    sad = serializers.IntegerField(default=0)
    angry = serializers.IntegerField(default=0)
    
class ReactionTypeBreakdownSerializer(serializers.Serializer):
    content_type = serializers.CharField()
    reaction_type = serializers.CharField()
    count = serializers.IntegerField()

class ReactionContentTypeBreakdownSerializer(serializers.Serializer):
    content_type = serializers.CharField()
    count = serializers.IntegerField()

class UserReactionStatisticsSerializer(serializers.Serializer):
    total_reactions = serializers.IntegerField()
    type_breakdown = ReactionTypeBreakdownSerializer(many=True)
    content_type_breakdown = ReactionContentTypeBreakdownSerializer(many=True)
    first_reaction_date = serializers.DateTimeField(allow_null=True)

class MostReactedContentSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=[c[0] for c in REACTION_TYPES])
    id = serializers.IntegerField()
    reaction_count = serializers.IntegerField()
    representation = serializers.StringRelatedField()

class MutualReactionsSerializer(serializers.Serializer):
    mutual_posts = serializers.IntegerField()
    mutual_comments = serializers.IntegerField()
    total_mutual_likes = serializers.IntegerField()
    


class ShareContentObjectDetail(serializers.Serializer):
    type = serializers.CharField()
    id = serializers.IntegerField()
    representation = serializers.StringRelatedField()
    
class ContentObject(serializers.Serializer):
    type = serializers.ChoiceField(choices=[c[0] for c in REACTION_TYPES])
    id = serializers.IntegerField()
    content_preview = serializers.StringRelatedField()
    
    
class PostStatsSerializers(serializers.Serializer):
    comment_count = serializers.IntegerField()
    like_count = serializers.IntegerField()
    reaction_count = ReactionCountSerializer()
    privacy = serializers.ChoiceField(choices=["public", "followers", "secret"])
    comments = CommentDisplaySerializer(many=True)
    liked = serializers.BooleanField()
    current_reaction = serializers.StringRelatedField()
    


class UserPostStatisticsSerializer(serializers.Serializer):
    total_posts = serializers.IntegerField()
    public_posts = serializers.IntegerField()
    private_posts = serializers.IntegerField()
    type_breakdown = serializers.ListField()
    first_post_date = serializers.DateTimeField(allow_null=True)


class SearchSerializer(serializers.Serializer):
    query = serializers.CharField(required=True, max_length=255)
    post_type = serializers.ChoiceField(choices=[c[0] for c in POST_TYPES], required=False, allow_null=True)
    limit = serializers.IntegerField(default=20, min_value=1, max_value=100)
    offset = serializers.IntegerField(default=0, min_value=0)


class TrendingPostsSerializer(serializers.Serializer):
    post = serializers.SerializerMethodField()  # Will be overridden in view
    like_count = serializers.IntegerField()
    comment_count = serializers.IntegerField()
