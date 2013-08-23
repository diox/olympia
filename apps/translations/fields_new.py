import base64
import pickle
import uuid

from django.conf import settings
from django.db import models
from django.db.models.fields import CharField
from django.utils import six, translation as translation_utils
from django.utils.translation.trans_real import to_language

import redisutils


redis = redisutils.connections['master']


def save_new_translations(key, sender):
    print 'save_new_translations'
    print '->', key, sender
    #redis.set(key, store_pickle(value))


def get_pickle(value):
    return pickle.loads(base64.b64decode(value))


def store_pickle(value):
    return base64.b64encode(pickle.dumps(value))


def make_new_key():
    return uuid.uuid4().hex


def get_translation(instance, value):
    key = 'l10n:%s:%s' % (instance._meta.db_table, value)
    print 'Getting %s: %s' % (value, redis.get(key))
    return redis.get(key)


def set_translation(instance, value):
    print 'Setting %s ...' % value
    instance._translations_to_save = value


def save_translation(instance, key):
    key = 'l10n:%s:%s' % (instance._meta.db_table, key)
    value = instance._translations_to_save
    print 'Saving %s: %s' % (value, key)
    redis.set(key, value)


class NewTranslatedDescriptor(object):
    """
    The descriptor for the translated attribute on the model instance.
    """

    def __init__(self, field):
        self.field = field

    def __get__(self, instance=None, owner=None):
        print '__get__'

        if instance is None:
            raise AttributeError(
                "The '%s' attribute can only be accessed from %s instances."
                % (self.field.name, owner.__name__))

        # The instance dict contains whatever was originally assigned
        # in __set__.
        trans = instance.__dict__[self.field.name]

        print 'trans........%s' % trans

        if trans is None:
            #attr = self.field.attr_class(instance, self.field, trans)
            instance._key = make_new_key()
            print 'MAKING NEW KEY'
        else:
            print 'USING EXISTING KEY'
            instance._key = trans
        # else:
        #     set_translation(instance, trans)

        # That was fun, wasn't it?
        return get_translation(instance, instance.__dict__[self.field.name])

    def __set__(self, instance, value):
        print '__set__'
        instance.__dict__[self.field.name] = value
        set_translation(instance, value)
        # existing_key = instance.__dict__.get(self.field.name)
        # print 'existing_key:%s, value:%s' % (existing_key, value)
        # if existing_key is None:
        #     instance.__dict__[self.field.name] = make_new_key()
        # else:
        #     instance.__dict__[self.field.name] = existing_key



class NewTranslatedField(CharField):
    """
    Reference:
    https://github.com/django/django/blob/master/django/db/models/fields/files.py
    """

    # The class to wrap instance attributes in. Accessing the Trans object off
    # the instance will always return an instance of attr_class.
    # attr_class = Trans

    # The descriptor to use for accessing the attribute off of the class.
    descriptor_class = NewTranslatedDescriptor

    def __init__(self, *args, **kwargs):
        kwargs['max_length'] = kwargs.get('max_length', 23)
        super(NewTranslatedField, self).__init__(*args, **kwargs)

    def get_internal_type(self):
        return 'CharField'

    def contribute_to_class(self, cls, name):
        super(NewTranslatedField, self).contribute_to_class(cls, name)
        setattr(cls, self.name, self.descriptor_class(self))

    def get_prep_value(self, value):
        """Returns field's value prepared for saving into a database."""
        print 'get_prep_value'
        value = super(NewTranslatedField, self).get_prep_value(value)
        # Need to convert File objects provided via a form to unicode for
        # database insertion.
        if value is None:
            return None
        return six.text_type(value)

    def pre_save(self, model_instance, add):
        """Returns field's value just before saving."""
        trans = super(NewTranslatedField, self).pre_save(model_instance, add)
        print 'pre_save....%s' % trans
        #if trans and not trans._committed:
        save_translation(model_instance, model_instance._key)
        return model_instance._key
