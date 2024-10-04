# Generated by Django 5.1.1 on 2024-09-26 12:33

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0006_alter_project_stack'),
        ('skills', '0003_alter_stack_name'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='session',
            name='prog_language',
        ),
        migrations.AddField(
            model_name='session',
            name='prog_language',
            field=models.ManyToManyField(blank=True, to='skills.proglanguage'),
        ),
    ]
