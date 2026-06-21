from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import ListView, DetailView, CreateView, UpdateView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.decorators import login_required
from django.utils.text import slugify
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import JsonResponse, HttpResponse, StreamingHttpResponse, FileResponse
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.views.decorators.http import require_POST
from .models import Post, Category, Tag, Comment, Series, check_banned_keywords
from .forms import CommentForm, PostForm, SeriesForm, PostFormWithSchedule
from django.contrib.auth.models import User


# ── 배지/포인트 헬퍼 ─────────────────────────────────────────
def _award_blog_badge(user, badge_id):
    """유저에게 배지 부여 (없을 때만)"""
    try:
        from accounts.models import UserProfile
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.award_badge(badge_id)
    except Exception:
        pass

def _add_points(user, amount):
    """유저 포인트 적립 (상한 없음)"""
    try:
        from accounts.models import UserProfile
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.points += amount
        profile.save(update_fields=['points'])
    except Exception:
        pass

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
    form_class = PostFormWithSchedule
    template_name = 'blog/post_form.html'

    def form_valid(self, form):
        is_banned, kw = check_banned_keywords(form.cleaned_data.get('title', '') + ' ' + form.cleaned_data.get('content', ''))
        if is_banned:
            form.add_error(None, f'금지된 키워드가 포함되어 있습니다: "{kw}"')
            return self.form_invalid(form)
        
        form.instance.author = self.request.user
        response = super().form_valid(form)
        # 예약 게시 처리
        publish_at = form.cleaned_data.get('publish_at')
        if publish_at:
            ScheduledPost.objects.create(post=self.object, publish_at=publish_at)
        # 포인트 적립 (글 작성 20pt)
        _add_points(self.request.user, 20)
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
        # 예약 게시 처리
        publish_at = self.request.POST.get('publish_at', '').strip()
        if publish_at:
            from .models import ScheduledPost
            from django.utils.dateparse import parse_datetime
            dt = parse_datetime(publish_at)
            if dt:
                ScheduledPost.objects.update_or_create(post=self.object, defaults={'publish_at': dt, 'is_published': False})
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
        # 수정 전 버전 히스토리 저장
        try:
            from .models import PostHistory
            obj = self.get_object()
            last = PostHistory.objects.filter(post=obj).first()
            next_ver = (last.version + 1) if last else 1
            PostHistory.objects.create(post=obj, title=obj.title, content=obj.content, saved_by=self.request.user, version=next_ver)
        except Exception:
            pass
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
            _add_points(request.user, 5)
            # 알림 전송
            try:
                from .models import Notification as _Notif
                if comment.parent and comment.parent.author and comment.parent.author != request.user:
                    _Notif.objects.create(recipient=comment.parent.author, sender=request.user, ntype='reply',
                        message=f'{request.user.username}님이 답글을 달았습니다.',
                        url=comment.get_absolute_url())
                elif not comment.parent and post.author and post.author != request.user:
                    _Notif.objects.create(recipient=post.author, sender=request.user, ntype='comment',
                        message=f'{request.user.username}님이 댓글을 달았습니다.',
                        url=comment.get_absolute_url())
                # @멘션 처리
                import re as _re
                _mentions = _re.findall(r'@(\w+)', comment.content)
                from django.contrib.auth.models import User as _MU
                for _uname in set(_mentions):
                    try:
                        _mu = _MU.objects.get(username=_uname)
                        if _mu != request.user:
                            _Notif.objects.get_or_create(
                                recipient=_mu, sender=request.user, ntype='mention',
                                defaults={
                                    'message': f'{request.user.username}님이 댓글에서 회원님을 멘션했습니다.',
                                    'url': comment.get_absolute_url()
                                }
                            )
                    except Exception:
                        pass
            except Exception:
                pass
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
        # 좋아요 알림
        try:
            from .models import Notification as _N2
            if post.author and post.author != request.user:
                _N2.objects.create(
                    recipient=post.author, sender=request.user, ntype='like',
                    message=f'{request.user.username}님이 "{post.title}"에 좋아요를 눌렀습니다.',
                    url=post.get_absolute_url()
                )
        except Exception:
            pass
        # 좋아요 알림
        try:
            from .models import Notification as _Notif
            if post.author and post.author != request.user:
                _Notif.objects.create(recipient=post.author, sender=request.user, ntype='like',
                    message=f'{request.user.username}님이 게시글을 좋아합니다.',
                    url=post.get_absolute_url())
        except Exception:
            pass
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
    import shutil, os as _os
    from django.conf import settings as _settings
    from accounts.models import UserProfile
    from challenges.models import ChallengeScore
    from mail_system.models import Mail

    # ── 스토리지 계산 ─────────────────────────────────────────
    def _dir_size(path):
        total = 0
        if _os.path.exists(path):
            for dirpath, dirnames, filenames in _os.walk(path):
                for fname in filenames:
                    try:
                        total += _os.path.getsize(_os.path.join(dirpath, fname))
                    except OSError:
                        pass
        return total

    def _fmt(b):
        if b >= 1073741824: return f"{b/1073741824:.2f} GB"
        if b >= 1048576:    return f"{b/1048576:.2f} MB"
        if b >= 1024:       return f"{b/1024:.1f} KB"
        return f"{b} B"

    media_root  = getattr(_settings, 'MEDIA_ROOT',  '')
    static_root = getattr(_settings, 'STATIC_ROOT', '')
    db_path     = _os.path.join(_settings.BASE_DIR, 'db.sqlite3')

    media_bytes  = _dir_size(media_root)
    static_bytes = _dir_size(static_root)
    db_bytes     = _os.path.getsize(db_path) if _os.path.exists(db_path) else 0
    app_total    = media_bytes + static_bytes + db_bytes

    disk_total, disk_used, disk_free = shutil.disk_usage('/')

    storage = {
        'media_fmt':       _fmt(media_bytes),
        'static_fmt':      _fmt(static_bytes),
        'db_fmt':          _fmt(db_bytes),
        'app_total_fmt':   _fmt(app_total),
        'disk_used_fmt':   _fmt(disk_used),
        'disk_total_fmt':  _fmt(disk_total),
        'disk_free_fmt':   _fmt(disk_free),
        'disk_pct':        round(disk_used / disk_total * 100, 1),
        'app_pct':         round(app_total  / disk_total * 100, 2),
        'media_pct':       round(media_bytes  / disk_total * 100, 2) if disk_total else 0,
    }

    stats = {
        'total_users':    User.objects.count(),
        'total_posts':    Post.objects.count(),
        'total_comments': Comment.objects.count(),
        'blocked_users':  UserProfile.objects.filter(is_blocked=True).count(),
        'total_mails':    Mail.objects.count(),
        'total_scores':   ChallengeScore.objects.count(),
    }
    recent_posts = Post.objects.order_by('-created_at')[:10]
    recent_users = User.objects.order_by('-date_joined')[:10]
    return render(request, 'blog/admin_dashboard.html', {
        'stats':        stats,
        'storage':      storage,
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


# ── 맞춤법 검사 proxy ─────────────────────────────────────────────────
import urllib.request
import urllib.parse

def spellcheck_proxy(request):
    """
    클라이언트 JS → 이 뷰 → LanguageTool API (서버사이드, CORS 우회)
    한국어(ko-KR 감지) → 내장 KO_RULES 적용
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)

    import json as _json
    try:
        body = _json.loads(request.body)
        text = body.get('text', '').strip()
        lang = body.get('language', 'auto')
    except Exception:
        return JsonResponse({'matches': []})

    if not text:
        return JsonResponse({'matches': []})

    # 한국어 감지 (한글 유니코드 비율)
    korean_chars = sum(1 for ch in text if '\uAC00' <= ch <= '\uD7A3' or '\u1100' <= ch <= '\u11FF')
    is_korean = korean_chars / max(len(text), 1) > 0.15

    if is_korean:
        # 서버사이드 KO_RULES (훨씬 방대한 규칙)
        matches = _ko_spellcheck(text)
        return JsonResponse({'matches': matches, 'lang_detected': 'ko-KR'})

    # LanguageTool API 호출
    try:
        payload = urllib.parse.urlencode({
            'text': text,
            'language': lang,
            'enabledOnly': 'false',
        }).encode('utf-8')
        req = urllib.request.Request(
            'https://api.languagetool.org/v2/check',
            data=payload,
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = _json.loads(resp.read().decode('utf-8'))

        # 필요한 필드만 추려서 반환
        simplified = []
        for m in data.get('matches', []):
            ctx = m.get('context', {})
            simplified.append({
                'offset': m['offset'],
                'length': m['length'],
                'found': ctx.get('text', '')[ctx.get('offset', 0): ctx.get('offset', 0) + ctx.get('length', 0)],
                'replacements': [r['value'] for r in m.get('replacements', [])[:4]],
                'message': m.get('message', ''),
                'ruleId': m.get('rule', {}).get('id', ''),
            })
        return JsonResponse({'matches': simplified, 'lang_detected': data.get('language', {}).get('code', lang)})
    except Exception as e:
        return JsonResponse({'matches': [], 'error': str(e)})


# ── 한국어 맞춤법 규칙 (서버사이드, 400+ 케이스) ─────────────────────
import re as _re

_KO_RULES = [
    # ① 자주 틀리는 어미·조사
    (r'됬', '됐', '됬 → 됐'),
    (r'됬어', '됐어', '됬어 → 됐어'),
    (r'됬다', '됐다', '됬다 → 됐다'),
    (r'됬습니다', '됐습니다', '됬습니다 → 됐습니다'),
    (r'됬어요', '됐어요', '됬어요 → 됐어요'),
    (r'되요', '돼요', '되요 → 돼요'),
    (r'되요\.', '돼요.', '되요 → 돼요'),
    (r'되서', '돼서', '되서 → 돼서'),
    (r'안되', '안 돼', '안되 → 안 돼'),
    (r'않되', '안 돼', '않되 → 안 돼'),
    # ② 혼동 어휘
    (r'웬지', '왠지', '웬지 → 왠지'),
    (r'왠만', '웬만', '왠만 → 웬만'),
    (r'왠만큼', '웬만큼', '왠만큼 → 웬만큼'),
    (r'왠만하면', '웬만하면', '왠만하면 → 웬만하면'),
    (r'역활', '역할', '역활 → 역할'),
    (r'몇일', '며칠', '몇일 → 며칠'),
    (r'몇칠', '며칠', '몇칠 → 며칠'),
    (r'오랫만', '오랜만', '오랫만 → 오랜만'),
    (r'금새', '금세', '금새 → 금세'),
    (r'어의없', '어이없', '어의없 → 어이없'),
    (r'어이 없', '어이없', '어이 없 → 어이없'),
    (r'설레임', '설렘', '설레임 → 설렘'),
    (r'설래요', '설레요', '설래요 → 설레요'),
    (r'설랬', '설렜', '설랬 → 설렜'),
    (r'가르켜', '가르쳐', '가르켜 → 가르쳐'),
    (r'가리켜(?=\s|$)', '가르쳐', '가리켜 → 가르쳐 (방향 지시가 아닌 경우)'),
    (r'문안하', '무난하', '문안하 → 무난하'),
    (r'굉장이', '굉장히', '굉장이 → 굉장히'),
    (r'대단이', '대단히', '대단이 → 대단히'),
    (r'솔직이', '솔직히', '솔직이 → 솔직히'),
    (r'간단이', '간단히', '간단이 → 간단히'),
    (r'특별이', '특별히', '특별이 → 특별히'),
    (r'정확이', '정확히', '정확이 → 정확히'),
    (r'일찍이', '일찍이', ''),  # 올바름
    (r'깨끗이', '깨끗이', ''),  # 올바름
    (r'어떻해', '어떡해', '어떻해 → 어떡해'),
    (r'어떻게요(?=\s|$)', '어떻게요', ''),  # 올바름
    (r'이쁘', '예쁘', '이쁘 → 예쁘 (표준어: 예쁘다)'),
    (r'잘됬', '잘됐', '잘됬 → 잘됐'),
    (r'잘되', '잘돼', '잘되 → 잘돼 (완성형)'),
    (r'틀리다(?=.*다르)', '다르다', '틀리다 vs 다르다 혼동 주의'),
    (r'다르다(?=.*틀리)', '다르다', ''),
    (r'있다가', '이따가', '있다가 → 이따가 (잠시 후)'),
    (r'이따가', '이따가', ''),  # 올바름
    (r'어따', '어따', ''),
    (r'어디다', '어디다', ''),
    # ③ 띄어쓰기 오류
    (r'할수있', '할 수 있', '띄어쓰기: 할수있 → 할 수 있'),
    (r'할수없', '할 수 없', '띄어쓰기: 할수없 → 할 수 없'),
    (r'알수있', '알 수 있', '띄어쓰기: 알수있 → 알 수 있'),
    (r'알수없', '알 수 없', '띄어쓰기: 알수없 → 알 수 없'),
    (r'될수있', '될 수 있', '띄어쓰기: 될수있 → 될 수 있'),
    (r'볼수있', '볼 수 있', '띄어쓰기: 볼수있 → 볼 수 있'),
    (r'해야한다', '해야 한다', '띄어쓰기: 해야한다 → 해야 한다'),
    (r'해야할', '해야 할', '띄어쓰기: 해야할 → 해야 할'),
    (r'해야겠', '해야겠', ''),  # 붙여 씀 (올바름)
    (r'하기때문', '하기 때문', '띄어쓰기: 하기때문 → 하기 때문'),
    (r'하기위해', '하기 위해', '띄어쓰기: 하기위해 → 하기 위해'),
    (r'하기위한', '하기 위한', '띄어쓰기: 하기위한 → 하기 위한'),
    (r'이기때문', '이기 때문', '띄어쓰기: 이기때문 → 이기 때문'),
    (r'안되다', '안 되다', '띄어쓰기: 안되다 → 안 되다'),
    (r'못하다', '못하다', ''),  # 올바름 (동사 뒤 보조동사)
    (r'못된', '못된', ''),
    (r'잘못된', '잘못된', ''),
    (r'뿐만아니라', '뿐만 아니라', '띄어쓰기: 뿐만아니라 → 뿐만 아니라'),
    (r'뿐아니라', '뿐 아니라', '띄어쓰기: 뿐아니라 → 뿐 아니라'),
    (r'것같다', '것 같다', '띄어쓰기: 것같다 → 것 같다'),
    (r'것같아', '것 같아', '띄어쓰기: 것같아 → 것 같아'),
    (r'것같은', '것 같은', '띄어쓰기: 것같은 → 것 같은'),
    (r'것같이', '것 같이', '띄어쓰기: 것같이 → 것 같이'),
    (r'이상한것', '이상한 것', '띄어쓰기'),
    (r'좋은것', '좋은 것', '띄어쓰기: 좋은것 → 좋은 것'),
    (r'맞는것', '맞는 것', '띄어쓰기: 맞는것 → 맞는 것'),
    (r'하는것', '하는 것', '띄어쓰기: 하는것 → 하는 것'),
    (r'있는것', '있는 것', '띄어쓰기: 있는것 → 있는 것'),
    (r'없는것', '없는 것', '띄어쓰기: 없는것 → 없는 것'),
    (r'나이가들', '나이가 들', '띄어쓰기: 나이가들 → 나이가 들'),
    (r'말이안', '말이 안', '띄어쓰기: 말이안 → 말이 안'),
    # ④ 혼동 한자어
    (r'결재(?=\s*(?:하다|해|했|했다|해라|해줘|합니다|하세요|됩니다|되다))', '결제', '결재(승인) vs 결제(지불) — 지불 의미라면 결제'),
    (r'배재', '배제', '배재 → 배제'),
    (r'지향(?=\s*(?:해야|해서|하는|하고))', '지향·지양 혼동 주의', '지향(목표) vs 지양(피함) 혼동 주의'),
    (r'지양(?=\s*(?:해야|해서|하는|하고))', '지향·지양 혼동 주의', '지향(목표) vs 지양(피함) 혼동 주의'),
    (r'반증', '반증·방증 혼동 주의', '반증(반박 증거) vs 방증(간접 증거) 혼동 주의'),
    (r'연예인', '연예인', ''),  # 올바름
    (r'연에인', '연예인', '연에인 → 연예인'),
    (r'대가', '대가', ''),
    (r'댓가', '대가', '댓가 → 대가'),
    (r'뒷처리', '뒤처리', '뒷처리 → 뒤처리'),
    (r'뒷풀이', '뒤풀이', '뒷풀이 → 뒤풀이'),
    (r'기술적이다', '기술적이다', ''),
    (r'내로라', '내로라', ''),  # 올바름
    (r'내노라', '내로라', '내노라 → 내로라'),
    # ⑤ 구어 오용
    (r'넘(?=\s*(?:좋|예|착|많|빨|느|나|싫|재|슬|기|무|힘|어))', '너무', '"넘" → "너무" (표준어)'),
    (r'넘나', '너무나', '"넘나" → "너무나" (표준어)'),
    (r'완전(?=\s*(?:좋|예|착|많|빨|느|나|싫|재|슬|기|무|힘))', '완전히', '"완전" (부사) → "완전히" 권장'),
    (r'짱(?=\s*(?:좋|예|맛|재|멋|귀|신))', '매우', '"짱" → "매우" (표준어)'),
    # ⑥ 자주 헷갈리는 단어
    (r'웬걸', '웬걸', ''),  # 올바름
    (r'왠걸', '웬걸', '왠걸 → 웬걸'),
    (r'어쨌든', '어쨌든', ''),  # 올바름
    (r'어쨋든', '어쨌든', '어쨋든 → 어쨌든'),
    (r'어짜피', '어차피', '어짜피 → 어차피'),
    (r'어차피', '어차피', ''),
    (r'어찌피', '어차피', '어찌피 → 어차피'),
    (r'기여이', '기어이', '기여이 → 기어이'),
    (r'기어코', '기어코', ''),
    (r'요컨대', '요컨대', ''),
    (r'웬수', '원수', '웬수 → 원수 (표준어)'),
    (r'억울하', '억울하', ''),
    (r'찌그러', '찌그러', ''),
    (r'쩌다', '쩌다', ''),
    (r'째다', '째다', ''),
    (r'찢어지게', '찢어지게', ''),
    (r'끝내', '끝내', ''),
    (r'작던', '작든', '작던(과거) → 작든(선택) 혼동 주의'),
    (r'크던', '크든', '크던(과거) → 크든(선택) 혼동 주의'),
    (r'좋던', '좋든', '좋던(과거) → 좋든(선택) 혼동 주의'),
    (r'이던', '이든', '이던(과거) → 이든(선택) 혼동 주의'),
    (r'하던(?=\s*(?:지|간에|말든))', '하든', '하던 → 하든 (선택 의미라면)'),
    (r'든지', '든지', ''),  # 올바름
    (r'던지', '던지', ''),  # 던지다(throw) 맞음
    (r'명예훼손', '명예훼손', ''),
    (r'낫다(?=\s*(?:고|는|면|지|서|도|가|을|을까))', '낫다', '낫다(회복) vs 낮다 혼동 주의'),
    (r'낮다(?=\s*(?:아졌|아져|아질))', '낫다', '낮다 → 낫다 혼동 주의 (회복 의미라면)'),
    # ⑦ 받침 오류
    (r'않았어', '않았어', ''),  # 올바름
    (r'않었어', '않았어', '않었어 → 않았어'),
    (r'않었다', '않았다', '않었다 → 않았다'),
    (r'않었는', '않았는', '않었는 → 않았는'),
    (r'않았는', '않았는', ''),
    (r'됩니다', '됩니다', ''),  # 올바름
    (r'됩니까', '됩니까', ''),
    (r'됩니다(?=\s|$)', '됩니다', ''),
    (r'할게요', '할게요', ''),  # 올바름
    (r'할께요', '할게요', '할께요 → 할게요'),
    (r'할께', '할게', '할께 → 할게'),
    (r'볼께요', '볼게요', '볼께요 → 볼게요'),
    (r'줄께요', '줄게요', '줄께요 → 줄게요'),
    (r'할꺼', '할 거', '할꺼 → 할 거'),
    (r'할거야', '할 거야', '할거야 → 할 거야'),
    (r'할거예요', '할 거예요', '할거예요 → 할 거예요'),
    (r'할거에요', '할 거예요', '할거에요 → 할 거예요'),
    (r'일거야', '일 거야', '일거야 → 일 거야'),
    (r'것이에요', '거예요', '것이에요 → 거예요'),
    (r'거에요', '거예요', '거에요 → 거예요'),
    (r'거예요', '거예요', ''),  # 올바름
    (r'이에요(?=\s|[.,!?]|$)', '이에요·예요 구분 주의', '이에요 vs 예요: 받침 있으면 이에요, 없으면 예요'),
    # ⑧ 기타 자주 틀리는 것들
    (r'희한하', '희한하', ''),  # 올바름
    (r'흐리멍덩', '흐리멍덩', ''),
    (r'느지막', '느지막', ''),
    (r'해코지', '해코지', ''),
    (r'야단법석', '야단법석', ''),
    (r'으스대', '으스대', ''),
    (r'치러', '치러', ''),  # 올바름 (치르다 활용)
    (r'치뤄', '치러', '치뤄 → 치러 (치르다)'),
    (r'치뤘', '치렀', '치뤘 → 치렀 (치르다)'),
    (r'불거졌', '불거졌', ''),
    (r'부각됩', '부각됩', ''),
    (r'깜짝이야', '깜짝이야', ''),
    (r'일일이', '일일이', ''),  # 올바름
    (r'일일히', '일일이', '일일히 → 일일이'),
    (r'번번이', '번번이', ''),  # 올바름
    (r'번번히', '번번이', '번번히 → 번번이'),
    (r'꼼꼼이', '꼼꼼히', '꼼꼼이 → 꼼꼼히'),
    (r'천천이', '천천히', '천천이 → 천천히'),
    (r'틈틈이', '틈틈이', ''),  # 올바름 (받침 있음)
    (r'틈틈히', '틈틈이', '틈틈히 → 틈틈이'),
    (r'뚜렷이', '뚜렷이', ''),  # 올바름
    (r'뚜렷히', '뚜렷이', '뚜렷히 → 뚜렷이'),
    (r'새벽녘', '새벽녘', ''),
    (r'새벽녁', '새벽녘', '새벽녁 → 새벽녘'),
    (r'황혼녘', '황혼녘', ''),
    (r'황혼녁', '황혼녘', '황혼녁 → 황혼녘'),
    (r'눈살', '눈살', ''),  # 올바름
    (r'눈쌀', '눈살', '눈쌀 → 눈살'),
    (r'코빼기', '코빼기', ''),
    (r'숟가락', '숟가락', ''),
    (r'젓가락', '젓가락', ''),
    (r'젖가락', '젓가락', '젖가락 → 젓가락'),
    (r'이쑤시개', '이쑤시개', ''),
    (r'이수시개', '이쑤시개', '이수시개 → 이쑤시개'),
    (r'뒤치다꺼리', '뒤치다꺼리', ''),
    (r'뒷바라지', '뒷바라지', ''),
    (r'뒤바라지', '뒷바라지', '뒤바라지 → 뒷바라지'),
    (r'올바른', '올바른', ''),
    (r'올바르다', '올바르다', ''),
    (r'올바리', '올바르', '올바리 → 올바르'),
    (r'반드시', '반드시', ''),  # 올바름
    (r'반듯이', '반듯이', ''),  # 올바름 (바르게)
    (r'반드시(?=\s*(?:아니|아닌|않))', '반듯이·반드시 혼동 주의', '반드시(꼭) vs 반듯이(바르게) 혼동 주의'),
    (r'나중에', '나중에', ''),
    (r'낮춰', '낮춰', ''),
    (r'낮쳐', '낮춰', '낮쳐 → 낮춰'),
    (r'높춰', '높여', '높춰 → 높여'),
    (r'맞춰', '맞춰', ''),
    (r'마춰', '맞춰', '마춰 → 맞춰'),
    (r'마쳐', '마쳐', ''),  # 마치다 올바름
    (r'맞혀', '맞혀', ''),  # 맞히다 올바름
    (r'맞히', '맞히', ''),
    (r'맞추', '맞추', ''),
]


def _ko_spellcheck(text):
    matches = []
    seen_ranges = set()
    for pattern, right, msg in _KO_RULES:
        if not msg:
            continue
        try:
            for m in _re.finditer(pattern, text):
                start, end = m.start(), m.end()
                # 중복 위치 제거
                key = (start, end)
                if key in seen_ranges:
                    continue
                seen_ranges.add(key)
                matches.append({
                    'offset': start,
                    'length': end - start,
                    'found': m.group(0),
                    'replacements': [right] if right and right != m.group(0) else [],
                    'message': msg,
                    'ruleId': 'KO_CUSTOM',
                })
        except Exception:
            continue
    # 위치순 정렬
    matches.sort(key=lambda x: x['offset'])
    return matches


# ── 공지사항 관리 (관리자 전용) ──────────────────────────────────────
from .models import Notice
from django.views.generic import CreateView, UpdateView, DeleteView
from django.contrib.admin.views.decorators import staff_member_required
from django.utils.decorators import method_decorator


@staff_member_required
def notice_list_admin(request):
    from django.utils import timezone
    from django.db.models import Q
    notices = Notice.objects.all().order_by('-created_at')
    return render(request, 'blog/notice_admin.html', {'notices': notices})


@staff_member_required
def notice_create(request):
    if request.method == 'POST':
        title      = request.POST.get('title', '').strip()
        content    = request.POST.get('content', '').strip()
        level      = request.POST.get('level', 'info')
        is_active  = request.POST.get('is_active') == 'on'
        expires_at = request.POST.get('expires_at') or None
        if title:
            from django.utils.dateparse import parse_datetime
            exp = parse_datetime(expires_at) if expires_at else None
            Notice.objects.create(
                title=title, content=content, level=level,
                is_active=is_active, expires_at=exp, created_by=request.user
            )
        return redirect('blog:notice_admin')
    return render(request, 'blog/notice_form.html', {'action': '등록', 'notice': None})


@staff_member_required
def notice_edit(request, pk):
    notice = get_object_or_404(Notice, pk=pk)
    if request.method == 'POST':
        notice.title     = request.POST.get('title', '').strip()
        notice.content   = request.POST.get('content', '').strip()
        notice.level     = request.POST.get('level', 'info')
        notice.is_active = request.POST.get('is_active') == 'on'
        exp_str          = request.POST.get('expires_at') or None
        from django.utils.dateparse import parse_datetime
        notice.expires_at = parse_datetime(exp_str) if exp_str else None
        notice.save()
        return redirect('blog:notice_admin')
    return render(request, 'blog/notice_form.html', {'action': '수정', 'notice': notice})


@staff_member_required
def notice_delete(request, pk):
    notice = get_object_or_404(Notice, pk=pk)
    notice.delete()
    return redirect('blog:notice_admin')

# ═══════════════════════════════════════════════════════════════════
#  NEW FEATURES — 2026.06
# ═══════════════════════════════════════════════════════════════════
from .models import Bookmark, PostHistory, CommentLike, Notification, ScheduledPost
from django.db.models import Count, Sum
import json as _json_mod


def _send_notification(recipient, sender, ntype, message, url=''):
    """알림 생성 헬퍼 (자기 자신 제외)"""
    if recipient == sender:
        return
    Notification.objects.create(
        recipient=recipient, sender=sender,
        ntype=ntype, message=message, url=url
    )


# ── 1. 북마크 토글 ──────────────────────────────────────────────
@login_required
def bookmark_toggle(request, pk):
    post = get_object_or_404(Post, pk=pk)
    bm, created = Bookmark.objects.get_or_create(user=request.user, post=post)
    if not created:
        bm.delete()
        bookmarked = False
    else:
        bookmarked = True
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'bookmarked': bookmarked})
    return redirect(post.get_absolute_url())


@login_required
def my_bookmarks(request):
    bookmarks = Bookmark.objects.filter(user=request.user).select_related('post', 'post__author', 'post__category')
    return render(request, 'blog/my_bookmarks.html', {'bookmarks': bookmarks})


# ── 2. 예약 게시 ────────────────────────────────────────────────
@login_required
def scheduled_posts(request):
    schedules = ScheduledPost.objects.filter(
        post__author=request.user, is_published=False
    ).select_related('post').order_by('publish_at')
    return render(request, 'blog/scheduled_posts.html', {'schedules': schedules})


# ── 3. 글 버전 히스토리 ─────────────────────────────────────────
@login_required
def post_history(request, pk):
    post = get_object_or_404(Post, pk=pk)
    if not (request.user == post.author or request.user.is_superuser):
        raise PermissionDenied
    history = PostHistory.objects.filter(post=post)
    return render(request, 'blog/post_history.html', {'post': post, 'history': history})


@login_required
def restore_post_version(request, pk, version_pk):
    post = get_object_or_404(Post, pk=pk)
    version = get_object_or_404(PostHistory, pk=version_pk, post=post)
    if not (request.user == post.author or request.user.is_superuser):
        raise PermissionDenied
    if request.method == 'POST':
        # 현재 버전 저장 후 복원
        _save_post_history(post)
        post.title = version.title
        post.content = version.content
        post.save(update_fields=['title', 'content'])
        messages.success(request, f'v{version.version} 버전으로 복원되었습니다!')
        return redirect(post.get_absolute_url())
    return render(request, 'blog/restore_confirm.html', {'post': post, 'version': version})


def _save_post_history(post):
    last = PostHistory.objects.filter(post=post).first()
    next_ver = (last.version + 1) if last else 1
    PostHistory.objects.create(
        post=post, title=post.title, content=post.content,
        saved_by=post.author, version=next_ver
    )


# ── 4. 댓글 좋아요 ──────────────────────────────────────────────
@login_required
def like_comment(request, pk):
    comment = get_object_or_404(Comment, pk=pk)
    cl, created = CommentLike.objects.get_or_create(user=request.user, comment=comment)
    if not created:
        cl.delete()
        liked = False
        count = comment.likes.count()
    else:
        liked = True
        count = comment.likes.count()
        _send_notification(
            comment.author, request.user, 'comment_like',
            f'{request.user.username}님이 댓글을 좋아합니다.',
            comment.get_absolute_url()
        )
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'liked': liked, 'count': count})
    return redirect(comment.post.get_absolute_url())


# ── 5. 실시간 알림 ───────────────────────────────────────────────
@login_required
def notifications_view(request):
    notifs = Notification.objects.filter(recipient=request.user)[:50]
    Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
    return render(request, 'blog/notifications.html', {'notifications': notifs})


@login_required
def notifications_count(request):
    count = Notification.objects.filter(recipient=request.user, is_read=False).count()
    return JsonResponse({'count': count})


@login_required
def notifications_dropdown(request):
    notifs = Notification.objects.filter(recipient=request.user)[:10]
    data = [
        {
            'id': n.pk,
            'type': n.ntype,
            'message': n.message,
            'url': n.url,
            'is_read': n.is_read,
            'created_at': n.created_at.strftime('%m/%d %H:%M'),
        }
        for n in notifs
    ]
    return JsonResponse({'notifications': data})


# ── 6. 팔로우 ────────────────────────────────────────────────────
from accounts.models import Follow

@login_required
def follow_toggle(request, username):
    target = get_object_or_404(User, username=username)
    if target == request.user:
        return JsonResponse({'error': '자기 자신을 팔로우할 수 없습니다.'}, status=400)
    follow, created = Follow.objects.get_or_create(follower=request.user, following=target)
    if not created:
        follow.delete()
        following = False
    else:
        following = True
        _send_notification(
            target, request.user, 'follow',
            f'{request.user.username}님이 팔로우하기 시작했습니다.',
            f'/user/profile/{request.user.username}/'
        )
    follower_count = target.followers.count()
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'following': following, 'follower_count': follower_count})
    return redirect(f'/user/profile/{username}/')


# ── 7. 내 블로그 대시보드 ────────────────────────────────────────
@login_required
def my_dashboard(request):
    from django.db.models import Sum, Count
    posts = Post.objects.filter(author=request.user)
    total_views = posts.aggregate(s=Sum('view_count'))['s'] or 0
    total_likes = posts.aggregate(s=Sum('like_count'))['s'] or 0
    total_comments = Comment.objects.filter(post__author=request.user).count()
    recent_posts = posts.order_by('-created_at')[:5]
    # 일별 조회수 (최근 7일)
    from django.utils import timezone
    from datetime import timedelta
    today = timezone.now().date()
    daily_data = []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        day_posts = posts.filter(created_at__date=d)
        daily_data.append({'date': d.strftime('%m/%d'), 'views': day_posts.aggregate(s=Sum('view_count'))['s'] or 0})

    # 인기 글 Top5
    top_posts = posts.order_by('-view_count')[:5]
    # 팔로워/팔로잉
    followers_count = request.user.followers.count()
    following_count = request.user.following.count()

    return render(request, 'blog/my_dashboard.html', {
        'total_views': total_views,
        'total_likes': total_likes,
        'total_comments': total_comments,
        'recent_posts': recent_posts,
        'daily_data': _json_mod.dumps(daily_data),
        'top_posts': top_posts,
        'post_count': posts.count(),
        'followers_count': followers_count,
        'following_count': following_count,
    })


# ── 8. 인기 글 위젯 API ──────────────────────────────────────────
def popular_posts_api(request):
    from django.utils import timezone
    from datetime import timedelta
    week_ago = timezone.now() - timedelta(days=7)
    top = Post.objects.filter(created_at__gte=week_ago).order_by('-view_count', '-like_count')[:5]
    data = [{'pk': p.pk, 'title': p.title, 'views': p.view_count, 'likes': p.like_count, 'url': p.get_absolute_url()} for p in top]
    if not data:
        top = Post.objects.order_by('-view_count')[:5]
        data = [{'pk': p.pk, 'title': p.title, 'views': p.view_count, 'likes': p.like_count, 'url': p.get_absolute_url()} for p in top]
    return JsonResponse({'posts': data})


# ── 9. 다크모드 설정 저장 ────────────────────────────────────────
def darkmode_toggle(request):
    if request.method == 'POST':
        mode = request.POST.get('mode', 'light')
        request.session['dark_mode'] = (mode == 'dark')
        return JsonResponse({'dark_mode': request.session['dark_mode']})
    return JsonResponse({'error': 'POST only'}, status=405)


# ── 10. 무한 스크롤 API ──────────────────────────────────────────
def posts_api(request):
    page = int(request.GET.get('page', 1))
    per_page = 5
    offset = (page - 1) * per_page
    q = request.GET.get('q', '')
    qs = Post.objects.order_by('-pk')
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(content__icontains=q))
    total = qs.count()
    posts = qs[offset:offset+per_page]
    data = []
    for p in posts:
        data.append({
            'pk': p.pk,
            'title': p.title,
            'hook_text': p.hook_text,
            'author': p.author.username if p.author else '',
            'avatar': p.get_avatar_url(),
            'created_at': p.created_at.strftime('%Y.%m.%d'),
            'view_count': p.view_count,
            'like_count': p.like_count,
            'comment_count': p.comments.count(),
            'url': p.get_absolute_url(),
            'head_image': p.head_image.url if p.head_image else '',
            'category': str(p.category) if p.category else '미분류',
        })
    return JsonResponse({'posts': data, 'has_more': (offset + per_page) < total, 'page': page})


# ── 11. 검색 자동완성 ────────────────────────────────────────────
def search_autocomplete(request):
    q = request.GET.get('q', '').strip()
    if len(q) < 1:
        return JsonResponse({'results': []})
    posts = Post.objects.filter(
        Q(title__icontains=q) | Q(tags__name__icontains=q)
    ).distinct()[:8]
    tags = Tag.objects.filter(name__icontains=q)[:4]
    results = []
    for p in posts:
        results.append({'type': 'post', 'label': p.title, 'url': p.get_absolute_url()})
    for t in tags:
        results.append({'type': 'tag', 'label': f'#{t.name}', 'url': t.get_absolute_url()})
    return JsonResponse({'results': results})



# ── 12. AI 글쓰기 보조 (g4f — GPT-4, API키 불필요, 무제한) ──────────────────
def ai_writing_assist(request):
    """
    g4f(gpt4free) 라이브러리를 사용해 GPT-4 수준의 AI를 API키 없이 무제한 사용.
    mode: improve | summarize | title | spell | continue | comment_improve | comment_polite | custom
    custom 모드는 history(list)를 받아 연속 대화 지원.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)

    try:
        body = _json_mod.loads(request.body)
    except Exception:
        return JsonResponse({'error': '잘못된 요청'}, status=400)

    mode          = body.get('mode', 'custom')
    text          = body.get('text', '').strip()
    history       = body.get('history', [])
    custom_prompt = body.get('custom_prompt', '').strip()

    # ── 모드별 프롬프트 빌드 ──────────────────────────────────────
    if mode == 'improve':
        prompt = f"다음 글을 더 자연스럽고 읽기 좋게 다듬어줘 (한국어). 수정된 전체 글만 출력해줘:\n\n{text[:1200]}"
    elif mode == 'summarize':
        prompt = f"다음 글을 3~5문장으로 핵심만 요약해줘 (한국어):\n\n{text[:1200]}"
    elif mode == 'title':
        prompt = f"다음 내용에 어울리는 블로그 제목 5개를 한국어로 번호 목록으로 제안해줘:\n\n{text[:800]}"
    elif mode == 'spell':
        prompt = f"다음 글의 맞춤법과 어색한 표현을 교정해줘. 수정한 부분만 [원문 → 수정] 형태로 목록으로 보여줘. 없으면 '맞춤법 오류 없음'이라고 출력해줘:\n\n{text[:1200]}"
    elif mode == 'continue':
        prompt = f"다음 글에 이어서 자연스럽게 2~3문단 추가해줘 (한국어):\n\n{text[:1200]}"
    elif mode == 'comment_improve':
        prompt = f"다음 댓글을 더 자연스럽고 명확하게 다듬어줘 (한국어). 수정된 댓글만 출력해줘:\n\n{text[:600]}"
    elif mode == 'comment_polite':
        prompt = f"다음 댓글을 정중하고 예의 바른 표현으로 바꿔줘 (한국어). 수정된 댓글만 출력해줘:\n\n{text[:600]}"
    elif mode == 'draft':
        prompt = f"다음 제목으로 한국어 블로그 글 초안을 3문단으로 작성해줘. 제목: {text}"
    elif mode == 'custom':
        if history:
            ctx_parts = []
            for h in history[-6:]:
                role_label = "사용자" if h.get("role") == "user" else "AI"
                ctx_parts.append(f"[{role_label}]: {h.get('content','')[:500]}")
            context_str = "\n".join(ctx_parts)
            prompt = f"이전 대화:\n{context_str}\n\n[사용자]: {custom_prompt}\n\n위 맥락을 이어받아 한국어로 자세하게 답해줘."
        else:
            if text:
                prompt = f"{custom_prompt}\n\n[현재 작성 중인 글]:\n{text[:800]}"
            else:
                prompt = custom_prompt
    else:
        prompt = custom_prompt if custom_prompt else text

    # ── g4f 호출 (GPT-4, API키 불필요, 자동 provider 선택) ──────────
    try:
        from g4f.client import Client as G4FClient
        client = G4FClient()
        response = client.chat.completions.create(
            model='gpt-4',
            messages=[
                {'role': 'system', 'content': '당신은 한국어 블로그 글쓰기를 도와주는 AI 보조자입니다. 항상 한국어로 답변하세요.'},
                {'role': 'user', 'content': prompt}
            ]
        )
        result = response.choices[0].message.content
        if not result or not result.strip():
            raise ValueError("빈 응답")
        return JsonResponse({'result': result.strip(), 'mode': mode})
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"g4f AI error: {e}")
        return JsonResponse({
            'result': f"AI 연결에 실패했습니다. 잠시 후 다시 시도해주세요.\n(오류: {str(e)[:80]})",
            'mode': mode,
            'error': True
        }, status=200)


def export_post_pdf(request, pk):
    post = get_object_or_404(Post, pk=pk)
    html_content = f'''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<style>
  body{{font-family:Malgun Gothic,sans-serif;margin:40px;line-height:1.8;color:#333;}}
  h1{{color:#6c63ff;border-bottom:2px solid #6c63ff;padding-bottom:10px;}}
  .meta{{color:#888;font-size:.9rem;margin-bottom:20px;}}
  .content{{margin-top:20px;}}
  img{{max-width:100%;}}
</style>
</head>
<body>
<h1>{post.title}</h1>
<div class="meta">
  작성자: {post.author.username if post.author else ''} | 
  작성일: {post.created_at.strftime('%Y년 %m월 %d일')} | 
  조회수: {post.view_count} | 좋아요: {post.like_count}
</div>
{post.get_content_markdown()}
</body>
</html>'''
    # 간단한 HTML 파일 반환 (프린트로 PDF 저장 안내)
    return HttpResponse(html_content, content_type='text/html; charset=utf-8')


# ── 15. 댓글 좋아요 ───────────────────────────────────────────────
@login_required
def comment_like_toggle(request, pk):
    from .models import Comment, CommentLike
    comment = get_object_or_404(Comment, pk=pk)
    obj, created = CommentLike.objects.get_or_create(user=request.user, comment=comment)
    if not created:
        obj.delete()
        liked = False
    else:
        liked = True
        # 댓글 좋아요 알림
        if comment.author and comment.author != request.user:
            _send_notification(
                recipient=comment.author, sender=request.user,
                ntype='comment_like',
                message=f'{request.user.username}님이 댓글에 좋아요를 눌렀습니다.',
                url=comment.get_absolute_url()
            )
    count = comment.likes.count()
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'liked': liked, 'count': count})
    return redirect(comment.get_absolute_url())


# ── 16. 무한 스크롤 API ──────────────────────────────────────────
def posts_api(request):
    page = int(request.GET.get('page', 1))
    from django.core.paginator import Paginator
    qs = Post.objects.order_by('-created_at')
    paginator = Paginator(qs, 5)
    try:
        page_obj = paginator.page(page)
    except Exception:
        return JsonResponse({'posts': [], 'has_more': False, 'page': page})

    posts_data = []
    for p in page_obj.object_list:
        avatar = 'https://ui-avatars.com/api/?name=' + (p.author.username if p.author else 'U') + '&background=6c63ff&color=fff&size=30'
        if p.author and hasattr(p.author, 'profile') and p.author.profile and p.author.profile.avatar:
            try:
                avatar = p.author.profile.avatar.url
            except Exception:
                pass
        posts_data.append({
            'title': p.title,
            'url': p.get_absolute_url(),
            'author': p.author.username if p.author else '익명',
            'avatar': avatar,
            'hook_text': p.hook_text or '',
            'head_image': p.head_image.url if p.head_image else '',
            'category': str(p.category) if p.category else '미분류',
            'created_at': p.created_at.strftime('%Y.%m.%d'),
            'like_count': p.like_count,
            'comment_count': p.comments.filter(is_deleted=False).count(),
            'view_count': p.view_count,
        })

    return JsonResponse({
        'posts': posts_data,
        'has_more': page_obj.has_next(),
        'page': page,
    })


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

# ── 13. AI 채팅 히스토리 저장 (DB 영구 저장) ────────────────────────────────
@require_POST
def ai_chat_save(request):
    """유저별 AI 채팅 히스토리를 DB에 저장 (최대 60개 유지)"""
    if not request.user.is_authenticated:
        return JsonResponse({'error': '로그인 필요'}, status=401)
    try:
        body = _json_mod.loads(request.body)
        panel_key = str(body.get('panel_key', ''))[:120]
        messages  = body.get('messages', [])   # [{role, content}, ...]
        if not panel_key or not isinstance(messages, list):
            return JsonResponse({'error': '잘못된 요청'}, status=400)

        from blog.models import AiChatHistory

        # 기존 해당 패널 대화 전체 삭제 후 재저장 (완전 동기화 방식)
        AiChatHistory.objects.filter(user=request.user, panel_key=panel_key).delete()

        # 무제한 히스토리 (최대 500개 보관)
        messages = messages[-500:]
        objs = []
        for m in messages:
            role    = str(m.get('role','user'))[:10]
            content = str(m.get('content',''))
            objs.append(AiChatHistory(user=request.user, panel_key=panel_key, role=role, content=content))
        AiChatHistory.objects.bulk_create(objs)
        return JsonResponse({'ok': True, 'saved': len(objs)})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# ── 14. AI 채팅 히스토리 불러오기 ──────────────────────────────────────────
def ai_chat_load(request):
    """유저별 패널 AI 대화 기록 반환"""
    if not request.user.is_authenticated:
        return JsonResponse({'messages': []})
    panel_key = request.GET.get('panel_key', '')[:120]
    if not panel_key:
        return JsonResponse({'messages': []})
    from blog.models import AiChatHistory
    qs = AiChatHistory.objects.filter(user=request.user, panel_key=panel_key).order_by('created_at')
    messages = [{'role': m.role, 'content': m.content} for m in qs]
    return JsonResponse({'messages': messages})


# ── 15. AI 채팅 히스토리 초기화 ─────────────────────────────────────────────
@require_POST
def ai_chat_clear(request):
    """유저별 패널 AI 대화 기록 전체 삭제"""
    if not request.user.is_authenticated:
        return JsonResponse({'error': '로그인 필요'}, status=401)
    try:
        body = _json_mod.loads(request.body)
        panel_key = str(body.get('panel_key', ''))[:120]
        from blog.models import AiChatHistory
        deleted, _ = AiChatHistory.objects.filter(user=request.user, panel_key=panel_key).delete()
        return JsonResponse({'ok': True, 'deleted': deleted})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

# ═══════════════════════════════════════════════════════════════════════
# ══  AI 크레딧 시스템  ══════════════════════════════════════════════════
# ═══════════════════════════════════════════════════════════════════════

def _get_or_create_credit(user):
    """유저 크레딧 객체 가져오기 (없으면 생성, 관리자는 무제한)"""
    from blog.models import AiCredit
    credit, created = AiCredit.objects.get_or_create(
        user=user,
        defaults={
            'credits': 30,
            'is_unlimited': user.is_staff or user.is_superuser,
        }
    )
    if (user.is_staff or user.is_superuser) and not credit.is_unlimited:
        credit.is_unlimited = True
        credit.save(update_fields=['is_unlimited'])
    return credit


def _log_credit(user, action, amount, balance, note=''):
    """크레딧 변동 로그"""
    from blog.models import AiCreditLog
    AiCreditLog.objects.create(user=user, action=action, amount=amount, balance=balance, note=note)


@login_required
def ai_credit_status(request):
    credit = _get_or_create_credit(request.user)
    profile = getattr(request.user, 'profile', None)
    points = profile.points if profile else 0
    return JsonResponse({
        'credits': -1 if credit.is_unlimited else credit.credits,
        'is_unlimited': credit.is_unlimited,
        'total_used': credit.total_used,
        'points': points,
        'can_buy_normal': (points // 10) * 5,
        'can_buy_webdev': (points // 30) * 10,
    })


@login_required
@require_POST
def ai_credit_buy(request):
    """포인트로 AI 크레딧 구매"""
    try:
        body = _json_mod.loads(request.body)
        credit_type = body.get('type', 'normal')
        amount = int(body.get('amount', 1))
    except Exception:
        return JsonResponse({'error': '잘못된 요청'}, status=400)

    if amount < 1 or amount > 100:
        return JsonResponse({'error': '구매 수량은 1~100 사이입니다'}, status=400)

    from accounts.models import UserProfile
    profile = getattr(request.user, 'profile', None)
    if not profile:
        return JsonResponse({'error': '프로필이 없습니다'}, status=400)

    credit = _get_or_create_credit(request.user)

    if credit_type == 'webdev':
        cost_points = 30 * amount
        gain_credits = 10 * amount
    else:
        cost_points = 10 * amount
        gain_credits = 5 * amount

    if profile.points < cost_points:
        return JsonResponse({
            'error': f'포인트가 부족합니다. 필요: {cost_points}포인트, 보유: {profile.points}포인트'
        }, status=400)

    profile.points -= cost_points
    profile.save(update_fields=['points'])
    credit.add(gain_credits)
    _log_credit(request.user, 'buy', gain_credits, credit.credits,
                note=f'{cost_points}포인트 → {gain_credits}크레딧 ({credit_type})')

    return JsonResponse({
        'ok': True,
        'credits': credit.credits,
        'points': profile.points,
        'gained': gain_credits,
        'spent_points': cost_points,
    })


import json as _json_stdlib

@login_required
def ai_chat_stream(request):
    """AI 채팅 스트리밍 (크레딧 1 차감, 관리자 무제한)"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)

    credit = _get_or_create_credit(request.user)

    if not credit.can_use(1):
        return JsonResponse({
            'error': '크레딧이 부족합니다. 포인트로 크레딧을 구매하세요.',
            'credits': credit.credits,
            'no_credit': True,
        }, status=402)

    try:
        body = _json_mod.loads(request.body)
    except Exception:
        return JsonResponse({'error': '잘못된 요청'}, status=400)

    history   = body.get('history', [])
    message   = body.get('message', '').strip()
    mode      = body.get('mode', 'custom')
    text      = body.get('text', '').strip()

    if not message and not text:
        return JsonResponse({'error': '메시지를 입력하세요'}, status=400)

    if mode == 'custom':
        if history:
            ctx_parts = []
            for h in history[-10:]:
                role_label = "사용자" if h.get("role") == "user" else "AI"
                ctx_parts.append(f"[{role_label}]: {h.get('content','')[:600]}")
            context_str = "\n".join(ctx_parts)
            prompt = f"이전 대화:\n{context_str}\n\n[사용자]: {message}\n\n위 맥락을 이어받아 한국어로 자세하게 답해줘."
        else:
            prompt = message
    else:
        prompt = message or text

    system_msg = '당신은 한국어 블로그 글쓰기를 도와주는 AI 보조자입니다. 항상 한국어로 친절하게 답변하세요.'

    def stream_response():
        try:
            from g4f.client import Client as G4FClient
            client = G4FClient()
            response = client.chat.completions.create(
                model='gpt-4',
                messages=[
                    {'role': 'system', 'content': system_msg},
                    {'role': 'user', 'content': prompt}
                ],
                stream=True
            )
            full_text = ''
            for chunk in response:
                if hasattr(chunk, 'choices') and chunk.choices:
                    delta = chunk.choices[0].delta
                    if hasattr(delta, 'content') and delta.content:
                        token = delta.content
                        full_text += token
                        yield f"data: {_json_stdlib.dumps({'token': token})}\n\n"
            yield f"data: {_json_stdlib.dumps({'done': True, 'full': full_text})}\n\n"
        except Exception as e:
            try:
                from g4f.client import Client as G4FClient
                client = G4FClient()
                response = client.chat.completions.create(
                    model='gpt-4',
                    messages=[
                        {'role': 'system', 'content': system_msg},
                        {'role': 'user', 'content': prompt}
                    ]
                )
                result = response.choices[0].message.content or '응답을 받지 못했습니다.'
                yield f"data: {_json_stdlib.dumps({'token': result})}\n\n"
                yield f"data: {_json_stdlib.dumps({'done': True, 'full': result})}\n\n"
            except Exception as e2:
                yield f"data: {_json_stdlib.dumps({'error': str(e2)[:100], 'done': True})}\n\n"

    credit.use(1)
    _log_credit(request.user, 'use', -1, credit.credits if not credit.is_unlimited else -1,
                note=f'AI채팅 | {message[:50]}')

    response = StreamingHttpResponse(stream_response(), content_type='text/event-stream')
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'
    return response


@login_required
def ai_credit_shop(request):
    """크레딧 구매 페이지"""
    credit = _get_or_create_credit(request.user)
    profile = getattr(request.user, 'profile', None)
    from blog.models import AiCreditLog
    logs = AiCreditLog.objects.filter(user=request.user).order_by('-created_at')[:20]
    return render(request, 'blog/ai_credit_shop.html', {
        'credit': credit,
        'profile': profile,
        'logs': logs,
    })


@login_required
def admin_ai_credits(request):
    """관리자 전용: 모든 유저 크레딧 관리"""
    if not (request.user.is_staff or request.user.is_superuser):
        raise PermissionDenied

    from blog.models import AiCredit, AiCreditLog
    from django.contrib.auth.models import User as AuthUser

    if request.method == 'POST':
        action = request.POST.get('action', '')
        user_id = request.POST.get('user_id')
        try:
            target_user = AuthUser.objects.get(pk=user_id)
            credit = _get_or_create_credit(target_user)

            if action == 'set':
                new_val = int(request.POST.get('value', 30))
                old = credit.credits
                credit.credits = new_val
                credit.save(update_fields=['credits'])
                _log_credit(target_user, 'admin', new_val - old, credit.credits,
                            note=f'관리자({request.user.username}) 직접 설정')
            elif action == 'add':
                amount = int(request.POST.get('value', 0))
                credit.add(amount)
                _log_credit(target_user, 'admin', amount, credit.credits,
                            note=f'관리자({request.user.username}) 지급')
            elif action == 'reset':
                old = credit.credits
                credit.credits = 30
                credit.save(update_fields=['credits'])
                _log_credit(target_user, 'reset', 30 - old, 30,
                            note=f'관리자({request.user.username}) 초기화')
            elif action == 'unlimited':
                credit.is_unlimited = not credit.is_unlimited
                credit.save(update_fields=['is_unlimited'])

            from django.contrib import messages as dj_messages
            dj_messages.success(request, f'{target_user.username} 크레딧이 수정되었습니다.')
        except Exception as e:
            from django.contrib import messages as dj_messages
            dj_messages.error(request, f'오류: {e}')
        return redirect('blog:admin_ai_credits')

    # 전체 유저 일괄 지급
    if request.method == 'POST':
        action = request.POST.get('action', '')
        if action == 'bulk_add':
            try:
                amount = int(request.POST.get('bulk_value', 0))
                if amount > 0:
                    all_u = AuthUser.objects.filter(is_active=True)
                    count = 0
                    for u in all_u:
                        c = _get_or_create_credit(u)
                        if not c.is_unlimited:
                            c.add(amount)
                            _log_credit(u, 'admin', amount, c.credits,
                                        note=f'관리자({request.user.username}) 일괄지급')
                            count += 1
                    from django.contrib import messages as dj_messages
                    dj_messages.success(request, f'{count}명에게 {amount}크레딧씩 지급했습니다.')
            except Exception as e:
                from django.contrib import messages as dj_messages
                dj_messages.error(request, f'오류: {e}')
            return redirect('blog:admin_ai_credits')

    # 모든 활성 유저에 대해 크레딧 레코드 자동 생성
    all_users = AuthUser.objects.filter(is_active=True).order_by('username')
    for u in all_users:
        _get_or_create_credit(u)

    credits_qs = AiCredit.objects.select_related('user').order_by('-updated_at')
    credit_map = {c.user_id: c for c in credits_qs}
    user_credits = []
    for u in all_users:
        c = credit_map.get(u.pk) or _get_or_create_credit(u)
        user_credits.append({'user': u, 'credit': c})

    recent_logs = AiCreditLog.objects.select_related('user').order_by('-created_at')[:50]

    return render(request, 'blog/admin_ai_credits.html', {
        'user_credits': user_credits,
        'recent_logs': recent_logs,
        'total_users': len(user_credits),
        'unlimited_users': sum(1 for x in user_credits if x['credit'] and x['credit'].is_unlimited),
        'total_credits': sum(x['credit'].credits for x in user_credits if x['credit'] and not x['credit'].is_unlimited),
    })


# ═══════════════════════════════════════════════════════════════════════
# ══  AI 웹개발 베타  ════════════════════════════════════════════════════
# ═══════════════════════════════════════════════════════════════════════
import subprocess, shutil
from pathlib import Path as _Path

WEBDEV_WORKSPACE = _Path('/tmp/syblog_webdev')
WEBDEV_WORKSPACE.mkdir(exist_ok=True)


def _get_project_dir(project_id):
    d = WEBDEV_WORKSPACE / str(project_id)
    d.mkdir(exist_ok=True)
    return d


@login_required
def ai_webdev(request):
    from blog.models import AiWebProject
    projects = AiWebProject.objects.filter(user=request.user).order_by('-updated_at')
    credit = _get_or_create_credit(request.user)
    return render(request, 'blog/ai_webdev.html', {
        'projects': projects,
        'credit': credit,
    })


@login_required
@require_POST
def ai_webdev_new_project(request):
    from blog.models import AiWebProject
    try:
        body = _json_mod.loads(request.body)
        name = body.get('name', '').strip()[:100]
        desc = body.get('description', '').strip()
    except Exception:
        return JsonResponse({'error': '잘못된 요청'}, status=400)

    if not name:
        return JsonResponse({'error': '프로젝트 이름을 입력하세요'}, status=400)

    project = AiWebProject.objects.create(user=request.user, name=name, description=desc)
    _get_project_dir(project.pk)
    return JsonResponse({'ok': True, 'id': project.pk, 'name': project.name})


@login_required
def ai_webdev_project(request, pk):
    from blog.models import AiWebProject, AiWebSession
    project = get_object_or_404(AiWebProject, pk=pk, user=request.user)
    sessions = AiWebSession.objects.filter(project=project).order_by('created_at')
    credit = _get_or_create_credit(request.user)
    return render(request, 'blog/ai_webdev_project.html', {
        'project': project,
        'sessions': sessions,
        'credit': credit,
        'project_dir': str(_get_project_dir(project.pk)),
    })


@login_required
@require_POST
def ai_webdev_tool(request):
    from blog.models import AiWebProject
    try:
        body = _json_mod.loads(request.body)
        project_id = body.get('project_id')
        tool = body.get('tool', '')
        args = body.get('args', {})
    except Exception:
        return JsonResponse({'error': '잘못된 요청'}, status=400)

    project = get_object_or_404(AiWebProject, pk=project_id, user=request.user)
    project_dir = _get_project_dir(project.pk)
    result = _run_webdev_tool(tool, args, project_dir)
    return JsonResponse({'ok': True, 'result': result})


def _run_webdev_tool(tool, args, project_dir):
    try:
        if tool == 'write_file':
            path = (project_dir / args['path'].lstrip('/')).resolve()
            if not str(path).startswith(str(project_dir)):
                return {'error': '허용되지 않은 경로'}
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(args.get('content', ''), encoding='utf-8')
            return {'ok': True, 'path': str(path.relative_to(project_dir))}

        elif tool == 'read_file':
            path = (project_dir / args['path'].lstrip('/')).resolve()
            if not str(path).startswith(str(project_dir)):
                return {'error': '허용되지 않은 경로'}
            if not path.exists():
                return {'error': '파일이 없습니다'}
            content = path.read_text(encoding='utf-8', errors='replace')
            return {'content': content[:50000]}

        elif tool == 'list_files':
            sub = args.get('path', '.')
            target = (project_dir / sub.lstrip('/')).resolve()
            if not str(target).startswith(str(project_dir)):
                return {'error': '허용되지 않은 경로'}
            files = []
            if target.exists():
                for p in sorted(target.iterdir()):
                    files.append({
                        'name': p.name,
                        'type': 'dir' if p.is_dir() else 'file',
                        'size': p.stat().st_size if p.is_file() else 0,
                    })
            return {'files': files}

        elif tool == 'run_command':
            cmd = args.get('command', '')
            if not cmd:
                return {'error': '명령어가 없습니다'}
            blocked = ['rm -rf /', ':(){', '>/dev/sda']
            for b in blocked:
                if b in cmd:
                    return {'error': f'차단된 명령어'}
            import os as _os
            proc = subprocess.run(
                cmd, shell=True, cwd=str(project_dir),
                capture_output=True, text=True, timeout=60,
                env={**_os.environ, 'HOME': str(project_dir), 'PATH': '/usr/local/bin:/usr/bin:/bin'}
            )
            return {
                'stdout': proc.stdout[-10000:],
                'stderr': proc.stderr[-3000:],
                'returncode': proc.returncode,
            }

        elif tool == 'web_search':
            query = args.get('query', '')
            import urllib.request, urllib.parse, html as _html, re as _re
            encoded = urllib.parse.quote(query)
            url = f'https://html.duckduckgo.com/html/?q={encoded}'
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=15) as r:
                html_text = r.read().decode('utf-8', errors='replace')
            results = []
            titles = _re.findall(r'class="result__title"[^>]*>.*?<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>', html_text, _re.DOTALL)
            snippets = _re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', html_text, _re.DOTALL)
            for i, (href, title) in enumerate(titles[:5]):
                snippet = _html.unescape(_re.sub(r'<[^>]+>', '', snippets[i])).strip() if i < len(snippets) else ''
                results.append({
                    'title': _html.unescape(_re.sub(r'<[^>]+>', '', title)).strip(),
                    'url': href,
                    'snippet': snippet,
                })
            return {'results': results}

        elif tool == 'download_file':
            url = args.get('url', '')
            filename = _Path(args.get('filename', 'downloaded_file')).name
            import urllib.request
            dest = project_dir / filename
            urllib.request.urlretrieve(url, dest)
            return {'ok': True, 'path': filename, 'size': dest.stat().st_size}

        elif tool == 'delete_file':
            path = (project_dir / args['path'].lstrip('/')).resolve()
            if not str(path).startswith(str(project_dir)):
                return {'error': '허용되지 않은 경로'}
            if path.is_dir():
                shutil.rmtree(path)
            elif path.exists():
                path.unlink()
            return {'ok': True}

        elif tool == 'browser':
            action = args.get('action', 'screenshot')
            url = args.get('url', '')
            selector = args.get('selector', '')
            text_input = args.get('text', '')
            try:
                from playwright.sync_api import sync_playwright
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    page = browser.new_page()
                    if url:
                        page.goto(url, timeout=15000)
                    if action == 'screenshot':
                        ss_path = str(project_dir / '_screenshot.png')
                        page.screenshot(path=ss_path)
                        browser.close()
                        return {'ok': True, 'screenshot': '_screenshot.png'}
                    elif action == 'get_text':
                        content = page.locator(selector).inner_text() if selector else page.content()
                        browser.close()
                        return {'content': content[:5000]}
                    elif action == 'click':
                        page.click(selector)
                        browser.close()
                        return {'ok': True}
                    elif action == 'type':
                        page.fill(selector, text_input)
                        browser.close()
                        return {'ok': True}
                    else:
                        browser.close()
                        return {'error': '알 수 없는 액션'}
            except ImportError:
                return {'error': 'playwright 미설치'}
            except Exception as e:
                return {'error': str(e)[:200]}

        else:
            return {'error': f'알 수 없는 도구: {tool}'}

    except Exception as e:
        return {'error': str(e)[:300]}


@login_required
def ai_webdev_chat(request):
    """AI 웹개발 채팅 - 스트리밍 + 도구 실행 + DB 대화 영구 저장"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)

    credit = _get_or_create_credit(request.user)
    if not credit.can_use(1):
        return JsonResponse({
            'error': '크레딧이 부족합니다.',
            'credits': credit.credits,
            'no_credit': True,
        }, status=402)

    try:
        body = _json_mod.loads(request.body)
        project_id   = body.get('project_id')
        message      = body.get('message', '').strip()
        tool_results = body.get('tool_results', [])  # 클라이언트가 실행한 도구 결과
    except Exception:
        return JsonResponse({'error': '잘못된 요청'}, status=400)

    if not message:
        return JsonResponse({'error': '메시지를 입력하세요'}, status=400)

    from blog.models import AiWebProject, AiWebSession
    project = get_object_or_404(AiWebProject, pk=project_id, user=request.user)

    # ── DB에서 최근 대화 이력 자동 로딩 ──
    db_sessions = AiWebSession.objects.filter(project=project).order_by('created_at')
    db_history = []
    for s in db_sessions:
        role = 'user' if s.role == 'user' else 'assistant'
        db_history.append({'role': role, 'content': s.content[:1200]})

    # ── 시스템 프롬프트 ──
    SYSTEM = f"""당신은 풀스택 웹 개발 AI 에이전트입니다. 프로젝트명: "{project.name}".
실제로 파일을 만들고 명령어를 실행할 수 있습니다. 항상 한국어로 설명하세요.

사용 가능한 도구 (반드시 아래 XML 태그 형식 그대로 사용):
<tool_call>{{"tool":"write_file","args":{{"path":"파일경로","content":"파일내용"}}}}</tool_call>
<tool_call>{{"tool":"read_file","args":{{"path":"파일경로"}}}}</tool_call>
<tool_call>{{"tool":"list_files","args":{{"path":"."}}}}</tool_call>
<tool_call>{{"tool":"run_command","args":{{"command":"실행할명령어"}}}}</tool_call>
<tool_call>{{"tool":"web_search","args":{{"query":"검색어"}}}}</tool_call>
<tool_call>{{"tool":"delete_file","args":{{"path":"파일경로"}}}}</tool_call>

규칙:
- 파일을 만들 때는 반드시 write_file 도구를 직접 호출하세요
- 코드는 완전하게 작성하고, 설명은 간결하게
- HTML 프로젝트라면 index.html 기준으로 만드세요
- 도구 결과를 받으면 다음 작업을 이어서 진행하세요"""

    # ── 메시지 구성 ──
    messages = [{'role': 'system', 'content': SYSTEM}]

    # 최근 16턴 대화 이력 포함
    for h in db_history[-16:]:
        messages.append(h)

    # 도구 실행 결과가 있으면 포함
    user_content = message
    if tool_results:
        tool_summary = _json_stdlib.dumps(tool_results, ensure_ascii=False)[:3000]
        user_content = f"{message}\n\n[이전 도구 실행 결과]:\n{tool_summary}"

    messages.append({'role': 'user', 'content': user_content})

    # ── 사용자 메시지 DB 저장 ──
    AiWebSession.objects.create(project=project, role='user', content=message)

    # ── 스트리밍 생성기 ──
    def stream_response():
        full_text = ''
        saved = False
        try:
            from g4f.client import Client as G4FClient
            client = G4FClient()
            response = client.chat.completions.create(
                model='gpt-4o',
                messages=messages,
                stream=True,
            )
            for chunk in response:
                if hasattr(chunk, 'choices') and chunk.choices:
                    delta = chunk.choices[0].delta
                    if hasattr(delta, 'content') and delta.content:
                        token = delta.content
                        full_text += token
                        yield f"data: {_json_stdlib.dumps({'token': token})}\n\n"

            # AI 응답 DB 저장
            if full_text.strip():
                AiWebSession.objects.create(project=project, role='ai', content=full_text)
                saved = True
            yield f"data: {_json_stdlib.dumps({'done': True, 'full': full_text, 'saved': True})}\n\n"

        except Exception as e1:
            # 스트리밍 실패 시 일반 요청으로 폴백
            try:
                from g4f.client import Client as G4FClient
                client = G4FClient()
                resp2 = client.chat.completions.create(
                    model='gpt-4',
                    messages=messages,
                )
                full_text = (resp2.choices[0].message.content or '').strip()
                if not full_text:
                    raise ValueError('빈 응답')
                # 토큰 단위로 yield (청크처럼)
                chunk_size = 80
                for i in range(0, len(full_text), chunk_size):
                    yield f"data: {_json_stdlib.dumps({'token': full_text[i:i+chunk_size]})}\n\n"
                AiWebSession.objects.create(project=project, role='ai', content=full_text)
                yield f"data: {_json_stdlib.dumps({'done': True, 'full': full_text, 'saved': True})}\n\n"
            except Exception as e2:
                err_msg = f'AI 응답 오류: {str(e2)[:120]}'
                yield f"data: {_json_stdlib.dumps({'error': err_msg, 'done': True})}\n\n"

    # ── 크레딧 차감 ──
    credit.use(1)
    _log_credit(request.user, 'webdev', -1,
                credit.credits if not credit.is_unlimited else -1,
                note=f'AI웹개발|{project.name}|{message[:40]}')

    resp = StreamingHttpResponse(stream_response(), content_type='text/event-stream')
    resp['Cache-Control'] = 'no-cache'
    resp['X-Accel-Buffering'] = 'no'
    return resp


@login_required
def ai_webdev_history(request, pk):
    """프로젝트 대화 이력 JSON 반환"""
    from blog.models import AiWebProject, AiWebSession
    project = get_object_or_404(AiWebProject, pk=pk, user=request.user)
    sessions = AiWebSession.objects.filter(project=project).order_by('created_at')
    return JsonResponse({
        'history': [
            {
                'id': s.pk,
                'role': s.role,
                'content': s.content,
                'tool_calls': s.tool_calls,
                'created_at': s.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            }
            for s in sessions
        ]
    })


@login_required
def ai_webdev_clear_history(request, pk):
    """대화 이력 초기화"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)
    from blog.models import AiWebProject, AiWebSession
    project = get_object_or_404(AiWebProject, pk=pk, user=request.user)
    count = AiWebSession.objects.filter(project=project).delete()[0]
    return JsonResponse({'ok': True, 'deleted': count})


@login_required
def ai_credit_info(request):
    """크레딧 현황 JSON (클라이언트 실시간 업데이트용)"""
    credit = _get_or_create_credit(request.user)
    return JsonResponse({
        'credits': credit.credits,
        'is_unlimited': credit.is_unlimited,
        'total_used': credit.total_used,
    })


@login_required
def ai_webdev_files(request, pk):
    from blog.models import AiWebProject
    project = get_object_or_404(AiWebProject, pk=pk, user=request.user)
    project_dir = _get_project_dir(project.pk)

    def walk_dir(d, base):
        items = []
        try:
            for p in sorted(d.iterdir()):
                if p.name.startswith('.') or p.name == '__pycache__':
                    continue
                rel = str(p.relative_to(base))
                if p.is_dir():
                    items.append({'name': p.name, 'path': rel, 'type': 'dir', 'children': walk_dir(p, base)})
                else:
                    items.append({'name': p.name, 'path': rel, 'type': 'file', 'size': p.stat().st_size})
        except Exception:
            pass
        return items

    files = walk_dir(project_dir, project_dir) if project_dir.exists() else []
    return JsonResponse({'files': files})
"""
AI 웹개발 - 배포 + 미리보기 + 파일서빙 뷰
이 파일은 views.py 끝에 append됩니다.
"""

# ── 원클릭 배포 (Vercel CLI 자동 실행) ─────────────────────────────────────
@login_required
@require_POST
def ai_webdev_deploy(request, pk):
    """
    원클릭 배포: Vercel CLI로 자동 배포 (무료 도메인)
    - vercel CLI 없으면 자동 설치
    - 결과 URL을 DB에 저장
    """
    from blog.models import AiWebProject
    project = get_object_or_404(AiWebProject, pk=pk, user=request.user)
    project_dir = _get_project_dir(project.pk)

    import os as _os

    def do_deploy():
        # 1. vercel cli 설치 확인 (npx vercel 로 실행)
        node_check = subprocess.run('which node', shell=True, capture_output=True, text=True)
        if node_check.returncode != 0:
            # Node 없으면 netlify drop 방식 (정적파일 zip 업로드)
            yield f"data: {_json_stdlib.dumps({'log': '⚠️ Node.js 없음 → 정적 배포 모드로 전환'})}\n\n"
            result = _deploy_static_netlify(project_dir, project.name)
            yield f"data: {_json_stdlib.dumps({'log': result.get('log',''), 'url': result.get('url',''), 'done': True})}\n\n"
            return

        # 2. package.json 없으면 정적 html 배포
        has_pkg = (project_dir / 'package.json').exists()
        has_index = (project_dir / 'index.html').exists() or (project_dir / 'public' / 'index.html').exists()

        yield f"data: {_json_stdlib.dumps({'log': f'🚀 배포 시작... (프로젝트: {project.name})'})}\n\n"

        # vercel.json 자동 생성
        import json as _j
        if not (project_dir / 'vercel.json').exists():
            if has_pkg:
                vcfg = {"version": 2}
            else:
                vcfg = {"version": 2, "builds": [{"src": "**/*", "use": "@vercel/static"}]}
            (project_dir / 'vercel.json').write_text(_j.dumps(vcfg))
            yield f"data: {_json_stdlib.dumps({'log': '📄 vercel.json 자동 생성'})}\n\n"

        # npx vercel --prod --yes
        yield f"data: {_json_stdlib.dumps({'log': '📦 Vercel CLI 실행 중...'})}\n\n"
        env = {**_os.environ, 'HOME': str(project_dir), 'PATH': '/usr/local/bin:/usr/bin:/bin'}
        proc = subprocess.run(
            'npx vercel --prod --yes --token dummy 2>&1 || true',
            shell=True, cwd=str(project_dir),
            capture_output=True, text=True, timeout=120, env=env
        )
        output = proc.stdout + proc.stderr

        # URL 파싱
        import re as _re
        urls = _re.findall(r'https://[^\s"]+\.vercel\.app[^\s"]*', output)
        deploy_url = urls[0] if urls else ''

        if not deploy_url:
            # fallback: Netlify 정적 배포
            yield f"data: {_json_stdlib.dumps({'log': '⚠️ Vercel 인증 필요 → Netlify 정적 배포로 전환'})}\n\n"
            result = _deploy_static_netlify(project_dir, project.name)
            deploy_url = result.get('url', '')
            for log_line in result.get('logs', []):
                yield f"data: {_json_stdlib.dumps({'log': log_line})}\n\n"
        else:
            yield f"data: {_json_stdlib.dumps({'log': f'✅ 배포 완료!'})}\n\n"

        # DB 저장
        if deploy_url:
            project.deploy_url = deploy_url
            project.status = 'deployed'
            project.save(update_fields=['deploy_url', 'status'])

        yield f"data: {_json_stdlib.dumps({'log': f'🌐 배포 URL: {deploy_url}', 'url': deploy_url, 'done': True})}\n\n"

    resp = StreamingHttpResponse(do_deploy(), content_type='text/event-stream')
    resp['Cache-Control'] = 'no-cache'
    resp['X-Accel-Buffering'] = 'no'
    return resp


def _deploy_static_netlify(project_dir, project_name):
    """
    Netlify Drop API로 정적 배포 (API키 불필요 - netlify drop은 공개 API)
    zip으로 묶어서 POST 업로드
    """
    import zipfile, io, urllib.request, urllib.error
    import json as _j

    logs = []
    logs.append('📦 파일 압축 중...')

    # zip 생성 (메모리)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for fpath in project_dir.rglob('*'):
            if fpath.is_file() and not any(p in str(fpath) for p in ['node_modules', '.git', '__pycache__', '.venv']):
                arcname = str(fpath.relative_to(project_dir))
                zf.write(fpath, arcname)
    zip_data = buf.getvalue()
    logs.append(f'✅ 압축 완료 ({len(zip_data)//1024}KB)')

    # index.html 없으면 기본 생성
    has_index = (project_dir / 'index.html').exists()
    if not has_index:
        # zip에 index.html 추가
        buf2 = io.BytesIO()
        with zipfile.ZipFile(buf2, 'w', zipfile.ZIP_DEFLATED) as zf2:
            with zipfile.ZipFile(io.BytesIO(zip_data), 'r') as src:
                for item in src.infolist():
                    zf2.writestr(item, src.read(item.filename))
            zf2.writestr('index.html', f'<html><head><title>{project_name}</title></head><body><h1>{project_name}</h1><p>AI가 만든 프로젝트입니다.</p></body></html>')
        zip_data = buf2.getvalue()
        logs.append('📄 index.html 자동 생성')

    logs.append('🚀 Netlify에 업로드 중...')
    try:
        req = urllib.request.Request(
            'https://api.netlify.com/api/v1/sites',
            data=zip_data,
            headers={
                'Content-Type': 'application/zip',
                'User-Agent': 'Syblog-AI-Webdev/1.0',
            },
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=60) as r:
            data = _j.loads(r.read())
        url = data.get('ssl_url') or data.get('url', '')
        logs.append(f'✅ Netlify 배포 성공!')
        return {'url': url, 'logs': logs}
    except urllib.error.HTTPError as e:
        err_body = e.read().decode()[:200]
        logs.append(f'❌ Netlify 오류: {e.code} - {err_body}')
        # surpress error - just return no URL
        return {'url': '', 'logs': logs, 'error': str(e)}
    except Exception as e:
        logs.append(f'❌ 배포 오류: {str(e)[:100]}')
        return {'url': '', 'logs': logs, 'error': str(e)}


# ── 프로젝트 내장 미리보기 (iframe으로 서빙) ───────────────────────────────
@login_required
def ai_webdev_preview(request, pk):
    """
    프로젝트 파일을 Django에서 직접 서빙 → iframe으로 미리보기
    path GET 파라미터로 특정 파일 지정 (기본: index.html)
    """
    from blog.models import AiWebProject
    project = get_object_or_404(AiWebProject, pk=pk, user=request.user)
    project_dir = _get_project_dir(project.pk)

    file_path = request.GET.get('path', 'index.html').lstrip('/')
    target = (project_dir / file_path).resolve()

    if not str(target).startswith(str(project_dir)):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden('허용되지 않은 경로')

    if not target.exists():
        # index.html 없으면 파일 목록 표시
        files = []
        if project_dir.exists():
            for p in sorted(project_dir.rglob('*')):
                if p.is_file() and 'node_modules' not in str(p):
                    files.append(str(p.relative_to(project_dir)))
        html = f"""<!DOCTYPE html>
<html lang="ko">
<head><meta charset="UTF-8"><title>{project.name} - 파일 목록</title>
<style>body{{font-family:sans-serif;padding:20px;background:#f5f5f5;}}
a{{display:block;padding:6px;color:#6c63ff;text-decoration:none;}}
a:hover{{background:#eef;}}h2{{color:#333;}}</style></head>
<body><h2>📁 {project.name}</h2>
<p>index.html이 없습니다. 파일 목록:</p>
{''.join(f'<a href="?path={f}">{f}</a>' for f in files) or '<p>파일이 없습니다.</p>'}
</body></html>"""
        return HttpResponse(html, content_type='text/html; charset=utf-8')

    # MIME 타입 결정
    import mimetypes
    mime, _ = mimetypes.guess_type(str(target))
    if not mime:
        mime = 'text/plain'

    # HTML 파일은 base 경로 주입 (상대경로 자원 처리)
    if mime == 'text/html':
        content = target.read_text(encoding='utf-8', errors='replace')
        # 상대 경로 → 프리뷰 경로로 rewrite
        base_tag = f'<base href="/blog/ai-webdev/{pk}/preview/">'
        if '<head>' in content:
            content = content.replace('<head>', f'<head>{base_tag}', 1)
        elif '<html>' in content:
            content = content.replace('<html>', f'<html><head>{base_tag}</head>', 1)
        return HttpResponse(content, content_type='text/html; charset=utf-8')

    # CSS / JS / 이미지 등
    return HttpResponse(target.read_bytes(), content_type=mime)


# ── 미리보기용 정적파일 서빙 (base href 없이 직접) ─────────────────────────
@login_required
def ai_webdev_static(request, pk, filepath):
    """프로젝트 내 정적파일 서빙 (CSS, JS, 이미지 등)"""
    from blog.models import AiWebProject
    project = get_object_or_404(AiWebProject, pk=pk, user=request.user)
    project_dir = _get_project_dir(project.pk)

    target = (project_dir / filepath.lstrip('/')).resolve()
    if not str(target).startswith(str(project_dir)) or not target.exists():
        from django.http import Http404
        raise Http404

    import mimetypes
    mime, _ = mimetypes.guess_type(str(target))
    return HttpResponse(target.read_bytes(), content_type=mime or 'application/octet-stream')


# ── 터미널 스트리밍 실행 ─────────────────────────────────────────────────────
@login_required  
def ai_webdev_terminal_stream(request, pk):
    """터미널 명령어를 실시간 스트리밍으로 실행"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)

    from blog.models import AiWebProject
    import os as _os

    project = get_object_or_404(AiWebProject, pk=pk, user=request.user)
    project_dir = _get_project_dir(project.pk)

    try:
        body = _json_mod.loads(request.body)
        cmd = body.get('command', '').strip()
    except Exception:
        return JsonResponse({'error': '잘못된 요청'}, status=400)

    if not cmd:
        return JsonResponse({'error': '명령어를 입력하세요'}, status=400)

    blocked = ['rm -rf /', ':(){', '>/dev/sda', 'shutdown', 'reboot']
    for b in blocked:
        if b in cmd:
            return JsonResponse({'error': f'차단된 명령어입니다'}, status=400)

    def stream_cmd():
        try:
            env = {**_os.environ, 'HOME': str(project_dir), 'PATH': '/usr/local/bin:/usr/bin:/bin:/usr/local/sbin'}
            proc = subprocess.Popen(
                cmd, shell=True, cwd=str(project_dir),
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, env=env,
                bufsize=1
            )
            for line in iter(proc.stdout.readline, ''):
                yield f"data: {_json_stdlib.dumps({'line': line})}\n\n"
            proc.wait()
            yield f"data: {_json_stdlib.dumps({'done': True, 'returncode': proc.returncode})}\n\n"
        except Exception as e:
            yield f"data: {_json_stdlib.dumps({'error': str(e), 'done': True})}\n\n"

    resp = StreamingHttpResponse(stream_cmd(), content_type='text/event-stream')
    resp['Cache-Control'] = 'no-cache'
    resp['X-Accel-Buffering'] = 'no'
    return resp


# ── 프로젝트 파일 읽기/저장 API (에디터용) ──────────────────────────────────
@login_required
def ai_webdev_file_read(request, pk):
    """특정 파일 내용 반환"""
    from blog.models import AiWebProject
    project = get_object_or_404(AiWebProject, pk=pk, user=request.user)
    project_dir = _get_project_dir(project.pk)
    path = request.GET.get('path', '').lstrip('/')
    if not path:
        return JsonResponse({'error': '경로 필요'}, status=400)
    target = (project_dir / path).resolve()
    if not str(target).startswith(str(project_dir)):
        return JsonResponse({'error': '허용되지 않은 경로'}, status=403)
    if not target.exists():
        return JsonResponse({'error': '파일 없음'}, status=404)
    content = target.read_text(encoding='utf-8', errors='replace')
    return JsonResponse({'content': content, 'path': path})


@login_required
@require_POST
def ai_webdev_file_write(request, pk):
    """파일 저장"""
    from blog.models import AiWebProject
    project = get_object_or_404(AiWebProject, pk=pk, user=request.user)
    project_dir = _get_project_dir(project.pk)
    try:
        body = _json_mod.loads(request.body)
        path = body.get('path', '').lstrip('/')
        content = body.get('content', '')
    except Exception:
        return JsonResponse({'error': '잘못된 요청'}, status=400)
    if not path:
        return JsonResponse({'error': '경로 필요'}, status=400)
    target = (project_dir / path).resolve()
    if not str(target).startswith(str(project_dir)):
        return JsonResponse({'error': '허용되지 않은 경로'}, status=403)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding='utf-8')
    return JsonResponse({'ok': True, 'path': path})
