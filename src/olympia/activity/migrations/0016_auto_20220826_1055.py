# Generated by Django 3.2.15 on 2022-08-26 10:55

import ipaddress
from django.db import migrations


def backfill_iplog_ip_address_binary(apps, schema_editor):
    IPLog = apps.get_model('activity', 'IPLog')
    for log in IPLog.objects.filter(ip_address_binary__isnull=True).iterator():
        log.ip_address_binary = ipaddress.ip_address(log.ip_address).packed
        log.save()


class Migration(migrations.Migration):

    dependencies = [
        ('activity', '0015_auto_20220826_0956'),
    ]

    operations = [
        migrations.RunPython(backfill_iplog_ip_address_binary)
    ]
