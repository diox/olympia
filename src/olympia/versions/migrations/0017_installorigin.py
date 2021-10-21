# Generated by Django 3.2.8 on 2021-10-21 12:56

from django.db import migrations, models
import django.db.models.deletion


def create_waffle_switch_if_it_doesnt_already_exist(apps, schema_editor):
    Switch = apps.get_model('waffle', 'Switch')
    Switch.objects.get_or_create(
        name='record-install-origins',
        defaults={
            'active': False,
            'note': 'Record install origins declared in add-on manifests at submission',
        },
    )


class Migration(migrations.Migration):

    dependencies = [
        ('versions', '0016_auto_20210325_1320'),
    ]

    operations = [
        migrations.CreateModel(
            name='InstallOrigin',
            fields=[
                (
                    'id',
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name='ID',
                    ),
                ),
                ('origin', models.CharField(max_length=255)),
                ('base_domain', models.CharField(max_length=255)),
                (
                    'version',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to='versions.version',
                    ),
                ),
            ],
        ),
        migrations.RunPython(create_waffle_switch_if_it_doesnt_already_exist),
    ]
