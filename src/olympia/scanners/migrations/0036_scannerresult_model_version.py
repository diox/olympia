# Generated by Django 2.2.13 on 2020-07-16 13:24

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('scanners', '0035_delete_versionscannerflags'),
    ]

    operations = [
        migrations.AddField(
            model_name='scannerresult',
            name='model_version',
            field=models.CharField(max_length=30, null=True),
        ),
    ]
