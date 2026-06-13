from django.urls import path
from . import views

app_name = 'mail_system'

urlpatterns = [
    path('', views.inbox, name='inbox'),
    path('sent/', views.sent_box, name='sent'),
    path('<int:pk>/', views.mail_detail, name='detail'),
    path('compose/', views.compose, name='compose'),
    path('compose/<str:recipient_username>/', views.compose, name='compose_to'),
    path('delete/<int:pk>/', views.delete_mail, name='delete'),
    path('api/search-users/', views.search_users, name='search_users'),
]
