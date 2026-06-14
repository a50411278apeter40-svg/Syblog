from django.db import models
from django.contrib.auth.models import User

CHALLENGE_LIST = [
    ('dino', '🦕 공룡 점프게임', 'dino_game'),
    ('snake', '🐍 스네이크 게임', 'snake_game'),
    ('tetris', '🟦 테트리스', 'tetris_game'),
    ('flappy', '🐦 플래피 버드', 'flappy_game'),
    ('breakout', '🧱 벽돌깨기', 'breakout_game'),
    ('memory', '🃏 메모리 카드', 'memory_game'),
    ('typing', '⌨️ 타자 연습', 'typing_game'),
    ('2048', '🔢 2048', 'game_2048'),
    ('pong', '🏓 퐁 게임', 'pong_game'),
    ('minesweeper', '💣 지뢰찾기', 'minesweeper_game'),
    ('quiz', '❓ 파이썬 퀴즈', 'quiz_game'),
    ('platformer', '🎮 플랫폼 점프', 'platformer_game'),
    ('colorguess', '🎨 색깔 맞추기', 'colorguess_game'),
    ('wordscramble', '🔤 단어 맞추기', 'wordscramble_game'),
    ('reaction', '⚡ 반응속도 테스트', 'reaction_game'),
    ('sudoku', '🔢 스도쿠', 'sudoku_game'),
    ('ballshoot', '🎯 공 쏘기 게임', 'ballshoot_game'),
    ('arrows', '⬆️ 화살표 게임', 'arrows_game'),
    ('catch', '🪣 공 받기 게임', 'catch_game'),
    ('asteroid', '🚀 소행성 피하기', 'asteroid_game'),
    ('mario', '🍄 슈퍼 마리오', 'mario_game'),
    # ── 신규 10개 ──────────────────────────────
    ('racing', '🏎️ 레이싱 게임', 'racing_game'),
    ('shooter', '🔫 탑뷰 슈터', 'shooter_game'),
    ('chess', '♟️ 체스', 'chess_game'),
    ('rhythm', '🎵 리듬 게임', 'rhythm_game'),
    ('fishing', '🎣 낚시 게임', 'fishing_game'),
    ('towdefense', '🏰 타워 디펜스', 'towdefense_game'),
    ('match3', '💎 보석 매칭', 'match3_game'),
    ('agar', '🦠 세포 키우기', 'agar_game'),
    ('whack', '🔨 두더지 잡기', 'whack_game'),
    ('spacewar', '👾 우주 전쟁', 'spacewar_game'),
]

def get_points_for_score(game_type, score):
    tables = {
        'dino': [(500, 50), (200, 30), (100, 15), (0, 5)],
        'snake': [(50, 60), (30, 40), (15, 20), (0, 8)],
        'tetris': [(1000, 70), (500, 45), (200, 25), (0, 10)],
        'flappy': [(30, 55), (15, 35), (5, 18), (0, 7)],
        'breakout': [(80, 65), (50, 40), (20, 20), (0, 8)],
        'memory': [(90, 50), (70, 30), (50, 15), (0, 5)],
        'typing': [(100, 60), (70, 35), (40, 18), (0, 6)],
        '2048': [(2048, 80), (1024, 50), (512, 30), (0, 10)],
        'pong': [(10, 45), (5, 25), (1, 12), (0, 5)],
        'minesweeper': [(100, 70), (60, 45), (30, 20), (0, 8)],
        'quiz': [(10, 100), (7, 60), (5, 35), (0, 10)],
        'platformer': [(50, 55), (30, 35), (10, 18), (0, 6)],
        'colorguess': [(20, 50), (10, 30), (5, 15), (0, 5)],
        'wordscramble': [(15, 55), (10, 35), (5, 18), (0, 6)],
        'reaction': [(300, 70), (500, 45), (800, 20), (99999, 5)],
        'sudoku': [(100, 80), (70, 55), (40, 25), (0, 8)],
        'ballshoot': [(50, 55), (30, 35), (10, 15), (0, 5)],
        'arrows': [(100, 60), (60, 38), (30, 18), (0, 6)],
        'catch': [(80, 55), (50, 33), (20, 16), (0, 5)],
        'mario': [(15, 100), (10, 70), (5, 40), (0, 15)],
        'racing': [(100, 80), (60, 50), (30, 25), (0, 8)],
        'shooter': [(50, 75), (30, 48), (15, 25), (0, 8)],
        'chess': [(1, 120), (0, 30)],
        'rhythm': [(95, 90), (80, 60), (60, 35), (0, 10)],
        'fishing': [(20, 70), (10, 45), (5, 22), (0, 7)],
        'towdefense': [(20, 85), (10, 55), (5, 28), (0, 10)],
        'match3': [(500, 80), (300, 52), (100, 28), (0, 8)],
        'agar': [(500, 75), (200, 48), (50, 22), (0, 7)],
        'whack': [(40, 65), (25, 40), (10, 20), (0, 6)],
        'spacewar': [(100, 80), (50, 50), (20, 25), (0, 8)],
        'asteroid': [(100, 65), (50, 40), (20, 20), (0, 8)],
    }
    thresholds = tables.get(game_type, [(0, 5)])
    if game_type == 'reaction':
        for threshold, pts in thresholds:
            if score <= threshold:
                return pts
        return 5
    else:
        for threshold, pts in thresholds:
            if score >= threshold:
                return pts
    return 5

class ChallengeScore(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='challenge_scores')
    game_type = models.CharField(max_length=30)
    score = models.IntegerField(default=0)
    points_earned = models.IntegerField(default=0)
    played_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-played_at']

    def __str__(self):
        return f'{self.user.username} - {self.game_type}: {self.score}'
