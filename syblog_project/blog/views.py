from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import ListView, DetailView, CreateView, UpdateView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.decorators import login_required
from django.utils.text import slugify
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import JsonResponse
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from .models import Post, Category, Tag, Comment, Series, check_banned_keywords
from .forms import CommentForm, PostForm, SeriesForm
from django.contrib.auth.models import User

class PostList(ListView):
    model = Post
    ordering = '-pk'
    paginate_by = 5
    template_name = 'blog/post_list.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # removed category query from view
        context['no_category_post_count'] = Post.objects.filter(category=None).count()
        context['recent_series'] = Series.objects.order_by('-created_at')[:5]
        return context

class PostDetail(DetailView):
    model = Post
    template_name = 'blog/post_detail.html'

    def get_object(self):
        obj = super().get_object()
        obj.view_count += 1
        obj.save(update_fields=['view_count'])
        return obj

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # removed category query from view
        context['no_category_post_count'] = Post.objects.filter(category=None).count()
        context['comment_form'] = CommentForm()
        context['comments'] = self.object.comments.filter(parent=None, is_deleted=False).order_by('created_at')
        if self.object.series:
            context['series_posts'] = self.object.series.posts.order_by('series_order')
        return context

class PostCreate(LoginRequiredMixin, CreateView):
    model = Post
    form_class = PostForm
    template_name = 'blog/post_form.html'

    def form_valid(self, form):
        is_banned, kw = check_banned_keywords(form.cleaned_data.get('title', '') + ' ' + form.cleaned_data.get('content', ''))
        if is_banned:
            form.add_error(None, f'금지된 키워드가 포함되어 있습니다: "{kw}"')
            return self.form_invalid(form)
        
        form.instance.author = self.request.user
        response = super().form_valid(form)
        # 배지 체크
        post_count = Post.objects.filter(author=self.request.user).count()
        _award_blog_badge(self.request.user, 'first_post')
        if post_count >= 5: _award_blog_badge(self.request.user, 'writer5')
        if post_count >= 20: _award_blog_badge(self.request.user, 'writer20')
        
        tags_str = self.request.POST.get('tags_str')
        if tags_str:
            tags_str = tags_str.strip().replace(',', ';')
            for t in tags_str.split(';'):
                t = t.strip()
                if t:
                    tag, _ = Tag.objects.get_or_create(name=t)
                    if not tag.slug:
                        tag.slug = slugify(t, allow_unicode=True)
                        tag.save()
                    self.object.tags.add(tag)
        return response

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields['series'].queryset = Series.objects.filter(author=self.request.user)
        return form

class PostUpdate(LoginRequiredMixin, UpdateView):
    model = Post
    form_class = PostForm
    template_name = 'blog/post_update_form.html'

    def dispatch(self, request, *args, **kwargs):
        obj = self.get_object()
        if not (request.user == obj.author or request.user.is_superuser or request.user.is_staff):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        is_banned, kw = check_banned_keywords(form.cleaned_data.get('title', '') + ' ' + form.cleaned_data.get('content', ''))
        if is_banned:
            form.add_error(None, f'금지된 키워드가 포함되어 있습니다: "{kw}"')
            return self.form_invalid(form)
        response = super().form_valid(form)
        self.object.tags.clear()
        tags_str = self.request.POST.get('tags_str')
        if tags_str:
            tags_str = tags_str.strip().replace(',', ';')
            for t in tags_str.split(';'):
                t = t.strip()
                if t:
                    tag, _ = Tag.objects.get_or_create(name=t)
                    if not tag.slug:
                        tag.slug = slugify(t, allow_unicode=True)
                        tag.save()
                    self.object.tags.add(tag)
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.object.tags.exists():
            context['tags_str_default'] = '; '.join(t.name for t in self.object.tags.all())
        return context

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields['series'].queryset = Series.objects.filter(author=self.request.user)
        return form

def category_page(request, slug):
    if slug == 'no_category':
        category = '미분류'
        post_list = Post.objects.filter(category=None)
    else:
        category = get_object_or_404(Category, slug=slug)
        post_list = Post.objects.filter(category=category)
    return render(request, 'blog/post_list.html', {
        'post_list': post_list,
        'categories': Category.objects.all(),
        'no_category_post_count': Post.objects.filter(category=None).count(),
        'category': category,
    })

def tag_page(request, slug):
    tag = get_object_or_404(Tag, slug=slug)
    return render(request, 'blog/post_list.html', {
        'post_list': tag.post_set.all(),
        'tag': tag,
        'categories': Category.objects.all(),
        'no_category_post_count': Post.objects.filter(category=None).count(),
    })

@login_required
def new_comment(request, pk):
    post = get_object_or_404(Post, pk=pk)
    if request.method == 'POST':
        form = CommentForm(request.POST)
        if form.is_valid():
            content = form.cleaned_data['content']
            is_banned, kw = check_banned_keywords(content)
            if is_banned:
                messages.error(request, f'금지된 키워드가 포함되어 있습니다: "{kw}"')
                return redirect(post.get_absolute_url())
            comment = form.save(commit=False)
            comment.post = post
            comment.author = request.user
            parent_id = request.POST.get('parent_id')
            if parent_id:
                try:
                    parent = Comment.objects.get(pk=int(parent_id))
                    comment.parent = parent
                except:
                    pass
            comment.save()
            _award_blog_badge(request.user, "first_comment")
            return redirect(comment.get_absolute_url())
    return redirect(post.get_absolute_url())

class CommentUpdate(LoginRequiredMixin, UpdateView):
    model = Comment
    form_class = CommentForm
    template_name = 'blog/comment_form.html'

    def dispatch(self, request, *args, **kwargs):
        obj = self.get_object()
        if not (request.user == obj.author or request.user.is_superuser):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

def delete_comment(request, pk):
    comment = get_object_or_404(Comment, pk=pk)
    post = comment.post
    if request.user.is_authenticated and (request.user == comment.author or request.user.is_superuser):
        comment.is_deleted = True
        comment.content = '삭제된 댓글입니다.'
        comment.save()
        return redirect(post.get_absolute_url())
    raise PermissionDenied

class PostSearch(PostList):
    paginate_by = None

    def get_queryset(self):
        q = self.kwargs['q']
        return Post.objects.filter(
            Q(title__contains=q) | Q(tags__name__contains=q)
        ).distinct()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        q = self.kwargs['q']
        context['search_info'] = f'검색: {q} ({self.get_queryset().count()}건)'
        return context

@login_required
def like_post(request, pk):
    post = get_object_or_404(Post, pk=pk)
    if request.user in post.likes.all():
        post.likes.remove(request.user)
        liked = False
    else:
        post.likes.add(request.user)
        liked = True
        _award_blog_badge(request.user, "first_like")
        if post.like_count >= 10: _award_blog_badge(post.author, "popular") if post.author else None
    post.like_count = post.likes.count()
    post.save(update_fields=['like_count'])
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'liked': liked, 'count': post.like_count})
    return redirect(post.get_absolute_url())

# ── Series Views ──
@login_required
def series_create(request):
    if request.method == 'POST':
        form = SeriesForm(request.POST, request.FILES)
        if form.is_valid():
            series = form.save(commit=False)
            series.author = request.user
            series.save()
            messages.success(request, '시리즈가 생성되었습니다!')
            return redirect('blog:series_detail', pk=series.pk)
    else:
        form = SeriesForm()
    return render(request, 'blog/series_form.html', {'form': form})

def series_detail(request, pk):
    series = get_object_or_404(Series, pk=pk)
    posts = series.posts.order_by('series_order')
    return render(request, 'blog/series_detail.html', {'series': series, 'posts': posts})

def series_list(request):
    all_series = Series.objects.all().order_by('-created_at')
    return render(request, 'blog/series_list.html', {'series_list': all_series})

@login_required
def my_series(request):
    series_list = Series.objects.filter(author=request.user).order_by('-created_at')
    return render(request, 'blog/my_series.html', {'series_list': series_list})

@login_required
def series_edit(request, pk):
    series = get_object_or_404(Series, pk=pk)
    if series.author != request.user and not request.user.is_superuser:
        raise PermissionDenied
    if request.method == 'POST':
        form = SeriesForm(request.POST, request.FILES, instance=series)
        if form.is_valid():
            form.save()
            messages.success(request, '시리즈가 수정되었습니다!')
            return redirect('blog:series_detail', pk=series.pk)
    else:
        form = SeriesForm(instance=series)
    return render(request, 'blog/series_form.html', {'form': form, 'series': series})

# ── Admin Views ──
@staff_member_required
def admin_dashboard(request):
    from accounts.models import UserProfile
    from challenges.models import ChallengeScore
    from mail_system.models import Mail
    stats = {
        'total_users': User.objects.count(),
        'total_posts': Post.objects.count(),
        'total_comments': Comment.objects.count(),
        'blocked_users': UserProfile.objects.filter(is_blocked=True).count(),
        'total_mails': Mail.objects.count(),
        'total_scores': ChallengeScore.objects.count(),
    }
    recent_posts = Post.objects.order_by('-created_at')[:10]
    recent_users = User.objects.order_by('-date_joined')[:10]
    return render(request, 'blog/admin_dashboard.html', {
        'stats': stats,
        'recent_posts': recent_posts,
        'recent_users': recent_users,
    })

@staff_member_required
def admin_delete_post(request, pk):
    if request.method == 'POST':
        post = get_object_or_404(Post, pk=pk)
        post.delete()
        messages.success(request, '게시글이 삭제되었습니다.')
    return redirect('blog:admin_dashboard')


# ── GitHub 백업 / 복원 ──
import json
import base64
import urllib.request
import urllib.parse
import os
import datetime

def _github_api(method, path, token, data=None):
    """GitHub API 호출 헬퍼"""
    url = f'https://api.github.com{path}'
    headers = {
        'Authorization': f'token {token}',
        'Accept': 'application/vnd.github.v3+json',
        'Content-Type': 'application/json',
        'User-Agent': 'SyBlog-Backup/1.0',
    }
    body = json.dumps(data).encode('utf-8') if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode('utf-8')), resp.status
    except urllib.error.HTTPError as e:
        err_body = e.read().decode('utf-8')
        return json.loads(err_body) if err_body else {}, e.code

from django.core.management import call_command
from io import StringIO
import tempfile
import base64
import json

from .utils_backup import perform_backup, perform_restore

@staff_member_required
def backup_to_github(request):
    if request.method != 'POST':
        return redirect('blog:admin_dashboard')
    
    success, msg = perform_backup()
    if success:
        messages.success(request, f'✅ GitHub 전체 백업 완료! (모든 데이터 저장됨) → {msg}')
    else:
        messages.error(request, f'❌ 백업 실패: {msg}')
    return redirect('blog:admin_dashboard')

@staff_member_required
def restore_from_github(request):
    if request.method != 'POST':
        return redirect('blog:admin_dashboard')
        
    success, msg = perform_restore()
    if success:
        messages.success(request, f'✅ 완벽 복원 완료! 기존 데이터가 완전히 지워지고 {msg} 파일의 모든 정보로 덮어씌워졌습니다.')
    else:
        messages.error(request, f'❌ 복원 실패: {msg}')
    return redirect('blog:admin_dashboard')

# ── 카테고리 context processor (전역) ──
from blog.models import Category as BlogCategory

def global_categories(request):
    return {
        'categories': BlogCategory.objects.all(),
        'no_category_post_count': Post.objects.filter(category=None).count(),
    }


from django.views.generic import DeleteView
from django.urls import reverse_lazy

class SeriesDelete(LoginRequiredMixin, DeleteView):
    model = Series
    success_url = reverse_lazy('blog:series_list')

    def dispatch(self, request, *args, **kwargs):
        obj = self.get_object()
        if not (request.user == obj.author or request.user.is_superuser):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

def search_view(request):
    q = request.GET.get('q', '')
    cat_slug = request.GET.get('category', '')
    tag_slug = request.GET.get('tag', '')
    sort = request.GET.get('sort', '-created_at')

    post_list = Post.objects.all().distinct()

    if q:
        post_list = post_list.filter(
            Q(title__icontains=q) |
            Q(content__icontains=q) |
            Q(author__username__icontains=q)
        )
    if cat_slug:
        post_list = post_list.filter(category__slug=cat_slug)
    if tag_slug:
        post_list = post_list.filter(tags__slug=tag_slug)

    if sort == 'views':
        post_list = post_list.order_by('-view_count', '-created_at')
    elif sort == 'likes':
        post_list = post_list.order_by('-like_count', '-created_at')
    else:
        post_list = post_list.order_by('-created_at')

    context = {
        'post_list': post_list,
        'q': q,
        'selected_cat': cat_slug,
        'selected_tag': tag_slug,
        'sort': sort,
        'categories': Category.objects.all(),
        'tags': Tag.objects.all(),
        'no_category_post_count': Post.objects.filter(category=None).count()
    }
    return render(request, 'blog/search.html', context)
