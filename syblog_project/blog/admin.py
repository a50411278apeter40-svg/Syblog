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


from .models import Notice

@admin.register(Notice)
class NoticeAdmin(admin.ModelAdmin):
    list_display  = ('title', 'level', 'is_active', 'created_by', 'created_at', 'expires_at')
    list_filter   = ('level', 'is_active')
    search_fields = ('title', 'content')
    list_editable = ('is_active',)

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

from .models import Bookmark, PostHistory, CommentLike, Notification, ScheduledPost

@admin.register(Bookmark)
class BookmarkAdmin(admin.ModelAdmin):
    list_display = ['user', 'post', 'created_at']

@admin.register(PostHistory)
class PostHistoryAdmin(admin.ModelAdmin):
    list_display = ['post', 'version', 'saved_by', 'saved_at']
    readonly_fields = ['post', 'title', 'content', 'saved_at', 'saved_by', 'version']

@admin.register(CommentLike)
class CommentLikeAdmin(admin.ModelAdmin):
    list_display = ['user', 'comment', 'created_at']

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['recipient', 'sender', 'ntype', 'message', 'is_read', 'created_at']
    list_filter = ['ntype', 'is_read']

@admin.register(ScheduledPost)
class ScheduledPostAdmin(admin.ModelAdmin):
    list_display = ['post', 'publish_at', 'is_published']

# ── AI 크레딧 & 웹개발 Admin ────────────────────────────────────
from blog.models import AiCredit, AiCreditLog, AiWebProject, AiWebSession

@admin.register(AiCredit)
class AiCreditAdmin(admin.ModelAdmin):
    list_display = ('user', 'credits', 'is_unlimited', 'total_used', 'updated_at')
    list_editable = ('credits', 'is_unlimited')
    search_fields = ('user__username',)
    list_filter = ('is_unlimited',)

@admin.register(AiCreditLog)
class AiCreditLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'action', 'amount', 'balance', 'note', 'created_at')
    list_filter = ('action',)
    search_fields = ('user__username',)
    readonly_fields = ('created_at',)

@admin.register(AiWebProject)
class AiWebProjectAdmin(admin.ModelAdmin):
    list_display = ('user', 'name', 'status', 'deploy_url', 'created_at')
    list_filter = ('status',)
    search_fields = ('user__username', 'name')

@admin.register(AiWebSession)
class AiWebSessionAdmin(admin.ModelAdmin):
    list_display = ('project', 'role', 'created_at')
    list_filter = ('role',)

# ── 게시판 관리 ──────────────────────────────────────────────────
from blog.models import Board, BoardPost, BoardComment, BoardPostLike, Suggestion

@admin.register(Board)
class BoardAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'icon', 'order', 'is_active')
    list_editable = ('order', 'is_active')
    prepopulated_fields = {'slug': ('name',)}

@admin.register(BoardPost)
class BoardPostAdmin(admin.ModelAdmin):
    list_display = ('title', 'board', 'author', 'views', 'is_pinned', 'is_blocked', 'created_at')
    list_filter = ('board', 'is_blocked', 'is_pinned')
    list_editable = ('is_pinned', 'is_blocked')
    search_fields = ('title', 'content', 'author__username')

@admin.register(BoardComment)
class BoardCommentAdmin(admin.ModelAdmin):
    list_display = ('post', 'author', 'content', 'is_blocked', 'created_at')
    list_filter = ('is_blocked',)
    list_editable = ('is_blocked',)

@admin.register(Suggestion)
class SuggestionAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'category', 'status', 'is_anonymous', 'created_at')
    list_filter = ('category', 'status')
    search_fields = ('title', 'content', 'author__username')
