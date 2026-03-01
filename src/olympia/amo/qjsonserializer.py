import json

from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Q

# QUERY scanner (acronym tbd)
#
# Principle:
# - New Scanner in addons-server
# - Uses json schema below to generate a configuration for the ScannerRule,
#   allowing admins to build a Q object for an arbitrary query starting from
#   the version object being scanned
# - Stores a JSON representation of the Q object
# - On scanning, we unserialize that back to a Q object
# - The scanner would then run Version.unfiltered.filter(q_object).exists()
#   and if that returns True then the rule is considered as matching
#
# For instance, using the UI, I could build a scanner rule that triggers for
# every version from add-ons that have more than 4.0 average ratings with more
# than 50 ratings while having less than 10 users.
#
# Or I could build a scanner rule that triggers for every version if the
# version is listed and the add-on has "foo" in the slug, or if the version is
# unlisted and has "bar" in the slug. Or whatever complex nested of conditions
# we want.


class QJSONSerializer:
    """
    Class to serialize and deserialize Q-objects to/from JSON.
    """

    def _serialize(self, obj):
        if not isinstance(obj, Q):
            return obj
        data = {
            'connector': obj.connector,
            'negated': obj.negated,
            'children': [self._serialize(child) for child in obj.children],
        }
        return data

    def serialize(self, obj):
        """
        Serialize a Q object to JSON.
        """
        return json.dumps(self._serialize(obj), cls=DjangoJSONEncoder)

    def _deserialize(self, data):
        children = []
        for child in data['children']:
            if isinstance(child, dict):
                children.append(self._deserialize(child))
            else:
                if isinstance(child, list):
                    child = tuple(child)
                children.append(child)

        obj = Q()
        obj.children = children
        obj.connector = data['connector']
        obj.negated = data['negated']
        return obj

    def deserialize(self, value):
        """
        Deserialize JSON data back to a Q object.

        FIXME: test with
        q = Q(
            Q(addon__status=amo.STATUS_NOMINATED)
            & Q(addon__average_daily_users__lt=100)
        ) & Q(
            Q(channel=amo.CHANNEL_LISTED)
            | Q(addon__versions__file__status=amo.STATUS_DISABLED)
        )
        serializer = QJSONSerializer()
        data = serializer.serialize(q)
        assert data == (
            '{"connector": "AND", "negated": false, "children": [{"connector":'
            ' "AND", "negated": false, "children": [["addon__status", 3], '
            '["addon__average_daily_users__lt", 100]]}, {"connector": "OR", '
            '"negated": false, "children": [["channel", 2], '
            '["addon__versions__file__status", 5]]}]}')
        assert serializer.deserialize(data) == q
        """
        data = json.loads(value)
        return self._deserialize(data)

    # FIXME: the following schema should represent reality, but there is a bug
    # in react-json-form with oneOf and prevents conditions from being selected
    # in the dropdown between nested/conditions.
    #
    # This looks like a bug in react-json-form:    #
    # Replacing 'keys' by 'properties' and testing that schema in
    # https://rjsf-team.github.io/react-jsonschema-form/ sort of works, though
    # it also seem to break at some point.
    #
    # Similar issues:
    # - https://github.com/bhch/react-json-form/issues/107 but the fix
    #   suggested in that one seems specific to consts.
    # - https://github.com/bhch/react-json-form/issues/71 but adding 'default'
    #   in a bunch of places doesn't seem to help.
    #
    # Worth filing a bug, especially as this is occurring when trying to
    # represent a Q object as a JSON schema after all, and the author of
    # react-json-form is also the author of django-jsonform...
    #
    # Note: for `value` we could expand the `oneOf` to other types (booleans,
    # nulls), but let's wait until the bug we're seeing with `oneOf` on
    # `children` is addressed.
    #
    #
    # FIXME: a cool thing to do would be an autocomplete on the key in the
    # conditions.
    json_schema = """
        {
          "type": "object",
          "keys": {
            "connector": {
              "type": "string",
              "enum": [
                "AND",
                "OR",
                "XOR"
              ],
              "default": "AND"
            },
            "negated": {
              "type": "boolean",
              "default": false
            },
            "children": {
              "oneOf": [
                {
                  "title": "Nested",
                  "type": "array",
                  "items": {
                    "$ref": "#"
                  }
                },
                {
                  "title": "Conditions",
                  "type": "array",
                  "items": {
                    "type": "object",
                    "keys": {
                      "key": {
                        "type": "string"
                      },
                      "value": {
                        "oneOf": [
                          {
                            "type": "integer",
                            "title": "Integer value"
                          },
                          {
                            "type": "string",
                            "title": "String value"
                          }
                        ]
                      }
                    }
                  }
                }
              ]
            }
          }
        }
    """
