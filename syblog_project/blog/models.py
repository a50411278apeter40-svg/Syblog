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

# ─── 1. 북마크 모델 ───────────────────────────────────────────
class Bookmark(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='bookmarks')
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='bookmarked_by')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'post')
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user.username} → {self.post.title}'


# ─── 2. 예약 게시 필드 (Post에 추가) - 별도 모델로 스케줄 관리 ───
class ScheduledPost(models.Model):
    post = models.OneToOneField(Post, on_delete=models.CASCADE, related_name='schedule')
    publish_at = models.DateTimeField(verbose_name='예약 공개 시각')
    is_published = models.BooleanField(default=False)

    def __str__(self):
        return f'{self.post.title} @ {self.publish_at}'


# ─── 3. 글 버전 히스토리 ────────────────────────────────────────
class PostHistory(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='history')
    title = models.CharField(max_length=200)
    content = models.TextField()
    saved_at = models.DateTimeField(auto_now_add=True)
    saved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    version = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ['-saved_at']

    def __str__(self):
        return f'{self.post.title} v{self.version}'


# ─── 4. 댓글 좋아요 ─────────────────────────────────────────────
class CommentLike(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='comment_likes')
    comment = models.ForeignKey(Comment, on_delete=models.CASCADE, related_name='likes')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'comment')

    def __str__(self):
        return f'{self.user.username} ♥ comment#{self.comment.pk}'


# ─── 5. 실시간 알림 ─────────────────────────────────────────────
class Notification(models.Model):
    TYPE_CHOICES = [
        ('like',      '좋아요'),
        ('comment',   '댓글'),
        ('reply',     '답글'),
        ('follow',    '팔로우'),
        ('mention',   '멘션'),
        ('comment_like', '댓글 좋아요'),
    ]
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_notifications', null=True, blank=True)
    ntype = models.CharField(max_length=20, choices=TYPE_CHOICES)
    message = models.CharField(max_length=300)
    url = models.CharField(max_length=500, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'→{self.recipient.username}: {self.message[:40]}'


# ─── 6. RSS Feed (별도 모델 불필요 - views에서 처리) ────────────


# ─── 7. AI 채팅 히스토리 (유저별 영구 저장, 최대 60개) ──────────────────────
class AiChatHistory(models.Model):
    user       = models.ForeignKey(User, on_delete=models.CASCADE, related_name='ai_chat_histories')
    panel_key  = models.CharField(max_length=120)          # 패널 식별자 (페이지URL+panelId)
    role       = models.CharField(max_length=10)           # 'user' or 'ai'
    content    = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f'{self.user.username} / {self.panel_key} / {self.role} / {self.content[:30]}'


# ─── 8. AI 크레딧 시스템 ────────────────────────────────────────
class AiCredit(models.Model):
    """유저별 AI 크레딧 (기본 30, 포인트로 구매 가능, 관리자 무제한)"""
    user           = models.OneToOneField(User, on_delete=models.CASCADE, related_name='ai_credit')
    credits        = models.IntegerField(default=30)       # 잔여 크레딧
    total_used     = models.IntegerField(default=0)        # 누적 사용량
    is_unlimited   = models.BooleanField(default=False)    # 관리자 무제한

    updated_at     = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.user.username} AI크레딧={self.credits} 무제한={self.is_unlimited}'

    def can_use(self, cost=1):
        """크레딧 사용 가능 여부"""
        if self.is_unlimited or self.user.is_staff or self.user.is_superuser:
            return True
        return self.credits >= cost

    def use(self, cost=1):
        """크레딧 차감 (관리자는 차감 없음). 성공 시 True"""
        if self.is_unlimited or self.user.is_staff or self.user.is_superuser:
            self.total_used += cost
            self.save(update_fields=['total_used', 'updated_at'])
            return True
        if self.credits < cost:
            return False
        self.credits -= cost
        self.total_used += cost
        self.save(update_fields=['credits', 'total_used', 'updated_at'])
        return True

    def add(self, amount):
        self.credits += amount
        self.save(update_fields=['credits', 'updated_at'])


class AiCreditLog(models.Model):
    """크레딧 변동 이력"""
    ACTION_CHOICES = [
        ('use',      'AI 사용'),
        ('buy',      '포인트 구매'),
        ('admin',    '관리자 지급'),
        ('reset',    '초기화'),
        ('webdev',   'AI 웹개발 사용'),
    ]
    user       = models.ForeignKey(User, on_delete=models.CASCADE, related_name='ai_credit_logs')
    action     = models.CharField(max_length=20, choices=ACTION_CHOICES)
    amount     = models.IntegerField()          # 양수=획득, 음수=사용
    balance    = models.IntegerField()          # 변동 후 잔액
    note       = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user.username} {self.action} {self.amount:+d} → {self.balance}'


# ─── 9. AI 웹개발 프로젝트 ───────────────────────────────────────
class AiWebProject(models.Model):
    """AI 웹개발 베타: 유저별 가상환경 프로젝트"""
    STATUS_CHOICES = [
        ('active',   '작업중'),
        ('deployed', '배포됨'),
        ('stopped',  '중지'),
    ]
    user        = models.ForeignKey(User, on_delete=models.CASCADE, related_name='web_projects')
    name        = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    status      = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    deploy_url  = models.URLField(blank=True)
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.user.username}/{self.name}'


class AiWebSession(models.Model):
    """AI 웹개발 대화 세션"""
    project     = models.ForeignKey(AiWebProject, on_delete=models.CASCADE, related_name='sessions')
    role        = models.CharField(max_length=10)   # 'user' or 'ai'
    content     = models.TextField()
    tool_calls  = models.JSONField(default=list)    # [{tool, args, result}, ...]
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']


class AiWebTask(models.Model):
    """AI 웹개발 백그라운드 작업 상태 추적 (새로고침 후에도 재개 가능)"""
    STATUS_RUNNING   = 'running'
    STATUS_DONE      = 'done'
    STATUS_ERROR     = 'error'
    STATUS_CANCELLED = 'cancelled'

    STATUS_CHOICES = [
        (STATUS_RUNNING,   '실행 중'),
        (STATUS_DONE,      '완료'),
        (STATUS_ERROR,     '오류'),
        (STATUS_CANCELLED, '취소'),
    ]

    project    = models.ForeignKey(AiWebProject, on_delete=models.CASCADE, related_name='tasks')
    status     = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_RUNNING)
    label      = models.CharField(max_length=200, blank=True)   # "명령 실행 중..." 같은 표시 문구
    result_msg = models.TextField(blank=True)                   # 완료 후 결과 메시지
    error_msg  = models.TextField(blank=True)
    loop_count = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Task({self.pk}) {self.project} [{self.status}]'
