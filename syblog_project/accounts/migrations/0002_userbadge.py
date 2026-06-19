from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='UserBadge',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('badge_id', models.CharField(max_length=50)),
                ('earned_at', models.DateTimeField(auto_now_add=True)),
                ('profile', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='badges', to='accounts.userprofile')),
            ],
            options={
                'ordering': ['earned_at'],
                'unique_together': {('profile', 'badge_id')},
            },
        ),
    ]
