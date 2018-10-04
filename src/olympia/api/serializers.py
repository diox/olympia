from datetime import datetime

from elasticsearch_dsl.response.hit import Hit
from rest_framework.serializers import ModelSerializer

from .fields import ESTranslationSerializerField, TranslationSerializerField


class BaseESSerializer(ModelSerializer):
    """
    A base deserializer that handles ElasticSearch data for a specific model.

    When deserializing, an unbound instance of the model (as defined by
    fake_object) is populated with the ES data in order to work well with
    the parent model serializer (e.g., AddonSerializer).

    """
    # In base classes add the field names we want converted to Python
    # datetime from the Elasticsearch datetime strings.
    datetime_fields = ()

    def __init__(self, *args, **kwargs):
        super(BaseESSerializer, self).__init__(*args, **kwargs)

        # Set all fields as read_only just in case.
        for field_name in self.fields:
            self.fields[field_name].read_only = True

    def get_fields(self):
        """
        Return all fields as normal, with one exception: replace every instance
        of TranslationSerializerField with ESTranslationSerializerField.
        """
        fields = super(BaseESSerializer, self).get_fields()
        for key, field in fields.items():
            if isinstance(field, TranslationSerializerField):
                fields[key] = ESTranslationSerializerField(source=field.source)
        return fields

    def to_representation(self, data):
        # 'explain' can be set by the view in context if it wants debugging
        # information. If set to a truthy value the view needs to use
        # .extra(explain=True) on the Search queryset or it will cause an
        # error when we try to access the explanation data.
        explain = self.context.get('explain')
        # Support `Hit` instances to allow passing in ElasticSearch
        # results directly into the serializer.
        if isinstance(data, Hit):
            if explain:
                score = data.meta['score']
                explanation = data.meta['explanation'].to_dict()
            data = data.to_dict()

        obj = self.fake_object(data)
        result = super(BaseESSerializer, self).to_representation(obj)
        if explain:
            result['_score'] = score
            result['_explanation'] = explanation
        return result

    def fake_object(self, data):
        """
        Create a fake model instance from ES data which serializer fields will
        source from.
        """
        raise NotImplementedError

    def handle_date(self, value):
        if not value:
            return None

        # Don't be picky about microseconds here. We get them some time
        # so we have to support them. So let's strip microseconds and handle
        # the datetime in a unified way.
        value = value.partition('.')[0]
        return datetime.strptime(value, u'%Y-%m-%dT%H:%M:%S')

    def _attach_fields(self, obj, data, field_names):
        """Attach fields to fake instance."""
        for field_name in field_names:
            value = data.get(field_name, None)
            if field_name in self.datetime_fields and value:
                value = self.handle_date(value)
            setattr(obj, field_name, value)
        return obj

    def _attach_translations(self, obj, data, field_names):
        """Deserialize ES translation fields."""
        for field_name in field_names:
            if field_name in self.fields:
                self.fields[field_name].attach_translations(
                    obj, data, field_name)
        return obj
