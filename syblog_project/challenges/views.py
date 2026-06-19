from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
import json
import datetime
from .models import ChallengeScore, CHALLENGE_LIST, get_points_for_score
from accounts.models import UserProfile, BADGE_LIST, BADGE_IDS, LEVEL_THRESHOLDS


def check_and_award_badges(profile, game_type, score, new_play_count):
    """게임 플레이 후 배지 조건 확인 및 부여. 새로 획득한 배지 목록 반환."""
    new_badges = []

    def award(badge_id):
        result = profile.award_badge(badge_id)
        if result:
            new_badges.append(result)

    # 첫 게임
    if new_play_count == 1:
        award('gamer')

    # 5가지 다른 게임
    played_games = set(ChallengeScore.objects.filter(user=profile.user).values_list('game_type', flat=True))
    if len(played_games) >= 5:
        award('game5')
    if len(played_games) >= len(CHALLENGE_LIST):
        award('game_all')

    # 총 플레이 횟수
    if new_play_count >= 50:
        award('play50')
    if new_play_count >= 100:
        award('play100')

    # 게임별 점수 배지
    if game_type == 'mario' and score >= 1000:
        award('mario_master')
    if game_type == 'snake' and score >= 30:
        award('snake_king')
    if game_type == 'tetris' and score >= 1000:
        award('tetris_god')
    if game_type == 'flappy' and score >= 20:
        award('flappy_ace')
    if game_type == 'dino' and score >= 500:
        award('dino_runner')
    if game_type == 'quiz' and score >= 10:
        award('quiz_genius')
    if game_type == 'reaction' and score <= 300:
        award('speed_demon')

    # 포인트 배지
    if profile.points >= 100:
        award('points100')
    if profile.points >= 500:
        award('points500')
    if profile.points >= 1500:
        award('points1500')

    # 레벨 배지
    if profile.level >= 5:
        award('level5')
    if profile.level >= 10:
        award('level10')

    # 야간 배지
    hour = datetime.datetime.now().hour
    if hour >= 23 or hour < 2:
        award('night_owl')

    # 모든 배지 달성 시 전설 배지
    all_badge_ids = set(b['id'] for b in BADGE_LIST if b['id'] != 'legend')
    if all_badge_ids.issubset(set(profile.get_badges())):
        award('legend')

    return new_badges


@login_required
def challenge_list(request):
    scores = {}
    for game_id, _, _ in CHALLENGE_LIST:
        best = ChallengeScore.objects.filter(
            user=request.user, game_type=game_id
        ).order_by('-score').first()
        scores[game_id] = best

    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    earned_badge_ids = profile.get_badges()
    earned_badges = [BADGE_IDS[bid] for bid in earned_badge_ids if bid in BADGE_IDS]

    return render(request, 'challenges/challenge_list.html', {
        'challenges': CHALLENGE_LIST,
        'scores': scores,
        'profile': profile,
        'all_badges': BADGE_LIST,
        'earned_badges': earned_badges,
        'earned_badge_ids': earned_badge_ids,
        'level_thresholds': LEVEL_THRESHOLDS,
    })


@login_required
def play_game(request, game_type):
    valid_games = [g[0] for g in CHALLENGE_LIST]
    if game_type not in valid_games:
        return redirect('challenges:list')
    game_name = next((g[1] for g in CHALLENGE_LIST if g[0] == game_type), game_type)
    best = ChallengeScore.objects.filter(
        user=request.user, game_type=game_type
    ).order_by('-score').first()
    return render(request, f'challenges/games/{game_type}.html', {
        'game_type': game_type,
        'game_name': game_name,
        'best_score': best,
    })


@login_required
@require_POST
def submit_score(request):
    try:
        data = json.loads(request.body)
        game_type = data.get('game_type')
        score = int(data.get('score', 0))

        valid_games = [g[0] for g in CHALLENGE_LIST]
        if game_type not in valid_games:
            return JsonResponse({'error': 'Invalid game'}, status=400)

        points = get_points_for_score(game_type, score)

        ChallengeScore.objects.create(
            user=request.user,
            game_type=game_type,
            score=score,
            points_earned=points,
        )

        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        old_level = profile.level
        profile.points += points
        profile.save()
        new_level = profile.level
        level_up = new_level > old_level

        # 배지 체크
        play_count = ChallengeScore.objects.filter(user=request.user).count()
        new_badges = check_and_award_badges(profile, game_type, score, play_count)

        return JsonResponse({
            'points_earned': points,
            'total_points': profile.points,
            'level': new_level,
            'level_title': profile.level_title,
            'level_color': profile.level_color,
            'level_up': level_up,
            'level_progress': profile.level_progress,
            'new_badges': new_badges,
            'next_level_points': profile.next_level_points,
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@login_required
def my_scores(request):
    scores = ChallengeScore.objects.filter(user=request.user).order_by('-played_at')[:50]
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    earned_badge_ids = profile.get_badges()
    earned_badges = [BADGE_IDS[bid] for bid in earned_badge_ids if bid in BADGE_IDS]
    # 카테고리별 배지 분류
    categories = {}
    for b in BADGE_LIST:
        cat = b['category']
        if cat not in categories:
            categories[cat] = []
        categories[cat].append({**b, 'earned': b['id'] in earned_badge_ids})

    return render(request, 'challenges/my_scores.html', {
        'scores': scores,
        'profile': profile,
        'all_badges': BADGE_LIST,
        'earned_badges': earned_badges,
        'earned_badge_ids': earned_badge_ids,
        'badge_categories': categories,
        'level_thresholds': LEVEL_THRESHOLDS,
    })


@login_required
def badge_list(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    earned_badge_ids = profile.get_badges()
    categories = {}
    for b in BADGE_LIST:
        cat = b['category']
        if cat not in categories:
            categories[cat] = []
        categories[cat].append({**b, 'earned': b['id'] in earned_badge_ids})
    return render(request, 'challenges/badges.html', {
        'profile': profile,
        'badge_categories': categories,
        'earned_count': len(earned_badge_ids),
        'total_count': len(BADGE_LIST),
        'level_thresholds': LEVEL_THRESHOLDS,
    })
