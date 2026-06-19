from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

# ─── 등급 시스템 (10단계) ───────────────────────────────────
LEVEL_THRESHOLDS = [
    (1,     0,     '🌱 새싹',   '#95A5A6'),
    (2,     150,   '🌿 새내기', '#2ECC71'),
    (3,     400,   '🌳 성장',   '#27AE60'),
    (4,     800,   '⭐ 탐험가', '#F1C40F'),
    (5,     1500,  '🔥 전사',   '#E67E22'),
    (6,     2500,  '💎 영웅',   '#3498DB'),
    (7,     4000,  '👑 왕',     '#9B59B6'),
    (8,     6500,  '🌙 달인',   '#E74C3C'),
    (9,     10000, '🌟 마스터', '#F39C12'),
    (10,    15000, '🏆 전설',   '#FFD700'),
]

# ─── 30개 배지 정의 ────────────────────────────────────────
BADGE_LIST = [
    # 가입/기본
    {'id': 'welcome',       'name': '환영합니다!',      'icon': '🎉', 'desc': '첫 가입을 환영합니다',           'category': '기본'},
    {'id': 'first_post',    'name': '첫 글 작성',       'icon': '✍️', 'desc': '첫 번째 글을 작성했습니다',      'category': '블로그'},
    {'id': 'first_comment', 'name': '첫 댓글',          'icon': '💬', 'desc': '첫 번째 댓글을 달았습니다',      'category': '블로그'},
    {'id': 'first_like',    'name': '첫 좋아요',        'icon': '❤️', 'desc': '처음으로 게시글에 좋아요를 눌렀습니다', 'category': '블로그'},
    # 블로그 활동
    {'id': 'writer5',       'name': '작가 지망생',      'icon': '📝', 'desc': '게시글 5개 작성',               'category': '블로그'},
    {'id': 'writer20',      'name': '베테랑 작가',      'icon': '📚', 'desc': '게시글 20개 작성',              'category': '블로그'},
    {'id': 'popular',       'name': '인기 포스터',      'icon': '🔥', 'desc': '게시글 좋아요 10개 이상 획득',   'category': '블로그'},
    {'id': 'view100',       'name': '주목받는 블로거',  'icon': '👀', 'desc': '총 조회수 100회 달성',           'category': '블로그'},
    {'id': 'series_start',  'name': '시리즈 시작',      'icon': '📖', 'desc': '첫 시리즈를 만들었습니다',       'category': '블로그'},
    # 게임 기본
    {'id': 'gamer',         'name': '게이머',           'icon': '🎮', 'desc': '첫 번째 게임을 플레이했습니다',  'category': '게임'},
    {'id': 'game5',         'name': '게임 수집가',      'icon': '🕹️', 'desc': '5가지 다른 게임 플레이',        'category': '게임'},
    {'id': 'game_all',      'name': '완전 정복',        'icon': '🏅', 'desc': '모든 게임을 한 번씩 플레이',     'category': '게임'},
    {'id': 'play50',        'name': '게임 중독자',      'icon': '😈', 'desc': '총 50번 게임 플레이',           'category': '게임'},
    {'id': 'play100',       'name': '백전노장',         'icon': '⚔️', 'desc': '총 100번 게임 플레이',         'category': '게임'},
    # 게임 점수
    {'id': 'mario_master',  'name': '마리오 마스터',    'icon': '🍄', 'desc': '마리오에서 1000점 이상',         'category': '게임'},
    {'id': 'snake_king',    'name': '스네이크 킹',      'icon': '🐍', 'desc': '스네이크에서 30칸 이상',         'category': '게임'},
    {'id': 'tetris_god',    'name': '테트리스 신',      'icon': '🟦', 'desc': '테트리스에서 1000점 이상',       'category': '게임'},
    {'id': 'flappy_ace',    'name': '플래피 에이스',    'icon': '🐦', 'desc': '플래피 버드 20점 이상',          'category': '게임'},
    {'id': 'dino_runner',   'name': '공룡 질주',        'icon': '🦖', 'desc': '공룡 게임 500점 이상',           'category': '게임'},
    {'id': 'quiz_genius',   'name': '퀴즈 천재',        'icon': '🧠', 'desc': '퀴즈에서 10문제 전부 정답',      'category': '게임'},
    # 포인트/레벨
    {'id': 'points100',     'name': '포인트 초보',      'icon': '🥉', 'desc': '누적 포인트 100점 달성',         'category': '등급'},
    {'id': 'points500',     'name': '포인트 중급',      'icon': '🥈', 'desc': '누적 포인트 500점 달성',         'category': '등급'},
    {'id': 'points1500',    'name': '포인트 고수',      'icon': '🥇', 'desc': '누적 포인트 1500점 달성',        'category': '등급'},
    {'id': 'level5',        'name': '5레벨 달성',       'icon': '🔥', 'desc': '레벨 5 (전사) 도달',            'category': '등급'},
    {'id': 'level10',       'name': '전설 달성',        'icon': '🏆', 'desc': '최고 레벨 10 (전설) 도달',      'category': '등급'},
    # 특별
    {'id': 'night_owl',     'name': '올빼미',           'icon': '🦉', 'desc': '밤 11시~새벽 2시 사이에 게임',  'category': '특별'},
    {'id': 'comeback',      'name': '컴백',             'icon': '🔄', 'desc': '7일 이상 쉬고 재접속',          'category': '특별'},
    {'id': 'lucky',         'name': '행운의 별',        'icon': '🌟', 'desc': '게임에서 희귀 아이템 획득 (별)','category': '특별'},
    {'id': 'speed_demon',   'name': '스피드 데몬',      'icon': '⚡', 'desc': '반응속도 게임 300ms 이하',       'category': '특별'},
    {'id': 'legend',        'name': '시블로그의 전설',  'icon': '👑', 'desc': '모든 배지를 달성한 전설',        'category': '특별'},
]

BADGE_IDS = {b['id']: b for b in BADGE_LIST}

def get_level_info(points):
    level, title, color = 1, LEVEL_THRESHOLDS[0][2], LEVEL_THRESHOLDS[0][3]
    for lv, threshold, name, col in LEVEL_THRESHOLDS:
        if points >= threshold:
            level, title, color = lv, name, col
    return level, title, color

def get_next_level_points(points):
    for lv, threshold, name, col in LEVEL_THRESHOLDS:
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
    def level_color(self):
        return get_level_info(self.points)[2]

    @property
    def next_level_points(self):
        return get_next_level_points(self.points)

    @property
    def level_progress(self):
        current_threshold = 0
        next_threshold = None
        for lv, threshold, name, col in LEVEL_THRESHOLDS:
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

    def get_badges(self):
        return list(self.badges.values_list('badge_id', flat=True))

    def has_badge(self, badge_id):
        return self.badges.filter(badge_id=badge_id).exists()

    def get_avatar_url(self, size=60):
        """실제 업로드된 아바타 or ui-avatars 폴백"""
        try:
            if self.avatar and self.avatar.name:
                return self.avatar.url
        except Exception:
            pass
        return f'https://ui-avatars.com/api/?name={self.user.username}&size={size}&background=6c63ff&color=fff'

    def award_badge(self, badge_id):
        """배지 부여 (없을 때만). 반환값: 새로 부여됐으면 badge info, 아니면 None"""
        if badge_id in BADGE_IDS and not self.has_badge(badge_id):
            UserBadge.objects.create(profile=self, badge_id=badge_id)
            return BADGE_IDS[badge_id]
        return None


class UserBadge(models.Model):
    profile = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='badges')
    badge_id = models.CharField(max_length=50)
    earned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('profile', 'badge_id')
        ordering = ['earned_at']

    def __str__(self):
        return f'{self.profile.user.username} - {self.badge_id}'

    @property
    def info(self):
        return BADGE_IDS.get(self.badge_id, {})


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if kwargs.get('raw', False):
        return
    if created:
        profile, is_new = UserProfile.objects.get_or_create(user=instance)
        if is_new:
            profile.award_badge('welcome')
    # 관리자(is_staff or is_superuser)는 항상 모든 배지 + 최대 포인트 보유
    if instance.is_staff or instance.is_superuser:
        profile, _ = UserProfile.objects.get_or_create(user=instance)
        for b in BADGE_LIST:
            profile.award_badge(b['id'])
        max_pts = LEVEL_THRESHOLDS[-1][1]
        if profile.points < max_pts:
            profile.points = max_pts
            profile.save(update_fields=['points'])

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    if kwargs.get('raw', False):
        return
    if hasattr(instance, 'profile'):
        instance.profile.save()
    else:
        UserProfile.objects.get_or_create(user=instance)
