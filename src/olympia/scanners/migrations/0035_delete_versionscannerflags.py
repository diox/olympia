# Generated by Django 2.2.13 on 2020-06-25 11:16

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('scanners', '0034_delete_version_flags_again'),
    ]

    operations = [
        migrations.DeleteModel(
            name='VersionScannerFlags',
        ),
    ]
