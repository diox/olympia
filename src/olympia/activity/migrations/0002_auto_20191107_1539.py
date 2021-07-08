# Generated by Django 2.2.6 on 2019-11-07 15:39

from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
import olympia.amo.fields
import olympia.amo.models


class Migration(migrations.Migration):

    dependencies = [
        ('blocklist', '0003_remove_block_addon'),
        ('activity', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='activitylog',
            name='action',
            field=models.SmallIntegerField(choices=[(1, 1), (2, 2), (3, 3), (4, 4), (5, 5), (6, 6), (7, 7), (8, 8), (9, 9), (12, 12), (16, 16), (17, 17), (18, 18), (19, 19), (20, 20), (21, 21), (22, 22), (23, 23), (24, 24), (25, 25), (26, 26), (27, 27), (28, 28), (29, 29), (31, 31), (32, 32), (33, 33), (34, 34), (35, 35), (36, 36), (37, 37), (38, 38), (39, 39), (40, 40), (41, 41), (42, 42), (43, 43), (44, 44), (45, 45), (46, 46), (47, 47), (48, 48), (49, 49), (53, 53), (60, 60), (98, 98), (99, 99), (100, 100), (101, 101), (102, 102), (103, 103), (104, 104), (105, 105), (106, 106), (107, 107), (108, 108), (109, 109), (110, 110), (120, 120), (121, 121), (128, 128), (130, 130), (131, 131), (132, 132), (133, 133), (134, 134), (135, 135), (136, 136), (137, 137), (138, 138), (139, 139), (140, 140), (141, 141), (142, 142), (143, 143), (144, 144), (145, 145), (146, 146), (147, 147), (148, 148), (149, 149), (150, 150), (151, 151), (152, 152), (153, 153), (154, 154), (155, 155), (156, 156), (157, 157), (158, 158)]),
        ),
        migrations.CreateModel(
            name='BlockLog',
            fields=[
                ('created', models.DateTimeField(blank=True, default=django.utils.timezone.now, editable=False)),
                ('modified', models.DateTimeField(auto_now=True)),
                ('id', olympia.amo.fields.PositiveAutoField(primary_key=True, serialize=False)),
                ('activity_log', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='activity.ActivityLog')),
                ('block', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='blocklist.Block')),
            ],
            options={
                'db_table': 'log_activity_block',
                'ordering': ('-created',),
            },
            bases=(olympia.amo.models.SaveUpdateMixin, models.Model),
        ),
    ]
