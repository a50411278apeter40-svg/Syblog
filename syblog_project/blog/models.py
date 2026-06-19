from django.db import models
from django.contrib.auth.models import User
from markdownx.models import MarkdownxField
from markdownx.utils import markdown
import os
from django.conf import settings

def check_banned_keywords(text):
    text_lower = text.lower()
    for kw in settings.BANNED_KEYWORDS:
        if kw.lower() in text_lower:
            return True, kw
    return False, None

class Tag(models.Model):
    name = models.CharField(max_length=50)
    slug = models.SlugField(max_length=200, unique=True, allow_unicode=True)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return f'/blog/tag/{self.slug}/'

class Category(models.Model):
    name = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(max_length=200, unique=True, allow_unicode=True)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return f'/blog/category/{self.slug}/'

    class Meta:
        verbose_name_plural = 'categories'

class Series(models.Model):
    title = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='series')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    thumbnail = models.ImageField(upload_to='series/thumbnails/', blank=True, null=True)

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return f'/blog/series/{self.pk}/'

    class Meta:
        verbose_name_plural = 'series'

class Post(models.Model):
    title = models.CharField(max_length=200)
    hook_text = models.CharField(max_length=300, blank=True)
    content = MarkdownxField()

    head_image = models.ImageField(upload_to='blog/images/%Y/%m/%d/', blank=True)
    file_upload = models.FileField(upload_to='blog/files/%Y/%m/%d/', blank=True)
    url_embed = models.URLField(blank=True, default='', max_length=500, verbose_name='URL 임베드')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    author = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
    category = models.ForeignKey(Category, null=True, blank=True, on_delete=models.SET_NULL)
    tags = models.ManyToManyField(Tag, blank=True)
    series = models.ForeignKey(Series, null=True, blank=True, on_delete=models.SET_NULL, related_name='posts')
    series_order = models.IntegerField(default=0)
    view_count = models.IntegerField(default=0)
    like_count = models.IntegerField(default=0)
    likes = models.ManyToManyField(User, blank=True, related_name='liked_posts')

    def __str__(self):
        return f'[{self.pk}]{self.title} :: {self.author}'

    def get_absolute_url(self):
        return f'/blog/{self.pk}/'

    def get_file_name(self):
        return os.path.basename(self.file_upload.name)

    def get_file_ext(self):
        return self.get_file_name().split('.')[-1]

    def get_content_markdown(self):
        return markdown(self.content)

    def get_avatar_url(self, size=60):
        try:
            profile = self.author.profile
            if profile.avatar and profile.avatar.name:
                return profile.avatar.url
        except Exception:
            pass
        return f'https://ui-avatars.com/api/?name={self.author.username}&background=6c63ff&color=fff&size={size}'

class Comment(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.CASCADE, related_name='replies')
    is_deleted = models.BooleanField(default=False)

    def __str__(self):
        return f'{self.author}::{self.content[:30]}'

    def get_absolute_url(self):
        return f'{self.post.get_absolute_url()}#comment-{self.pk}'

    def get_avatar_url(self, size=60):
        try:
            profile = self.author.profile
            if profile.avatar and profile.avatar.name:
                return profile.avatar.url
        except Exception:
            pass
        return f'https://ui-avatars.com/api/?name={self.author.username}&background=6c63ff&color=fff&size={size}'
    
    @property
    def top_level_replies(self):
        return self.replies.filter(is_deleted=False)


class Notice(models.Model):
    LEVEL_CHOICES = [
        ('info',    '일반 (파란색)'),
        ('warning', '주의 (노란색)'),
        ('danger',  '긴급 (빨간색)'),
        ('success', '성공 (초록색)'),
    ]
    title      = models.CharField(max_length=200, verbose_name='제목')
    content    = models.TextField(blank=True, verbose_name='상세 내용')
    level      = models.CharField(max_length=10, choices=LEVEL_CHOICES, default='info', verbose_name='종류')
    is_active  = models.BooleanField(default=True, verbose_name='표시 여부')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        verbose_name='작성자'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True, verbose_name='만료일시 (비워두면 무기한)')

    class Meta:
        ordering = ['-created_at']
        verbose_name = '공지사항'
        verbose_name_plural = '공지사항'

    def __str__(self):
        return self.title

    def is_visible(self):
        from django.utils import timezone
        if not self.is_active:
            return False
        if self.expires_at and timezone.now() > self.expires_at:
            return False
        return True
