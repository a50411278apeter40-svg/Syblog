from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

LEVEL_THRESHOLDS = [
    (1, 0, '새싹'),
    (2, 100, '씨앗'),
    (3, 300, '나무'),
    (4, 600, '덤불'),
    (5, 1000, '숲'),
    (6, 1500, '산'),
    (7, 2500, '바다'),
    (8, 4000, '하늘'),
    (9, 6000, '별'),
    (10, 10000, '전설'),
]

def get_level_info(points):
    level = 1
    title = '새싹'
    for lv, threshold, name in LEVEL_THRESHOLDS:
        if points >= threshold:
            level = lv
            title = name
    return level, title

def get_next_level_points(points):
    for lv, threshold, name in LEVEL_THRESHOLDS:
        if points < threshold:
            return threshold
    return None

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    bio = models.TextField(blank=True, default='')
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    points = models.IntegerField(default=0)
    is_blocked = models.BooleanField(default=False)
    website = models.URLField(blank=True, default='')
    github = models.CharField(max_length=100, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.user.username} Profile'

    @property
    def level(self):
        return get_level_info(self.points)[0]

    @property
    def level_title(self):
        return get_level_info(self.points)[1]

    @property
    def next_level_points(self):
        return get_next_level_points(self.points)

    @property
    def level_progress(self):
        current_threshold = 0
        next_threshold = None
        for lv, threshold, name in LEVEL_THRESHOLDS:
            if self.points >= threshold:
                current_threshold = threshold
            else:
                next_threshold = threshold
                break
        if next_threshold is None:
            return 100
        span = next_threshold - current_threshold
        progress = self.points - current_threshold
        return int((progress / span) * 100) if span > 0 else 100

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.get_or_create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    if hasattr(instance, 'profile'):
        instance.profile.save()
    else:
        UserProfile.objects.get_or_create(user=instance)
