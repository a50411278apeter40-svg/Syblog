from django.urls import path
from . import views

urlpatterns = [
    path('search/<str:q>/', views.PostSearch.as_view()),
    path('delete_comment/<int:pk>/', views.delete_comment),
    path('update_comment/<int:pk>/', views.CommentUpdate.as_view()),
    path('update_post/<int:pk>/', views.PostUpdate.as_view()),
    path('create_post/', views.PostCreate.as_view()),
    path('tag/<str:slug>/', views.tag_page),
    path('category/<str:slug>/', views.category_page),
    path('<int:pk>/new_comment/', views.new_comment),
    path('<int:pk>/like/', views.like_post),
    path('<int:pk>/', views.PostDetail.as_view()),
    path('series/', views.series_list, name='series_list'),
    path('series/create/', views.series_create, name='series_create'),
    path('series/my/', views.my_series, name='my_series'),
    path('series/<int:pk>/', views.series_detail, name='series_detail'),
    path('series/<int:pk>/edit/', views.series_edit, name='series_edit'),
    path('admin-dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('admin-delete-post/<int:pk>/', views.admin_delete_post, name='admin_delete_post'),
    path('', views.PostList.as_view()),
]
