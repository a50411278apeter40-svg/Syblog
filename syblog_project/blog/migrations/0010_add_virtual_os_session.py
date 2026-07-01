from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('blog', '0009_initial_boards'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.CreateModel(
            name='VirtualOSSession',
            fields=[
                ('id',          models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('user',        models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='virtual_os_sessions', to='auth.user')),
                ('name',        models.CharField(default='내 가상 OS', max_length=100)),
                ('cpu_id',      models.CharField(default='intel_core_i9_14900k', max_length=80)),
                ('ram_mb',      models.PositiveIntegerField(default=512)),
                ('vhd_size_gb', models.FloatField(default=8.0)),
                ('vhd_data',    models.TextField(blank=True)),
                ('state_data',  models.BinaryField(blank=True, null=True)),
                ('iso_path',    models.CharField(blank=True, max_length=500)),
                ('iso_name',    models.CharField(blank=True, max_length=200)),
                ('last_used',   models.DateTimeField(auto_now=True)),
                ('created_at',  models.DateTimeField(auto_now_add=True)),
                ('boot_count',  models.PositiveIntegerField(default=0)),
            ],
            options={'ordering': ['-last_used']},
        ),
    ]
