import functools

from django.core.exceptions import PermissionDenied

import commonware.log

log = commonware.log.getLogger('mkt.purchase')


def can_become_premium(f):
    """Check that the webapp can become premium."""
    @functools.wraps(f)
    def wrapper(request, addon_id, addon, *args, **kw):
        if not addon.can_become_premium():
            log.info('Cannot become premium: %d' % addon.pk)
            raise PermissionDenied
        return f(request, addon_id, addon, *args, **kw)
    return wrapper
