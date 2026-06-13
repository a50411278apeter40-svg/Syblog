from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
import json
from .models import ChallengeScore, CHALLENGE_LIST, get_points_for_score
from accounts.models import UserProfile

@login_required
def challenge_list(request):
    scores = {}
    for game_id, _, _ in CHALLENGE_LIST:
        best = ChallengeScore.objects.filter(
            user=request.user, game_type=game_id
        ).order_by('-score').first()
        scores[game_id] = best
    return render(request, 'challenges/challenge_list.html', {
        'challenges': CHALLENGE_LIST,
        'scores': scores,
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
        
        return JsonResponse({
            'points_earned': points,
            'total_points': profile.points,
            'level': new_level,
            'level_title': profile.level_title,
            'level_up': level_up,
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

@login_required
def my_scores(request):
    scores = ChallengeScore.objects.filter(user=request.user).order_by('-played_at')[:50]
    total_points = sum(s.points_earned for s in scores)
    return render(request, 'challenges/my_scores.html', {
        'scores': scores,
        'total_points': total_points,
    })
