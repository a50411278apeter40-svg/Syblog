from django.contrib import admin
from .models import ChallengeScore

@admin.register(ChallengeScore)
class ChallengeScoreAdmin(admin.ModelAdmin):
    list_display = ['user', 'game_type', 'score', 'points_earned', 'played_at']
    list_filter = ['game_type']
    
    actions = ['delete_selected_scores']
