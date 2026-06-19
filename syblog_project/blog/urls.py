from django.urls import path
from . import views

app_name = 'blog'

urlpatterns = [
    path('search/', views.search_view, name='search'),
    path('search_old/<str:q>/', views.PostSearch.as_view(), name='search_old'),
    path('delete_comment/<int:pk>/', views.delete_comment, name='delete_comment'),
    path('update_comment/<int:pk>/', views.CommentUpdate.as_view(), name='update_comment'),
    path('update_post/<int:pk>/', views.PostUpdate.as_view(), name='update_post'),
    path('create_post/', views.PostCreate.as_view(), name='create_post'),
    path('tag/<str:slug>/', views.tag_page, name='tag'),
    path('category/<str:slug>/', views.category_page, name='category'),
    path('<int:pk>/new_comment/', views.new_comment, name='new_comment'),
    path('<int:pk>/like/', views.like_post, name='like_post'),
    path('<int:pk>/', views.PostDetail.as_view(), name='post_detail'),
    path('series/', views.series_list, name='series_list'),
    path('series/create/', views.series_create, name='series_create'),
    path('series/my/', views.my_series, name='my_series'),
    path('series/<int:pk>/', views.series_detail, name='series_detail'),
    path('series/<int:pk>/edit/', views.series_edit, name='series_edit'),
    path('series/<int:pk>/delete/', views.SeriesDelete.as_view(), name='series_delete'),
    path('admin-dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('admin-delete-post/<int:pk>/', views.admin_delete_post, name='admin_delete_post'),
    path('backup-to-github/', views.backup_to_github, name='backup_to_github'),
    path('restore-from-github/', views.restore_from_github, name='restore_from_github'),
    path('spellcheck/', views.spellcheck_proxy, name='spellcheck'),
    path('', views.PostList.as_view(), name='index'),
]
