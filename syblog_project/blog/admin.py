from django.contrib import admin
from .models import Post, Category, Tag, Comment, Series

@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ['title', 'author', 'category', 'created_at', 'view_count', 'like_count']
    list_filter = ['category', 'created_at']
    search_fields = ['title', 'content']
    actions = ['delete_selected']

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    prepopulated_fields = {'slug': ('name',)}

@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    prepopulated_fields = {'slug': ('name',)}

@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ['author', 'post', 'content', 'created_at', 'is_deleted']
    actions = ['delete_selected']

@admin.register(Series)
class SeriesAdmin(admin.ModelAdmin):
    list_display = ['title', 'author', 'created_at']
