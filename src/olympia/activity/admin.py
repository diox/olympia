from django.contrib import admin

from olympia import amo
from olympia.amo.admin import AMOModelAdmin
from olympia.reviewers.models import ReviewActionReason
from olympia.zadmin.admin import related_single_content_link

from .models import ActivityLog, ReviewActionReasonLog


class ActivityLogAdmin(AMOModelAdmin):
    list_display = (
        'created',
        'user_link',
        'pretty_arguments',
        'kept_forever',
        'ip_address',
    )
    raw_id_fields = ('user',)
    readonly_fields = (
        'created',
        'user',
        'pretty_arguments',
        'kept_forever',
        'ip_address',
    )
    fields = (
        'user',
        'created',
        'pretty_arguments',
        'kept_forever',
        'ip_address',
    )
    raw_id_fields = ('user',)
    view_on_site = False
    list_select_related = ('iplog',)

    def lookup_allowed(self, lookup, value):
        if lookup == 'addonlog__addon':
            return True
        return super().lookup_allowed(lookup, value)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description='Arguments')
    def pretty_arguments(self, obj):
        return obj.to_string(type_='admin')

    @admin.display(description='User')
    def user_link(self, obj):
        return related_single_content_link(obj, 'user')

    @admin.display(description='IP Address', ordering='iplog__ip_address_binary')
    def ip_address(self, obj):
        return str(obj.iplog)

    @admin.display(description='Kept forever', boolean=True)
    def kept_forever(self, obj):
        return getattr(amo.LOG_BY_ID.get(obj.action), 'keep', False)

    def change_view(self, request, object_id, form_url='', extra_context=None):
        if extra_context is None:
            extra_context = {}
        # The __str__ for ActivityLog contains HTML, so use a simpler subtitle.
        extra_context['subtitle'] = f'{self.model._meta.verbose_name} {object_id}'
        return super().change_view(
            request, object_id, form_url=form_url, extra_context=extra_context
        )


class ReviewActionReasonLogAdmin(AMOModelAdmin):
    fields = (
        'created',
        'activity_log',
        'activity_log__user__email',
        'reason',
    )
    list_display = (
        'created',
        'activity_log',
        'reason',
        'activity_log__user__email',
    )
    list_filter = ('reason',)
    list_select_related = ('activity_log__user',)
    readonly_fields = (
        'created',
        'activity_log',
        'activity_log__user__email',
    )
    search_fields = ('activity_log__user__email',)
    view_on_site = False

    def activity_log__user__email(self, obj):
        return obj.activity_log.user.email

    def has_add_permission(self, request):
        return False

    def get_form(self, request, obj=None, **kwargs):
        form = super(ReviewActionReasonLogAdmin, self).get_form(request, obj, **kwargs)
        form.base_fields['reason'].widget.can_add_related = False
        form.base_fields['reason'].widget.can_change_related = False
        form.base_fields['reason'].empty_label = None
        form.base_fields['reason'].choices = [
            (reason.id, reason.labelled_name())
            for reason in ReviewActionReason.objects.all()
        ]
        return form


admin.site.register(ActivityLog, ActivityLogAdmin)
admin.site.register(ReviewActionReasonLog, ReviewActionReasonLogAdmin)
