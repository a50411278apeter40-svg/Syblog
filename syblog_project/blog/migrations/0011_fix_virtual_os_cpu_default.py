from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('blog', '0010_add_virtual_os_session'),
    ]

    operations = [
        migrations.AlterField(
            model_name='virtualossession',
            name='cpu_id',
            field=models.CharField(default='i9_14900k', max_length=80),
        ),
    ]
