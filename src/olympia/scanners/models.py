import json
import re

import yara

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import ugettext_lazy as _
from django_extensions.db.fields.json import JSONField

from olympia.amo.models import ModelBase
from olympia.constants.scanners import (
    ACTIONS,
    CUSTOMS,
    NO_ACTION,
    RESULT_STATES,
    SCANNERS,
    UNKNOWN,
    WAT,
    YARA,
)
from olympia.files.models import FileUpload


class AbstractScannerResult(ModelBase):
    # Store the "raw" results of a scanner.
    results = JSONField(default=[])
    scanner = models.PositiveSmallIntegerField(choices=SCANNERS.items())
    has_matches = models.NullBooleanField()
    state = models.PositiveSmallIntegerField(
        choices=RESULT_STATES.items(), null=True, blank=True, default=UNKNOWN
    )
    version = models.ForeignKey(
        'versions.Version',
        related_name="%(class)ss",
        on_delete=models.CASCADE,
        null=True,
    )
    matched_rules = models.ManyToManyField(
        'ScannerRule', through='ScannerMatch'
    )

    class Meta(ModelBase.Meta):
        abstract = True
        indexes = [
            models.Index(fields=('has_matches',)),
            models.Index(fields=('state',)),
        ]

    def add_yara_result(self, rule, tags=None, meta=None):
        """This method is used to store a Yara result."""
        self.results.append(
            {'rule': rule, 'tags': tags or [], 'meta': meta or {}}
        )

    def extract_rule_names(self):
        """This method parses the raw results and returns the (matched) rule
        names. Not all scanners have rules that necessarily match."""
        if self.scanner == YARA:
            return sorted({result['rule'] for result in self.results})
        if self.scanner == CUSTOMS and 'matchedRules' in self.results:
            return self.results['matchedRules']
        # We do not have support for the remaining scanners (yet).
        return []

    def save(self, *args, **kwargs):
        rule_model = self._meta.get_field('matched_rules').related_model
        matched_rules = rule_model.objects.filter(
            scanner=self.scanner, name__in=self.extract_rule_names()
        )
        self.has_matches = bool(matched_rules)
        # Save the instance first...
        super().save(*args, **kwargs)
        # ...then add the associated rules.
        for scanner_rule in matched_rules:
            self.matched_rules.add(scanner_rule)

    def get_scanner_name(self):
        return SCANNERS.get(self.scanner)

    def get_pretty_results(self):
        return json.dumps(self.results, indent=2)

    def can_report_feedback(self):
        return (
            self.has_matches and self.state == UNKNOWN and self.scanner != WAT
        )

    def can_revert_feedback(self):
        return (
            self.has_matches and self.state != UNKNOWN and self.scanner != WAT
        )

    def get_git_repository(self):
        return {
            CUSTOMS: settings.CUSTOMS_GIT_REPOSITORY,
            YARA: settings.YARA_GIT_REPOSITORY,
        }.get(self.scanner)


class AbstractScannerRule(ModelBase):
    name = models.CharField(
        max_length=200,
        help_text=_('This is the exact name of the rule used by a scanner.'),
    )
    scanner = models.PositiveSmallIntegerField(choices=SCANNERS.items())
    action = models.PositiveSmallIntegerField(
        choices=ACTIONS.items(), default=NO_ACTION
    )
    is_active = models.BooleanField(default=True)
    definition = models.TextField(null=True, blank=True)

    class Meta(ModelBase.Meta):
        abstract = True
        unique_together = ('name', 'scanner')

    def __str__(self):
        return self.name

    def clean(self):
        if self.scanner == YARA:
            self.clean_yara()

    def clean_yara(self):
        if not self.definition:
            raise ValidationError(
                {'definition': _('Yara rules should have a definition')}
            )

        if 'rule {}'.format(self.name) not in self.definition:
            raise ValidationError(
                {
                    'definition': _(
                        'The name of the rule in the definition should match '
                        'the name of the scanner rule'
                    )
                }
            )

        if len(re.findall(r'rule\s+.+?\s+{', self.definition)) > 1:
            raise ValidationError(
                {
                    'definition': _(
                        'Only one Yara rule is allowed in the definition'
                    )
                }
            )

        try:
            yara.compile(source=self.definition)
        except yara.SyntaxError as syntaxError:
            raise ValidationError({
                'definition': _('The definition is not valid: %(error)s') % {
                    'error': syntaxError,
                }
            })
        except Exception:
            raise ValidationError(
                {
                    'definition': _(
                        'An error occurred when compiling the definition'
                    )
                }
            )


class ScannerRule(AbstractScannerRule):
    class Meta(AbstractScannerRule.Meta):
        db_table = 'scanners_rules'


class ScannerResult(AbstractScannerResult):
    upload = models.ForeignKey(
        FileUpload,
        related_name="%(class)ss",  # scannerresults
        on_delete=models.SET_NULL,
        null=True,
    )

    class Meta(AbstractScannerResult.Meta):
        db_table = 'scanners_results'
        constraints = [
            models.UniqueConstraint(
                fields=('upload', 'scanner', 'version'),
                name='scanners_results_upload_id_scanner_'
                'version_id_ad9eb8a6_uniq',
            )
        ]


class ScannerMatch(ModelBase):
    result = models.ForeignKey(ScannerResult, on_delete=models.CASCADE)
    rule = models.ForeignKey(ScannerRule, on_delete=models.CASCADE)


class ScannerQueryRule(AbstractScannerRule):
    class Meta(AbstractScannerRule.Meta):
        db_table = 'scanners_query_rules'


class ScannerQueryResult(AbstractScannerResult):
    # Has to be overridden, because the parent refers to ScannerMatch.
    matched_rules = models.ManyToManyField(
        'ScannerQueryRule', through='ScannerQueryMatch'
    )

    class Meta(AbstractScannerResult.Meta):
        db_table = 'scanners_query_results'
        # FIXME indexes, unique constraints ?


class ScannerQueryMatch(ModelBase):
    result = models.ForeignKey(ScannerQueryResult, on_delete=models.CASCADE)
    rule = models.ForeignKey(ScannerQueryRule, on_delete=models.CASCADE)
