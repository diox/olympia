import json

from django.db.models.signals import post_delete, post_save, pre_save
from django.utils import translation as translation_utils

import redisutils


KEY_PREFIX = 'l10n'
REGISTRY = {}


# Exception for being unable to communicate with the L10n data store.
TransConnectionError = redisutils.redislib.ConnectionError

# Exception for trying to save a localised string of an incorrect data type.
TransValueError = ValueError('Must be a "str" or "dict"')


class SafeRedis(object):

    def __init__(self, obj):
        self._wrapped_obj = obj

    def __getattr__(self, attr):
        if attr in self.__dict__:
            return getattr(self, attr)

        # TODO: Catch redisutils.redislib.ConnectionError
        # and raise a generic exception. And add logging.
        return getattr(self._wrapped_obj, attr)


redis = SafeRedis(redisutils.connections['master'])


class Trans(object):

    def __init__(self, instance, name, *args, **kwargs):
        self.instance = instance
        self.name = name

    def __dict__(self):
        return get_translations(self.instance, self.name)

    def __repr__(self):
        return '<Trans: %s>' % self.instance.__dict__[self.name]

    def __str__(self):
        return self.__unicode__()

    def __unicode__(self):
        """
        (1) Try the currently activated language.
        (2) Try the instance's default language (if available).
        (3) Use the fallback in the database.

        TODO: Handle locales such as pt-BR, es-ES, etc.
        """

        data = get_translations(self.instance, self.name) or {}

        langs_to_try = [
            translation_utils.get_language(),
            get_default_lang(self.instance),
        ]

        for lang in langs_to_try:
            try:
                if lang is not None:
                    return data[lang]
            except KeyError:
                continue

        # Return the fallback in the database.
        return self.instance.__dict__[self.name]

    def get_key(self):
        return get_key(self.instance, self.name)


def get_default_lang(instance):
    return (getattr(instance, 'default_lang', None) or
            getattr(instance, 'default_locale', None))


def get_key(instance, name):
    return '%s:%s:%s:%s' % (KEY_PREFIX, instance._meta.db_table, instance.pk,
                            name)


def get_translations(instance, name):
    key = get_key(instance, name)

    data = {}

    try:
        data = redis.get(key)
    except TransConnectionError:
        # Return the fallback in the database.
        default_lang = get_default_lang(instance)

        # If we somehow don't have a `default_lang` field, this key
        # will be called `None`. So please remember to make a column.
        data = {default_lang: instance.__dict__[name]}
    else:
        try:
            data = json.loads(data)
        except (TypeError, ValueError):
            # It was invalid JSON.
            data = {}

    return data


def has_translation(instance, name):
    key = get_key(instance, name)

    try:
        data = redis.get(key)
    except TransConnectionError:
        # We can't be sure; let's assume yes until the data store is online.
        return True
    else:
        try:
            data = json.loads(data)
        except (TypeError, ValueError):
            # It was invalid JSON or no key exists.
            return False
        else:
            # It was a non-empty dict.
            return bool(data) and type(data) is dict


def get_lazy_translation(instance, name):
    """Return an object that lets us do lazy translations."""
    return Trans(instance=instance, name=name)


def save_translation(instance, name, value):
    if instance.pk is None:
        return

    key = get_key(instance, name)
    if value is None:
        delete_translation(instance, name)
        return
    elif isinstance(value, basestring):
        value = {translation_utils.get_language(): value}
    elif isinstance(value, dict):
        # Lowercase the locale keys.
        value = dict((k.lower(), v) for k, v in value.iteritems())
    else:
        raise TransValueError

    try:
        old_value = json.loads(redis.get(key))
    except (TypeError, ValueError, TransConnectionError):
        pass
    else:
        value = dict(old_value, **value)

    try:
        redis.set(key, json.dumps(value))
    except TransConnectionError:
        pass


def delete_translation(instance, name):
    key = get_key(instance, name)
    try:
        return redis.delete(key)
    except TransConnectionError:
        pass


def _trans_pre_save(sender, instance, **kwargs):
    setattr(instance, '_trans_saving', True)


def _trans_post_save(sender, instance, **kwargs):
    delattr(instance, '_trans_saving')


def _trans_post_delete(sender, instance, **kwargs):
    for field_name in REGISTRY[instance.__class__]:
        delete_translation(instance, field_name)


def register_trans(model, fields):
    global REGISTRY
    REGISTRY[model] = fields

    for field in fields:
        setattr(model, field, TransDescriptor(field))

    pre_save.connect(_trans_pre_save, sender=model)
    post_save.connect(_trans_post_save, sender=model)
    post_delete.connect(_trans_post_delete, sender=model)


class TransDescriptor(object):

    def __init__(self, name):
        self.name = name

    def __get__(self, obj, type_=None):
        if obj:
            key = obj.__dict__[self.name]
        else:
            return getattr(type_, self.name)

        if not key:
            return key

        if not isinstance(key, (basestring, dict)):
            raise TransValueError

        if getattr(obj, '_trans_saving', False):
            save_translation(obj, self.name, key)

            # Save this fallback value to the database if this is the first
            # translation.
            if not has_translation(obj, self.name):
                return key

            current_lang = translation_utils.get_language()
            default_lang = get_default_lang(obj)

            # Replace the fallback value if we're replacing the translation
            # for the default locale.
            if default_lang and default_lang == current_lang:
                if isinstance(key, basestring):
                    return key
                elif isinstance(key, dict):
                    # Lowercase the locale keys.
                    key = dict((k.lower(), v) for k, v in key.iteritems())
                    if current_lang in key:
                        return key[current_lang]

            # If there's not a `default_lang` and we did
            #
            #     tower.activate('fr')
            #     c.name = 'New Default Translated Name'
            #     c.save()
            #
            # ... then assume that should be the new fallback value.
            return key

        return get_lazy_translation(obj, self.name)

    def __set__(self, obj, value):
        obj.__dict__[self.name] = value


def get_all_translation_keys():
    """Returns a dict of all the translation keys across all the models."""
    data = {}
    for model, fields in REGISTRY.items():
        objs = model.objects.only('pk')
        data[model._meta.db_table] = {}
        for obj in objs:
            data[model._meta.db_table][obj.pk] = dict(
                (f, get_key(obj, f)) for f in fields
            )
    return data


def get_all_translation_strings():
    """Returns a dict of all the translated strings across all the models."""
    data = {}
    for model, fields in REGISTRY.items():
        objs = model.objects.only('pk')
        data[model._meta.db_table] = {}
        for obj in objs:
            data[model._meta.db_table][obj.pk] = {}
            for f in fields:
                val = getattr(obj, f)
                if val is not None:
                    translations = val.__dict__()
                else:
                    translations = None
                data[model._meta.db_table][obj.pk][f] = translations
    return data
