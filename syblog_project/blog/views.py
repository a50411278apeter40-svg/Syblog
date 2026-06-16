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
        context['categories'] = Category.objects.all()
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
        context['categories'] = Category.objects.all()
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

@staff_member_required
def backup_to_github(request):
    if request.method != 'POST':
        return redirect('blog:admin_dashboard')

    token = os.environ.get('GITHUB_TOKEN', '')
    repo = os.environ.get('GITHUB_REPO', 'a50411278apeter40-svg/Syblog')
    if not token:
        messages.error(request, '❌ GITHUB_TOKEN 환경변수가 설정되지 않았습니다.')
        return redirect('blog:admin_dashboard')

    # ── 모든 데이터 수집 ──
    from accounts.models import UserProfile
    from challenges.models import ChallengeScore
    from mail_system.models import Mail

    # Posts
    posts_data = []
    for p in Post.objects.select_related('author', 'category', 'series').prefetch_related('tags', 'likes').all():
        posts_data.append({
            'id': p.pk,
            'title': p.title,
            'hook_text': p.hook_text,
            'content': p.content,
            'author': p.author.username if p.author else None,
            'category': p.category.name if p.category else None,
            'tags': [t.name for t in p.tags.all()],
            'series': p.series.title if p.series else None,
            'series_order': p.series_order,
            'view_count': p.view_count,
            'like_count': p.like_count,
            'likes': [u.username for u in p.likes.all()],
            'created_at': p.created_at.isoformat(),
            'updated_at': p.updated_at.isoformat(),
        })

    # Comments
    comments_data = []
    for c in Comment.objects.select_related('post', 'author', 'parent').all():
        comments_data.append({
            'id': c.pk,
            'post_id': c.post.pk,
            'author': c.author.username,
            'content': c.content,
            'parent_id': c.parent.pk if c.parent else None,
            'is_deleted': c.is_deleted,
            'created_at': c.created_at.isoformat(),
        })

    # Categories
    categories_data = [{'id': c.pk, 'name': c.name, 'slug': c.slug} for c in Category.objects.all()]

    # Tags
    tags_data = [{'id': t.pk, 'name': t.name, 'slug': t.slug} for t in Tag.objects.all()]

    # Series
    series_data = []
    for s in Series.objects.select_related('author').all():
        series_data.append({
            'id': s.pk,
            'title': s.title,
            'description': s.description,
            'author': s.author.username,
            'created_at': s.created_at.isoformat(),
        })

    # Users
    users_data = []
    for u in User.objects.all():
        users_data.append({
            'id': u.pk,
            'username': u.username,
            'email': u.email,
            'is_staff': u.is_staff,
            'is_superuser': u.is_superuser,
            'date_joined': u.date_joined.isoformat(),
        })

    # UserProfiles
    profiles_data = []
    for p in UserProfile.objects.select_related('user').all():
        profiles_data.append({
            'user': p.user.username,
            'bio': getattr(p, 'bio', ''),
            'is_blocked': p.is_blocked,
        })

    # Mails
    mails_data = []
    for m in Mail.objects.select_related('sender', 'recipient').all():
        mails_data.append({
            'id': m.pk,
            'sender': m.sender.username,
            'recipient': m.recipient.username,
            'subject': m.subject,
            'body': m.body,
            'is_read': m.is_read,
            'sent_at': m.sent_at.isoformat(),
        })

    # ChallengeScores
    scores_data = []
    for s in ChallengeScore.objects.select_related('user').all():
        scores_data.append({
            'id': s.pk,
            'user': s.user.username,
            'game': s.game,
            'score': s.score,
            'created_at': s.created_at.isoformat(),
        })

    backup = {
        'backup_time': datetime.datetime.now().isoformat(),
        'posts': posts_data,
        'comments': comments_data,
        'categories': categories_data,
        'tags': tags_data,
        'series': series_data,
        'users': users_data,
        'user_profiles': profiles_data,
        'mails': mails_data,
        'challenge_scores': scores_data,
    }

    backup_json = json.dumps(backup, ensure_ascii=False, indent=2)
    backup_b64 = base64.b64encode(backup_json.encode('utf-8')).decode('utf-8')

    now_str = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    file_path = f'backups/syblog_backup_{now_str}.json'

    # GitHub에 파일 업로드
    commit_msg = f'🔒 자동 백업 {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}'
    result, status = _github_api('PUT', f'/repos/{repo}/contents/{file_path}', token, {
        'message': commit_msg,
        'content': backup_b64,
    })

    if status in (200, 201):
        post_count = len(posts_data)
        comment_count = len(comments_data)
        messages.success(request,
            f'✅ GitHub 백업 완료! '
            f'게시글 {post_count}개, 댓글 {comment_count}개, '
            f'사용자 {len(users_data)}명, 메일 {len(mails_data)}개, '
            f'챌린지기록 {len(scores_data)}개 → {file_path}'
        )
    else:
        messages.error(request, f'❌ 백업 실패: {result.get("message", "알 수 없는 오류")}')

    return redirect('blog:admin_dashboard')


@staff_member_required
def restore_from_github(request):
    if request.method != 'POST':
        return redirect('blog:admin_dashboard')

    token = os.environ.get('GITHUB_TOKEN', '')
    repo = os.environ.get('GITHUB_REPO', 'a50411278apeter40-svg/Syblog')
    if not token:
        messages.error(request, '❌ GITHUB_TOKEN 환경변수가 설정되지 않았습니다.')
        return redirect('blog:admin_dashboard')

    # 최신 백업 파일 목록 가져오기
    result, status = _github_api('GET', f'/repos/{repo}/contents/backups', token)
    if status != 200:
        messages.error(request, f'❌ 백업 파일 목록 로드 실패: {result.get("message", "")}')
        return redirect('blog:admin_dashboard')

    if not result:
        messages.error(request, '❌ 백업 파일이 없습니다.')
        return redirect('blog:admin_dashboard')

    # 가장 최신 파일 선택
    backup_files = sorted([f for f in result if f['name'].endswith('.json')], key=lambda x: x['name'], reverse=True)
    if not backup_files:
        messages.error(request, '❌ 백업 JSON 파일이 없습니다.')
        return redirect('blog:admin_dashboard')

    latest = backup_files[0]
    file_result, file_status = _github_api('GET', f'/repos/{repo}/contents/{latest["path"]}', token)
    if file_status != 200:
        messages.error(request, '❌ 백업 파일 로드 실패')
        return redirect('blog:admin_dashboard')

    content_b64 = file_result.get('content', '').replace('\n', '')
    backup = json.loads(base64.b64decode(content_b64).decode('utf-8'))

    restored = {'posts': 0, 'comments': 0, 'categories': 0, 'tags': 0}

    # 카테고리 복원
    for c in backup.get('categories', []):
        Category.objects.get_or_create(slug=c['slug'], defaults={'name': c['name']})
        restored['categories'] += 1

    # 태그 복원
    for t in backup.get('tags', []):
        Tag.objects.get_or_create(slug=t['slug'], defaults={'name': t['name']})
        restored['tags'] += 1

    # 게시글 복원 (없는 것만)
    for p in backup.get('posts', []):
        if not Post.objects.filter(pk=p['id']).exists():
            try:
                author = User.objects.filter(username=p['author']).first()
                category = Category.objects.filter(name=p['category']).first() if p['category'] else None
                post = Post.objects.create(
                    pk=p['id'],
                    title=p['title'],
                    hook_text=p.get('hook_text', ''),
                    content=p['content'],
                    author=author,
                    category=category,
                    series_order=p.get('series_order', 0),
                    view_count=p.get('view_count', 0),
                    like_count=p.get('like_count', 0),
                )
                for tag_name in p.get('tags', []):
                    tag, _ = Tag.objects.get_or_create(name=tag_name,
                        defaults={'slug': slugify(tag_name, allow_unicode=True)})
                    post.tags.add(tag)
                restored['posts'] += 1
            except Exception:
                pass

    # 댓글 복원
    for c in backup.get('comments', []):
        if not Comment.objects.filter(pk=c['id']).exists():
            try:
                post = Post.objects.filter(pk=c['post_id']).first()
                author = User.objects.filter(username=c['author']).first()
                if post and author:
                    Comment.objects.create(
                        pk=c['id'],
                        post=post,
                        author=author,
                        content=c['content'],
                        is_deleted=c.get('is_deleted', False),
                    )
                    restored['comments'] += 1
            except Exception:
                pass

    messages.success(request,
        f'✅ 복원 완료! ({latest["name"]}) — '
        f'게시글 {restored["posts"]}개, 댓글 {restored["comments"]}개, '
        f'카테고리 {restored["categories"]}개, 태그 {restored["tags"]}개 복원됨'
    )
    return redirect('blog:admin_dashboard')


# ── 카테고리 context processor (전역) ──
from blog.models import Category as BlogCategory

def global_categories(request):
    return {
        'categories': BlogCategory.objects.all(),
        'no_category_post_count': Post.objects.filter(category=None).count(),
    }
