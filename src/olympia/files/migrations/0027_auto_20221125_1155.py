# Generated by Django 3.2.16 on 2022-11-25 11:55

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('files', '0026_auto_20221104_1312'),
    ]

    operations = [
        migrations.AlterField(
            model_name='file',
            name='cert_serial_num',
            field=models.TextField(blank=True, max_length=100000),
        ),
        migrations.AlterField(
            model_name='fileupload',
            name='validation',
            field=models.TextField(max_length=100000, null=True),
        ),
        migrations.AlterField(
            model_name='filevalidation',
            name='validation',
            field=models.TextField(max_length=100000),
        ),
        migrations.AddConstraint(
            model_name='file',
            constraint=models.CheckConstraint(check=models.Q(('cert_serial_num__length__lte', 100000)), name='files_file_cert_se_d1e52afa_mlen'),
        ),
        migrations.AddConstraint(
            model_name='fileupload',
            constraint=models.CheckConstraint(check=models.Q(('validation__length__lte', 100000)), name='files_fileu_validat_9008406a_mlen'),
        ),
        migrations.AddConstraint(
            model_name='filevalidation',
            constraint=models.CheckConstraint(check=models.Q(('validation__length__lte', 100000)), name='files_filev_validat_482ae089_mlen'),
        ),
    ]
