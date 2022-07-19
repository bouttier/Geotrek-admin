# Generated by Django 3.1.14 on 2022-07-19 15:05

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('authent', '0009_userprofile_extended_username'),
        ('core', '0031_certificationlabel_certificationstatus_certificationtrail'),
    ]

    operations = [
        migrations.CreateModel(
            name='TrailCategory',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('label', models.CharField(max_length=128, verbose_name='Name')),
                ('structure', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='authent.structure', verbose_name='Related structure')),
            ],
            options={
                'verbose_name': 'Trail category',
                'verbose_name_plural': 'Trail categories',
                'ordering': ['label'],
            },
        ),
        migrations.AddField(
            model_name='trail',
            name='category',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='core.trailcategory', verbose_name='Category'),
        ),
    ]
