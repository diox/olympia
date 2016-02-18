import commonware.log
from rest_framework.authentication import BaseAuthentication


log = commonware.log.getLogger('z.api')


class RestOAuthAuthentication(BaseAuthentication):
    www_authenticate_realm = ''

    def authenticate(self, request):
        # Most of the work here is in the RestOAuthMiddleware.
        if (getattr(request._request, 'user', None) and
                'RestOAuth' in getattr(request._request, 'authed_from', [])):
            request.user = request._request.user
            return request.user, None

    def authenticate_header(self, request):
        return 'OAuth realm="%s"' % self.www_authenticate_realm
