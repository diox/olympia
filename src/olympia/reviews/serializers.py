from rest_framework import serializers
from rest_framework.relations import PrimaryKeyRelatedField

from olympia.reviews.models import Review
from olympia.users.serializers import BaseUserSerializer
from olympia.versions.models import Version


class BaseReviewSerializer(serializers.ModelSerializer):
    # title and body are TranslatedFields, but there is never more than one
    # translation for each review - it's essentially useless. Because of that
    # we use a simple CharField in the API, hiding the fact that it's a
    # TranslatedField underneath.
    body = serializers.CharField(allow_null=True, required=False)
    title = serializers.CharField(allow_null=True, required=False)
    user = BaseUserSerializer(read_only=True)
    version = PrimaryKeyRelatedField(queryset=Version.unfiltered)

    class Meta:
        model = Review
        fields = ('id', 'body', 'title', 'version', 'user')

    def to_representation(self, obj):
        data = super(BaseReviewSerializer, self).to_representation(obj)
        # For the version, we want to accept PKs for input, but use the version
        # string for output.
        data['version'] = unicode(obj.version.version) if obj.version else None
        return data

    def to_internal_value(self, data):
        data = super(BaseReviewSerializer, self).to_internal_value(data)
        # Get the add-on pk from the URL, no need to pass it as POST data since
        # the URL is always going to have it.
        data['addon_id'] = int(self.context['view'].kwargs['addon_pk'])
        # Get the user from the request, don't allow clients to pick one
        # themselves.
        data['user'] = self.context['request'].user
        return data


class ReviewSerializer(BaseReviewSerializer):
    reply = BaseReviewSerializer(read_only=True)

    class Meta:
        model = Review
        fields = BaseReviewSerializer.Meta.fields + ('rating', 'reply')
