# Generated by Django 2.2.17 on 2021-03-15 12:20

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('files', '0006_auto_20210223_1215'),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name='file',
            name='platform_id',
        ),
        migrations.AlterField(
            model_name='file',
            name='platform',
            field=models.PositiveIntegerField(choices=[(1, 'All Platforms'), (2, 'Linux'), (3, 'Mac OS X'), (5, 'Windows'), (7, 'Android')], db_column='platform_id', default=1, null=True),
        ),
    ]
