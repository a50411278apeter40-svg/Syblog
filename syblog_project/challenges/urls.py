from django.urls import path
from . import views

app_name = 'challenges'

urlpatterns = [
    path('', views.challenge_list, name='list'),
    path('play/<str:game_type>/', views.play_game, name='play'),
    path('submit/', views.submit_score, name='submit'),
    path('my-scores/', views.my_scores, name='my_scores'),
]
