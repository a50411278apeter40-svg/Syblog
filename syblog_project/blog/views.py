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
import logging

logger = logging.getLogger(__name__)


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

# ── 백업 진행 상태 추적 ──
import threading as _threading
_backup_status = {'running': False, 'result': None, 'msg': '', 'started_at': None}
_backup_lock = _threading.Lock()

def _run_backup_background():
    """백그라운드 스레드에서 백업 실행 (gunicorn 타임아웃 우회)"""
    import datetime as _dt
    with _backup_lock:
        _backup_status['running'] = True
        _backup_status['result'] = None
        _backup_status['msg'] = '백업 진행 중...'
        _backup_status['started_at'] = _dt.datetime.now().strftime('%H:%M:%S')
    try:
        success, msg = perform_backup()
        with _backup_lock:
            _backup_status['running'] = False
            _backup_status['result'] = success
            _backup_status['msg'] = msg
        logger.info(f'[backup-bg] 완료: success={success}, msg={msg}')
    except Exception as _e:
        with _backup_lock:
            _backup_status['running'] = False
            _backup_status['result'] = False
            _backup_status['msg'] = str(_e)
        logger.error(f'[backup-bg] 예외: {_e}', exc_info=True)

@staff_member_required
def backup_to_github(request):
    if request.method != 'POST':
        return redirect('blog:admin_dashboard')

    with _backup_lock:
        already_running = _backup_status['running']

    if already_running:
        messages.warning(request, '⏳ 백업이 이미 진행 중입니다. 잠시 후 결과를 확인하세요.')
        return redirect('blog:admin_dashboard')

    # 백그라운드 스레드로 백업 실행 (gunicorn worker 타임아웃 방지)
    t = _threading.Thread(target=_run_backup_background, daemon=True)
    t.start()
    messages.info(request, '🔄 백업이 백그라운드에서 시작되었습니다. 1~2분 후 결과를 확인하세요.')
    return redirect('blog:admin_dashboard')

@staff_member_required  
def backup_status_api(request):
    """백업 진행 상태 JSON API"""
    with _backup_lock:
        status = dict(_backup_status)
    return JsonResponse(status)

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


def notice_detail(request, pk):
    """공지사항 상세 페이지 — 로그인 불필요, 누구나 접근 가능"""
    from blog.models import Notice
    from django.utils import timezone
    notice = get_object_or_404(Notice, pk=pk)
    # 만료됐거나 비활성이면 404
    if not notice.is_visible():
        from django.http import Http404
        raise Http404("공지사항을 찾을 수 없습니다.")
    logger.info(f"[Notice] 상세 조회: pk={pk} title={notice.title}")
    return render(request, 'blog/notice_detail.html', {'notice': notice})


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

# ── Playwright 영구 세션 (프로젝트별 browser + page 재사용) ──
_pw_sessions = {}   # {project_pk: {'pw': ..., 'browser': ..., 'page': ..., 'url': ...}}

def _get_pw_page(pk, viewport_w=1280, viewport_h=800):
    """프로젝트별 Playwright 페이지를 영구 유지/재사용한다."""
    if not _ensure_playwright():
        raise ImportError('playwright 설치 실패')
    try:
        from playwright.sync_api import sync_playwright as _sync_pw
    except ImportError as e:
        raise ImportError(f'playwright import 실패: {e}')

    sess = _pw_sessions.get(pk)
    if sess:
        try:
            _ = sess['page'].url
            return sess['page'], sess
        except Exception:
            try: sess['browser'].close()
            except Exception: pass
            try: sess['pw'].__exit__(None, None, None)
            except Exception: pass
            _pw_sessions.pop(pk, None)

    pw_ctx = _sync_pw()
    pw = pw_ctx.__enter__()
    browser = pw.chromium.launch(
        headless=True,
        args=[
            '--no-sandbox', '--disable-setuid-sandbox',
            '--disable-dev-shm-usage', '--disable-gpu',
            '--disable-extensions', '--single-process',
        ]
    )
    ctx = browser.new_context(
        viewport={'width': viewport_w, 'height': viewport_h},
        user_agent='Mozilla/5.0 (compatible; SyblogBot/1.0)',
        ignore_https_errors=True,
    )
    page = ctx.new_page()
    sess = {'pw_ctx': pw_ctx, 'pw': pw, 'browser': browser, 'ctx': ctx, 'page': page}
    _pw_sessions[pk] = sess
    return page, sess



WEBDEV_WORKSPACE = _Path('/tmp/syblog_webdev')
WEBDEV_WORKSPACE.mkdir(exist_ok=True)

# ── 프로젝트별 독립 venv 환경 관리 ─────────────────────────────
_WEBDEV_ENV_READY: set = set()  # 이 서버 프로세스에서 준비 완료된 프로젝트


def _get_project_venv(project_dir: _Path) -> _Path:
    """프로젝트 전용 venv 경로 반환 (없으면 자동 생성)"""
    venv_dir = project_dir / '.venv'
    if not (venv_dir / 'bin' / 'python3').exists():
        subprocess.run(
            ['python3', '-m', 'venv', str(venv_dir)],
            timeout=90, capture_output=True
        )
        pip_path = venv_dir / 'bin' / 'pip'
        if pip_path.exists():
            subprocess.run(
                [str(pip_path), 'install', '--upgrade', 'pip', 'setuptools', '--quiet'],
                timeout=60, capture_output=True
            )
    return venv_dir


def _get_venv_env(project_dir: _Path) -> dict:
    """프로젝트 venv가 활성화된 환경변수 dict 반환 (Python 3.11 + Node 20)"""
    venv_dir = _get_project_venv(project_dir)
    venv_bin = str(venv_dir / 'bin')
    return {
        **os.environ,
        'VIRTUAL_ENV': str(venv_dir),
        'PATH': f'{venv_bin}:/usr/bin:/bin:/usr/local/bin',
        'HOME': str(project_dir),
        'PYTHONPATH': '',
        'NODE_PATH': '/usr/lib/node_modules',
    }


def _ensure_playwright():
    """playwright가 없으면 시스템 pip으로 자동 설치 후 chromium 바이너리 설치"""
    try:
        import playwright  # noqa
        return True
    except ImportError:
        pass
    import sys
    candidates = [
        sys.executable.replace('python3', 'pip3').replace('python', 'pip'),
        '/usr/local/bin/pip3', '/usr/bin/pip3', 'pip3', 'pip',
    ]
    for pip_exe in candidates:
        try:
            r = subprocess.run(
                [pip_exe, 'install', 'playwright==1.49.1', '--quiet'],
                capture_output=True, timeout=120
            )
            if r.returncode == 0:
                subprocess.run(['playwright', 'install', 'chromium'],
                               capture_output=True, timeout=180)
                return True
        except Exception:
            continue
    return False


def _webdev_auto_restore_env(project_dir: _Path):
    """
    프로젝트 진입 시 venv 생성 확인 + requirements.txt 있으면 자동 설치.
    서버 프로세스당 1회만 실행 (_WEBDEV_ENV_READY 캐시).
    """
    cache_key = str(project_dir)
    if cache_key in _WEBDEV_ENV_READY:
        return
    try:
        venv_dir = _get_project_venv(project_dir)
        req_file = project_dir / 'requirements.txt'
        if req_file.exists():
            pip_path = venv_dir / 'bin' / 'pip'
            if pip_path.exists():
                subprocess.run(
                    [str(pip_path), 'install', '-r', str(req_file), '--quiet'],
                    timeout=300, capture_output=True,
                    env=_get_venv_env(project_dir)
                )
    except Exception:
        pass
    _WEBDEV_ENV_READY.add(cache_key)


def _get_project_dir(project_id) -> _Path:
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
    project_dir = _get_project_dir(project.pk)
    # 새로고침/재진입 시 requirements.txt 있으면 자동 pip install
    _webdev_auto_restore_env(project_dir)
    return render(request, 'blog/ai_webdev_project.html', {
        'project': project,
        'sessions': sessions,
        'credit': credit,
        'project_dir': str(project_dir),
    })


@login_required
@require_POST
def ai_webdev_tool(request, pk=None):
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
            blocked = ['rm -rf /', ':(){', 'shutdown', 'reboot']
            for b in blocked:
                if b in cmd:
                    return {'error': '차단된 명령어'}
            import re as _re_rc
            # 프로젝트 독립 venv 환경 (Python 3.11 + Node 20)
            env = _get_venv_env(project_dir)
            venv_bin = str(_get_project_venv(project_dir) / 'bin')
            cmd_fixed = cmd
            if venv_bin not in cmd_fixed:
                cmd_fixed = _re_rc.sub(r'(?<![/\w])pip3?\s+install',
                                       f'{venv_bin}/pip install', cmd_fixed)
                cmd_fixed = _re_rc.sub(r'(?<![/\w])pip3?(?!\s*install)\b',
                                       f'{venv_bin}/pip', cmd_fixed)
                cmd_fixed = _re_rc.sub(r'(?<![/\w])python3?\b',
                                       f'{venv_bin}/python3', cmd_fixed)
            proc = subprocess.run(
                cmd_fixed, shell=True, cwd=str(project_dir),
                capture_output=True, text=True, timeout=120,
                env=env
            )
            # pip install 성공시 requirements.txt 자동 갱신
            if _re_rc.search(r'\bpip\b.*\binstall\b', cmd_fixed) and proc.returncode == 0:
                try:
                    pip_exe = f'{venv_bin}/pip'
                    freeze = subprocess.run(
                        [pip_exe, 'freeze'], capture_output=True, text=True, env=env)
                    if freeze.returncode == 0:
                        (project_dir / 'requirements.txt').write_text(
                            freeze.stdout, encoding='utf-8')
                except Exception:
                    pass
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
            wait_ms = int(args.get('wait', 1000))
            try:
                # ── 영구 세션 재사용 ──
                page, _ = _get_pw_page(pk)

                if action == 'close_session':
                    sess = _pw_sessions.pop(pk, None)
                    if sess:
                        try: sess['browser'].close()
                        except Exception: pass
                        try: sess['pw_ctx'].__exit__(None,None,None)
                        except Exception: pass
                    return {'ok': True, 'msg': '브라우저 세션 종료'}

                if url:
                    page.goto(url, timeout=25000, wait_until='domcontentloaded')
                    if wait_ms > 0:
                        page.wait_for_timeout(min(wait_ms, 4000))

                if action == 'screenshot':
                    ss_path = str(project_dir / '_screenshot.png')
                    page.screenshot(path=ss_path, full_page=False)
                    return {'ok': True, 'screenshot': '_screenshot.png',
                            'title': page.title(), 'current_url': page.url,
                            'session': 'persistent'}
                elif action == 'get_text':
                    if selector:
                        try:
                            txt = page.locator(selector).first.inner_text(timeout=5000)
                        except Exception:
                            txt = ''
                    else:
                        txt = page.inner_text('body') if page.locator('body').count() else page.content()
                    return {'content': txt[:8000], 'title': page.title(), 'current_url': page.url}
                elif action == 'get_html':
                    html = page.content()
                    return {'html': html[:10000], 'title': page.title(), 'current_url': page.url}
                elif action == 'click':
                    page.locator(selector).first.click(timeout=5000)
                    page.wait_for_timeout(500)
                    return {'ok': True, 'current_url': page.url}
                elif action == 'type':
                    page.locator(selector).first.fill(text_input, timeout=5000)
                    return {'ok': True, 'current_url': page.url}
                elif action == 'evaluate':
                    js_code = args.get('js', 'document.title')
                    result_js = page.evaluate(js_code)
                    return {'result': str(result_js)[:2000], 'current_url': page.url}
                elif action == 'back':
                    page.go_back(timeout=10000)
                    return {'ok': True, 'current_url': page.url}
                elif action == 'forward':
                    page.go_forward(timeout=10000)
                    return {'ok': True, 'current_url': page.url}
                elif action == 'reload':
                    page.reload(timeout=15000)
                    return {'ok': True, 'current_url': page.url}
                elif action == 'current_url':
                    return {'current_url': page.url, 'title': page.title()}
                else:
                    return {'error': f'알 수 없는 액션: {action}'}
            except ImportError:
                return {'error': 'playwright 미설치 또는 브라우저 미준비. 잠시 후 자동 설치됩니다. 다시 시도해주세요.'}
            except Exception as e:
                # 세션 깨진 경우 초기화 후 재시도
                _pw_sessions.pop(pk, None)
                return {'error': f'browser 오류: {str(e)[:300]}'}

        else:
            return {'error': f'알 수 없는 도구: {tool}'}

    except Exception as e:
        return {'error': str(e)[:300]}


@login_required
def ai_webdev_chat(request, pk=None):
    """AI 웹개발 채팅 - 스트리밍 + 도구 실행 + DB 대화 영구 저장"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)

    if not request.user.is_authenticated:
        return JsonResponse({'error': '로그인이 필요합니다.', 'no_credit': False}, status=401)

    credit = _get_or_create_credit(request.user)
    if not credit.can_use(1):
        return JsonResponse({
            'error': '크레딧이 부족합니다. 크레딧을 구매해주세요.',
            'credits': credit.credits,
            'no_credit': True,
        }, status=402)

    # ── 요청 파싱 (JSON or multipart/form-data) ──
    uploaded_images = []   # [{"name":..., "base64":..., "mime":...}]
    uploaded_files  = []   # [{"name":..., "path":... (저장 경로), "size":...}]

    content_type = request.content_type or ''
    if 'multipart' in content_type or 'form-data' in content_type:
        project_id   = request.POST.get('project_id', pk)
        message      = (request.POST.get('message') or '').strip()
        tool_results = _json_mod.loads(request.POST.get('tool_results', '[]'))

        # 첨부 파일 처리
        import base64 as _b64, os as _os
        _IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.svg'}
        # project_id를 안전하게 정수로 변환
        _proj_id_safe = int(project_id) if project_id else int(pk)
        for _f in request.FILES.getlist('files'):
            _ext = _os.path.splitext(_f.name)[1].lower()
            _bytes = _f.read()   # 한 번만 읽고 재사용
            if _ext in _IMAGE_EXTS:
                # 이미지 → base64 변환 후 multimodal에 전달
                _mime = _f.content_type or f'image/{_ext.lstrip(".")}'
                if not _mime or _mime == 'application/octet-stream':
                    _mime = f'image/{_ext.lstrip(".") or "jpeg"}'
                uploaded_images.append({
                    'name': _f.name,
                    'base64': _b64.b64encode(_bytes).decode(),
                    'mime': _mime,
                })
            # 모든 파일 → 프로젝트 디렉토리에 저장
            try:
                from blog.models import AiWebProject as _AiWebProject2
                _proj_tmp = _AiWebProject2.objects.get(pk=_proj_id_safe, user=request.user)
                _proj_dir = _get_project_dir(_proj_tmp.pk)
                _save_path = _proj_dir / 'uploads' / _f.name
                _save_path.parent.mkdir(parents=True, exist_ok=True)
                with open(_save_path, 'wb') as _sf:
                    _sf.write(_bytes)   # 이미 읽어둔 bytes 사용
                uploaded_files.append({
                    'name': _f.name,
                    'path': f'uploads/{_f.name}',
                    'size': len(_bytes),
                })
            except Exception as _fe:
                logger.warning(f'[chat-upload] 파일 저장 실패: {_fe}')
    else:
        try:
            body = _json_mod.loads(request.body)
            project_id   = body.get('project_id', pk)
            message      = (body.get('message') or '').strip()
            tool_results = body.get('tool_results', [])
        except Exception as parse_err:
            return JsonResponse({'error': f'잘못된 요청: {str(parse_err)[:80]}'}, status=400)

    # tool_results가 None일 때 방어
    if tool_results is None:
        tool_results = []

    if not message and not uploaded_images and not uploaded_files:
        return JsonResponse({'error': '메시지나 파일을 입력하세요'}, status=400)

    if not project_id:
        return JsonResponse({'error': '프로젝트 ID가 없습니다.'}, status=400)

    try:
        from blog.models import AiWebProject, AiWebSession
        project = AiWebProject.objects.get(pk=project_id, user=request.user)
    except Exception:
        return JsonResponse({'error': '프로젝트를 찾을 수 없습니다.'}, status=404)

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
    text_content = message or ''
    if tool_results:
        tool_summary = _json_stdlib.dumps(tool_results, ensure_ascii=False)[:3000]
        text_content = f"{text_content}\n\n[이전 도구 실행 결과]:\n{tool_summary}"
    if uploaded_files:
        file_list = ', '.join(f['name'] for f in uploaded_files)
        text_content += f"\n\n[업로드된 파일: {file_list}] — 파일은 프로젝트의 uploads/ 폴더에 저장됨"

    # 이미지가 있으면 multimodal content 구성 (GPT-4V / gpt-4o)
    if uploaded_images:
        import base64 as _b64_mc
        user_content_parts = []
        if text_content:
            user_content_parts.append({'type': 'text', 'text': text_content})
        for img in uploaded_images:
            user_content_parts.append({
                'type': 'image_url',
                'image_url': {
                    'url': f'data:{img["mime"]};base64,{img["base64"]}',
                    'detail': 'high',
                }
            })
        messages.append({'role': 'user', 'content': user_content_parts})
    else:
        messages.append({'role': 'user', 'content': text_content})

    # ── 사용자 메시지 DB 저장 ──
    db_msg = message
    if uploaded_files:
        db_msg += ' [첨부: ' + ', '.join(f['name'] for f in uploaded_files) + ']'
    if uploaded_images:
        db_msg += ' [이미지: ' + ', '.join(i['name'] for i in uploaded_images) + ']'
    AiWebSession.objects.create(project=project, role='user', content=db_msg)

    # ── g4f 모델 폴백 목록 ──
    _G4F_MODELS = ['gpt-4o', 'gpt-4o-mini', 'gpt-4', 'gpt-3.5-turbo']
    _has_images = bool(uploaded_images)

    # ── 스트리밍 생성기 ──
    def stream_response():
        import time as _time
        full_text = ''
        # 이미지가 있을 때 텍스트 폴백 메시지 준비 (vision 실패 대비)
        _text_only_messages = None
        if _has_images:
            _img_names = ', '.join(i['name'] for i in uploaded_images)
            _text_fallback_content = (text_content or '') + f'\n\n[첨부 이미지: {_img_names}] — 이미지를 분석해서 웹 개발 작업을 도와주세요.'
            _text_only_messages = messages[:-1] + [{'role': 'user', 'content': _text_fallback_content}]

        try:
            from g4f.client import Client as G4FClient
            client = G4FClient()

            # 스트리밍 시도 (모델 폴백) — 이미지 있으면 vision 먼저, 실패 시 텍스트 전용
            response = None
            last_err = None
            _msgs_to_use = messages

            # vision 모델 먼저 시도
            _vision_models = ['gpt-4o', 'gpt-4-vision-preview'] if _has_images else []
            _all_models = _vision_models + [m for m in _G4F_MODELS if m not in _vision_models]

            for _midx, _model in enumerate(_all_models):
                # vision 모델 실패 후엔 텍스트 전용 메시지로 전환
                if _has_images and _midx >= len(_vision_models) and _text_only_messages:
                    _msgs_to_use = _text_only_messages
                try:
                    response = client.chat.completions.create(
                        model=_model, messages=_msgs_to_use, stream=True,
                    )
                    break
                except Exception as _me:
                    last_err = _me
                    _time.sleep(0.3)
                    continue

            if response is None:
                raise Exception(f'모든 모델 실패: {last_err}')

            for chunk in response:
                if hasattr(chunk, 'choices') and chunk.choices:
                    delta = chunk.choices[0].delta
                    if hasattr(delta, 'content') and delta.content:
                        token = delta.content
                        full_text += token
                        yield f"data: {_json_stdlib.dumps({'token': token})}\n\n"

            # AI 응답 DB 저장
            if full_text.strip():
                try:
                    AiWebSession.objects.create(project=project, role='ai', content=full_text)
                except Exception:
                    pass
            yield f"data: {_json_stdlib.dumps({'done': True, 'full': full_text, 'saved': True})}\n\n"

        except Exception as e1:
            # 스트리밍 실패 → 논스트리밍 폴백
            try:
                from g4f.client import Client as G4FClient
                client = G4FClient()
                resp2 = None
                last_err2 = None
                _msgs2 = _text_only_messages if (_has_images and _text_only_messages) else messages
                for _model in _G4F_MODELS:
                    try:
                        resp2 = client.chat.completions.create(
                            model=_model, messages=_msgs2, stream=False,
                        )
                        break
                    except Exception as _me2:
                        last_err2 = _me2
                        continue

                if resp2 is None:
                    raise ValueError(f'모든 모델 응답 실패: {last_err2}')

                full_text = (resp2.choices[0].message.content or '').strip()
                if not full_text:
                    raise ValueError('빈 응답')

                chunk_size = 80
                for i in range(0, len(full_text), chunk_size):
                    yield f"data: {_json_stdlib.dumps({'token': full_text[i:i+chunk_size]})}\n\n"

                try:
                    AiWebSession.objects.create(project=project, role='ai', content=full_text)
                except Exception:
                    pass
                yield f"data: {_json_stdlib.dumps({'done': True, 'full': full_text, 'saved': True})}\n\n"

            except Exception as e2:
                err_msg = f'AI 응답 오류: {str(e2)[:200]}'
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
    """프로젝트 대화 이력 JSON 반환 (+ 실행중 task 상태)"""
    from blog.models import AiWebProject, AiWebSession, AiWebTask
    project = get_object_or_404(AiWebProject, pk=pk, user=request.user)
    sessions = AiWebSession.objects.filter(project=project).order_by('created_at')

    # 실행중 task 조회
    running_task = AiWebTask.objects.filter(
        project=project, status=AiWebTask.STATUS_RUNNING
    ).order_by('-created_at').first()

    task_info = None
    if running_task:
        task_info = {
            'id': running_task.pk,
            'status': running_task.status,
            'label': running_task.label or '명령 실행 중...',
            'updated_at': running_task.updated_at.strftime('%Y-%m-%d %H:%M:%S'),
        }

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
        ],
        'running_task': task_info,
    })



@login_required
def ai_webdev_upload(request, pk):
    """AI 웹빌더 파일 업로드 — 스토리지 저장 + 이미지 목록 반환"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)
    try:
        project = AiWebProject.objects.get(pk=pk, user=request.user)
    except Exception:
        return JsonResponse({'error': '프로젝트 없음'}, status=404)

    import base64 as _b64u, os as _os
    _IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.svg'}
    proj_dir = _get_project_dir(project.pk)
    upload_dir = proj_dir / 'uploads'
    upload_dir.mkdir(parents=True, exist_ok=True)

    saved = []
    images_b64 = []

    for _f in request.FILES.getlist('files'):
        _ext = _os.path.splitext(_f.name)[1].lower()
        _bytes = _f.read()
        _save_path = upload_dir / _f.name
        with open(_save_path, 'wb') as _sf:
            _sf.write(_bytes)
        entry = {
            'name': _f.name,
            'path': f'uploads/{_f.name}',
            'size': len(_bytes),
            'is_image': _ext in _IMAGE_EXTS,
        }
        saved.append(entry)
        if _ext in _IMAGE_EXTS:
            _mime = _f.content_type or f'image/{_ext.lstrip(".")}'
            images_b64.append({
                'name': _f.name,
                'mime': _mime,
                'base64': _b64u.b64encode(_bytes).decode(),
            })
        logger.info(f'[upload] 저장: {_f.name} ({len(_bytes)} bytes) → {_save_path}')

    return JsonResponse({'ok': True, 'saved': saved, 'images': images_b64})

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
@login_required
def ai_credit_info(request):
    """크레딧 현황 JSON (클라이언트 실시간 업데이트용)"""
    if not request.user.is_authenticated:
        return JsonResponse({'credits': 0, 'is_unlimited': False, 'total_used': 0})
    credit = _get_or_create_credit(request.user)
    profile = getattr(request.user, 'profile', None)
    return JsonResponse({
        'credits': -1 if credit.is_unlimited else credit.credits,
        'is_unlimited': credit.is_unlimited,
        'total_used': credit.total_used,
        'points': profile.points if profile else 0,
        'low': (not credit.is_unlimited) and credit.credits <= 5,
    })




@login_required
def ai_webdev_task_status(request, pk):
    """실행중 task 상태 조회"""
    from blog.models import AiWebProject, AiWebTask
    project = get_object_or_404(AiWebProject, pk=pk, user=request.user)
    task = AiWebTask.objects.filter(project=project, status=AiWebTask.STATUS_RUNNING).order_by('-created_at').first()
    if task:
        return JsonResponse({
            'running': True,
            'id': task.pk,
            'label': task.label or '명령 실행 중...',
            'updated_at': task.updated_at.strftime('%Y-%m-%d %H:%M:%S'),
        })
    return JsonResponse({'running': False})


@login_required
def ai_webdev_task_upsert(request, pk):
    """task 상태 생성/업데이트 (프런트에서 호출)"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)
    from blog.models import AiWebProject, AiWebTask
    project = get_object_or_404(AiWebProject, pk=pk, user=request.user)
    try:
        body = _json_mod.loads(request.body)
    except Exception:
        return JsonResponse({'error': '잘못된 요청'}, status=400)

    action     = body.get('action', 'start')   # start | update | done | error | cancel
    label      = body.get('label', '')
    result_msg = body.get('result_msg', '')
    error_msg  = body.get('error_msg', '')
    task_id    = body.get('task_id')

    if action == 'start':
        # 이전 running task 정리
        AiWebTask.objects.filter(project=project, status=AiWebTask.STATUS_RUNNING).update(
            status=AiWebTask.STATUS_CANCELLED
        )
        task = AiWebTask.objects.create(project=project, status=AiWebTask.STATUS_RUNNING, label=label)
        return JsonResponse({'ok': True, 'task_id': task.pk})

    elif action in ('update', 'done', 'error', 'cancel'):
        qs = AiWebTask.objects.filter(project=project)
        if task_id:
            qs = qs.filter(pk=task_id)
        else:
            qs = qs.filter(status=AiWebTask.STATUS_RUNNING)
        task = qs.order_by('-created_at').first()
        if not task:
            return JsonResponse({'error': 'task 없음'}, status=404)

        if action == 'update':
            task.label = label or task.label
            task.save(update_fields=['label', 'updated_at'])
        elif action == 'done':
            task.status = AiWebTask.STATUS_DONE
            task.result_msg = result_msg
            task.label = label or '작업 완료'
            task.save()
        elif action == 'error':
            task.status = AiWebTask.STATUS_ERROR
            task.error_msg = error_msg
            task.label = label or '오류 발생'
            task.save()
        elif action == 'cancel':
            task.status = AiWebTask.STATUS_CANCELLED
            task.save()
        return JsonResponse({'ok': True, 'task_id': task.pk, 'status': task.status})

    return JsonResponse({'error': '알 수 없는 action'}, status=400)

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
    """터미널 명령어 실시간 스트리밍 (venv 자동교정 + cd 세션유지)"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)

    from blog.models import AiWebProject
    import os as _os
    import re as _re

    project = get_object_or_404(AiWebProject, pk=pk, user=request.user)
    project_dir = _get_project_dir(project.pk)

    try:
        body = _json_mod.loads(request.body)
        cmd = body.get('command', '').strip()
        cwd_rel = body.get('cwd', '.').strip()
    except Exception:
        return JsonResponse({'error': '잘못된 요청'}, status=400)

    if not cmd:
        return JsonResponse({'error': '명령어를 입력하세요'}, status=400)

    blocked = ['rm -rf /', ':(){', '>/dev/sda', 'shutdown', 'reboot']
    for b in blocked:
        if b in cmd:
            return JsonResponse({'error': '차단된 명령어입니다'}, status=400)

    # venv 경로
    proj_venv = _get_project_venv(project_dir)
    venv_bin  = str(proj_venv / 'bin')
    venv_pip  = f'{venv_bin}/pip'
    venv_py   = f'{venv_bin}/python3'

    def fix_cmd(c):
        if venv_bin in c:
            return c
        c = _re.sub(r'(?<![/\w])pip3?\s+install', f'{venv_pip} install', c)
        c = _re.sub(r'(?<![/\w])pip3?(?!\s*install)\b', venv_pip, c)
        c = _re.sub(r'(?<![/\w])python3?\b', venv_py, c)
        return c

    cmd_fixed = fix_cmd(cmd)

    # CWD 계산
    try:
        cwd_path = project_dir if (not cwd_rel or cwd_rel == '.') else (project_dir / cwd_rel).resolve()
        if not str(cwd_path).startswith(str(project_dir)):
            cwd_path = project_dir
    except Exception:
        cwd_path = project_dir

    def stream_cmd():
        try:
            env = _get_venv_env(project_dir)

            # cd 명령 처리
            cd_match = _re.match(r'^cd\s*(.*)', cmd.strip())
            if cd_match:
                target = cd_match.group(1).strip()
                if not target or target == '~':
                    new_dir = project_dir
                elif target == '..':
                    new_dir = cwd_path.parent
                else:
                    new_dir = (cwd_path / target).resolve()
                if str(new_dir).startswith(str(project_dir)) and new_dir.is_dir():
                    try:
                        rel = str(new_dir.relative_to(project_dir))
                    except ValueError:
                        rel = '.'
                    yield f"data: {_json_stdlib.dumps({'done': True, 'returncode': 0, 'new_cwd': rel})}\n\n"
                else:
                    _cd_err = f'cd: {target}: No such directory\n'
                    yield f"data: {_json_stdlib.dumps({'line': _cd_err})}\n\n"
                    yield f"data: {_json_stdlib.dumps({'done': True, 'returncode': 1})}\n\n"
                return

            proc = subprocess.Popen(
                cmd_fixed, shell=True,
                cwd=str(cwd_path),
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, env=env, bufsize=1
            )
            for line in iter(proc.stdout.readline, ''):
                yield f"data: {_json_stdlib.dumps({'line': line})}\n\n"
            proc.wait()

            # pip install 성공 시 requirements.txt 자동 갱신
            is_pip_install = bool(_re.search(r'\bpip\b.*\binstall\b', cmd_fixed))
            if is_pip_install and proc.returncode == 0:
                try:
                    freeze_result = subprocess.run(
                        [venv_pip, 'freeze'],
                        capture_output=True, text=True, env=env
                    )
                    if freeze_result.returncode == 0:
                        (project_dir / 'requirements.txt').write_text(
                            freeze_result.stdout, encoding='utf-8')
                        _save_msg = _json_stdlib.dumps({'line': '\n[자동저장] requirements.txt 업데이트됨\n'})
                        yield f"data: {_save_msg}\n\n"
                except Exception:
                    pass

            try:
                rel_cwd = str(cwd_path.relative_to(project_dir))
            except ValueError:
                rel_cwd = '.'
            yield f"data: {_json_stdlib.dumps({'done': True, 'returncode': proc.returncode, 'cwd': rel_cwd})}\n\n"
        except Exception as e:
            yield f"data: {_json_stdlib.dumps({'error': str(e), 'done': True})}\n\n"

    resp = StreamingHttpResponse(stream_cmd(), content_type='text/event-stream')
    resp['Cache-Control'] = 'no-cache'
    resp['X-Accel-Buffering'] = 'no'
    return resp


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



@login_required
def ai_webdev_file_download(request, pk):
    """개별 파일 다운로드"""
    import mimetypes
    from django.http import FileResponse
    from blog.models import AiWebProject
    project = get_object_or_404(AiWebProject, pk=pk, user=request.user)
    project_dir = _get_project_dir(project.pk)
    path = request.GET.get('path', '').lstrip('/')
    if not path:
        return JsonResponse({'error': '경로 필요'}, status=400)
    target = (project_dir / path).resolve()
    if not str(target).startswith(str(project_dir.resolve())):
        return HttpResponse('허용되지 않은 경로', status=403)
    if not target.exists() or not target.is_file():
        return HttpResponse('파일 없음', status=404)
    mime, _ = mimetypes.guess_type(str(target))
    mime = mime or 'application/octet-stream'
    response = FileResponse(open(target, 'rb'), content_type=mime)
    response['Content-Disposition'] = f'attachment; filename="{target.name}"'
    logger.info(f'[WebDev] 파일 다운로드: pk={pk} path={path}')
    return response


@login_required
def ai_webdev_zip_download(request, pk):
    """전체 프로젝트 ZIP 다운로드"""
    import zipfile
    import io
    from blog.models import AiWebProject
    project = get_object_or_404(AiWebProject, pk=pk, user=request.user)
    project_dir = _get_project_dir(project.pk)
    if not project_dir.exists():
        return HttpResponse('프로젝트 파일 없음', status=404)

    buf = io.BytesIO()
    file_count = 0
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(project_dir.rglob('*')):
            if file_path.is_file():
                # 숨김파일 / __pycache__ 제외
                parts = file_path.relative_to(project_dir).parts
                if any(p.startswith('.') or p == '__pycache__' for p in parts):
                    continue
                arcname = str(file_path.relative_to(project_dir))
                zf.write(file_path, arcname)
                file_count += 1
    buf.seek(0)
    safe_name = ''.join(c if c.isalnum() or c in '-_' else '_' for c in project.name)
    logger.info(f'[WebDev] ZIP 다운로드: pk={pk} name={project.name} files={file_count}')
    response = HttpResponse(buf.read(), content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename="{safe_name}.zip"'
    return response

@login_required
def ai_webdev_proxy(request, pk, port, path=''):
    """
    실행 중인 개발 서버 포트를 Django 백엔드에서 프록시
    iframe 차단 없이 미리보기 가능
    """
    import urllib.request as _urllib_req
    import urllib.error as _urllib_err
    from blog.models import AiWebProject

    project = get_object_or_404(AiWebProject, pk=pk, user=request.user)

    # 허용 포트 범위 제한 (3000~9999)
    try:
        port = int(port)
        if not (3000 <= port <= 9999):
            return HttpResponse('허용되지 않는 포트', status=400)
    except (ValueError, TypeError):
        return HttpResponse('잘못된 포트', status=400)

    qs = request.GET.urlencode()
    url = f'http://127.0.0.1:{port}/{path}' + (f'?{qs}' if qs else '')

    try:
        req = _urllib_req.Request(url)
        req.add_header('Accept', request.META.get('HTTP_ACCEPT', '*/*'))
        req.add_header('Accept-Language', 'ko,en')

        with _urllib_req.urlopen(req, timeout=8) as resp:
            body = resp.read()
            ct = resp.getheader('Content-Type', 'text/html; charset=utf-8')

            # HTML이면 base 태그 주입 (상대 경로 처리)
            if 'text/html' in ct:
                try:
                    text = body.decode('utf-8', errors='replace')
                    base_url = f'/blog/ai-webdev/{pk}/proxy/{port}/'
                    base_tag = f'<base href="{base_url}">'
                    # X-Frame-Options 우회를 위해 meta 태그도 주입
                    inject = base_tag + f'<script>window.__PROXY_BASE__="{base_url}";</script>'
                    if '<head>' in text:
                        text = text.replace('<head>', f'<head>{inject}', 1)
                    elif '<html' in text:
                        idx = text.find('>', text.find('<html')) + 1
                        text = text[:idx] + f'<head>{inject}</head>' + text[idx:]
                    else:
                        text = inject + text
                    body = text.encode('utf-8')
                except Exception:
                    pass

            http_resp = HttpResponse(body, content_type=ct)
            http_resp['X-Frame-Options'] = 'SAMEORIGIN'
            http_resp['Cache-Control'] = 'no-cache'
            return http_resp

    except _urllib_err.URLError as e:
        # 서버 아직 안 뜸
        html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<style>
body{{font-family:sans-serif;background:#0d1117;color:#8b949e;
     display:flex;flex-direction:column;align-items:center;justify-content:center;
     height:100vh;margin:0;text-align:center;}}
.icon{{font-size:3rem;margin-bottom:12px;}}
p{{font-size:.9rem;max-width:300px;line-height:1.6;}}
button{{margin-top:16px;background:#1f6feb;color:#fff;border:none;
        border-radius:8px;padding:8px 20px;cursor:pointer;font-size:.9rem;}}
</style></head><body>
<div class="icon">🔌</div>
<p>포트 <strong style="color:#58a6ff;">{port}</strong>에서 실행 중인 서버가 없습니다.<br>
터미널에서 서버를 먼저 실행해주세요.</p>
<p style="font-size:.8rem;color:#484f58;">{str(e)[:80]}</p>
<button onclick="location.reload()">🔄 다시 시도</button>
</body></html>"""
        return HttpResponse(html, content_type='text/html; charset=utf-8', status=502)
    except Exception as e:
        return HttpResponse(f'프록시 오류: {str(e)[:200]}', status=500)



# ═══════════════════════════════════════════════════════════════
#  게시판 + 건의함  (Board & Suggestion)
# ═══════════════════════════════════════════════════════════════

# ── 악성글 키워드 필터 ──────────────────────────────────────────
_TOXIC_PATTERNS = [
    # 욕설/혐오
    r'씨발|시발|ㅅㅂ|개새|개년|병신|좆|보지|자지|미친|존나|ㅈㄴ|ㄱㅅ끼|창녀|걸레년|쓰레기|찐따',
    # 폭력/협박
    r'죽여|죽어라|살인|칼로|폭탄|폭발물|테러',
    # 스팸/광고
    r'대출\s*상담|불법\s*도박|카지노\s*추천|성인\s*사이트|클릭\s*하세요.*돈',
    # 개인정보 유도
    r'계좌번호.*알려|주민번호.*입력|비밀번호.*보내',
]
import re as _re_board
_TOXIC_RE = _re_board.compile('|'.join(_TOXIC_PATTERNS), _re_board.IGNORECASE)

def _detect_toxic(text: str):
    """악성/부적절 텍스트 감지. (이유, bool) 반환"""
    if not text:
        return None, False
    m = _TOXIC_RE.search(text)
    if m:
        return f"부적절한 표현이 포함되어 있습니다: '{m.group()}'", True
    # 반복 문자 스팸 감지 (같은 문자 10번 이상)
    if _re_board.search(r'(.)\1{9,}', text):
        return "스팸성 반복 문자가 감지되었습니다.", True
    # 외부 링크 과다 (5개 이상)
    if len(_re_board.findall(r'https?://', text)) >= 5:
        return "지나치게 많은 외부 링크가 포함되어 있습니다.", True
    return None, False

def _send_notification(recipient, sender, ntype, message, url=''):
    """알림 생성 헬퍼"""
    from blog.models import Notification as _Notif
    _Notif.objects.create(
        recipient=recipient,
        sender=sender,
        ntype=ntype,
        message=message,
        url=url,
    )

# ── 게시판 목록 ─────────────────────────────────────────────────
def board_list(request):
    from blog.models import Board as _Board
    boards = _Board.objects.filter(is_active=True)
    return render(request, 'blog/board_list.html', {'boards': boards})

# ── 게시판 상세(글 목록) ────────────────────────────────────────
def board_detail(request, slug):
    from blog.models import Board as _Board, BoardPost as _BP
    board = get_object_or_404(_Board, slug=slug, is_active=True)
    q = request.GET.get('q', '').strip()
    posts = _BP.objects.filter(board=board, is_blocked=False)
    if q:
        posts = posts.filter(
            _Q(title__icontains=q) | _Q(content__icontains=q)
        )
    from django.core.paginator import Paginator
    paginator = Paginator(posts, 20)
    page_obj = paginator.get_page(request.GET.get('page', 1))
    return render(request, 'blog/board_detail.html', {
        'board': board,
        'page_obj': page_obj,
        'q': q,
    })

# ── 게시글 상세 ─────────────────────────────────────────────────
def board_post_detail(request, board_slug, pk):
    from blog.models import Board as _Board, BoardPost as _BP, BoardComment as _BC, BoardPostLike as _BL
    from django.db.models import F as _F
    board = get_object_or_404(_Board, slug=board_slug)
    post = get_object_or_404(_BP, pk=pk, board=board, is_blocked=False)
    # 조회수
    _BP.objects.filter(pk=pk).update(views=_F('views') + 1)
    post.refresh_from_db(fields=['views'])
    comments = _BC.objects.filter(post=post, is_blocked=False, parent=None).prefetch_related('replies')
    liked = False
    if request.user.is_authenticated:
        liked = _BL.objects.filter(post=post, user=request.user).exists()
    return render(request, 'blog/board_post_detail.html', {
        'board': board,
        'post': post,
        'comments': comments,
        'liked': liked,
        'like_count': post.likes.count(),
    })

# ── 게시글 작성 ─────────────────────────────────────────────────
@login_required
def board_post_create(request, slug):
    from blog.models import Board as _Board, BoardPost as _BP
    board = get_object_or_404(_Board, slug=slug, is_active=True)
    if request.method == 'POST':
        title   = request.POST.get('title', '').strip()
        content = request.POST.get('content', '').strip()
        if not title or not content:
            return render(request, 'blog/board_post_form.html', {
                'board': board, 'error': '제목과 내용을 모두 입력하세요.', 'action': 'create',
            })
        # ── 악성글 감지 ──
        reason, is_toxic = _detect_toxic(title + ' ' + content)
        if is_toxic:
            return render(request, 'blog/board_post_form.html', {
                'board': board,
                'error': f'🚫 게시글을 등록할 수 없습니다.\n{reason}\n\n커뮤니티 규칙에 맞는 건전한 글을 작성해 주세요.',
                'action': 'create',
                'title': title,
                'content': content,
            })
        _BP.objects.create(board=board, author=request.user, title=title, content=content)
        messages.success(request, '✅ 게시글이 등록되었습니다.')
        return redirect('blog:board_detail', slug=slug)
    return render(request, 'blog/board_post_form.html', {'board': board, 'action': 'create'})

# ── 게시글 수정 ─────────────────────────────────────────────────
@login_required
def board_post_edit(request, board_slug, pk):
    from blog.models import Board as _Board, BoardPost as _BP
    board = get_object_or_404(_Board, slug=board_slug)
    post = get_object_or_404(_BP, pk=pk, board=board)
    if post.author != request.user and not request.user.is_staff:
        messages.error(request, '수정 권한이 없습니다.')
        return redirect('blog:board_post_detail', board_slug=board_slug, pk=pk)
    if request.method == 'POST':
        title   = request.POST.get('title', '').strip()
        content = request.POST.get('content', '').strip()
        reason, is_toxic = _detect_toxic(title + ' ' + content)
        if is_toxic:
            return render(request, 'blog/board_post_form.html', {
                'board': board, 'post': post,
                'error': f'🚫 {reason}', 'action': 'edit',
                'title': title, 'content': content,
            })
        post.title = title
        post.content = content
        post.save()
        messages.success(request, '✅ 게시글이 수정되었습니다.')
        return redirect('blog:board_post_detail', board_slug=board_slug, pk=pk)
    return render(request, 'blog/board_post_form.html', {
        'board': board, 'post': post,
        'action': 'edit', 'title': post.title, 'content': post.content,
    })

# ── 게시글 삭제 ─────────────────────────────────────────────────
@login_required
def board_post_delete(request, board_slug, pk):
    from blog.models import Board as _Board, BoardPost as _BP
    board = get_object_or_404(_Board, slug=board_slug)
    post = get_object_or_404(_BP, pk=pk, board=board)
    if post.author != request.user and not request.user.is_staff:
        messages.error(request, '삭제 권한이 없습니다.')
        return redirect('blog:board_post_detail', board_slug=board_slug, pk=pk)
    if request.method == 'POST':
        post.delete()
        messages.success(request, '게시글이 삭제되었습니다.')
        return redirect('blog:board_detail', slug=board_slug)
    return render(request, 'blog/board_post_delete_confirm.html', {'post': post, 'board': board})

# ── 댓글 작성 (AJAX) ───────────────────────────────────────────
@login_required
@require_POST
def board_comment_create(request, board_slug, pk):
    from blog.models import Board as _Board, BoardPost as _BP, BoardComment as _BC
    board = get_object_or_404(_Board, slug=board_slug)
    post  = get_object_or_404(_BP, pk=pk, board=board, is_blocked=False)
    try:
        body    = _json_mod.loads(request.body)
        content = body.get('content', '').strip()
        parent_id = body.get('parent_id')
    except Exception:
        return JsonResponse({'error': '잘못된 요청'}, status=400)
    if not content:
        return JsonResponse({'error': '내용을 입력하세요.'}, status=400)
    reason, is_toxic = _detect_toxic(content)
    if is_toxic:
        return JsonResponse({'error': f'🚫 {reason}'}, status=400)
    parent = None
    if parent_id:
        try:
            parent = _BC.objects.get(pk=parent_id, post=post)
        except _BC.DoesNotExist:
            pass
    comment = _BC.objects.create(post=post, author=request.user, content=content, parent=parent)
    # 게시글 작성자에게 알림 (자신 댓글 제외)
    if post.author != request.user:
        _send_notification(
            recipient=post.author,
            sender=request.user,
            ntype='comment',
            message=f'{request.user.username}님이 "{post.title}"에 댓글을 달았습니다.',
            url=post.get_absolute_url(),
        )
    return JsonResponse({
        'ok': True,
        'comment_id': comment.pk,
        'author': request.user.username,
        'content': comment.content,
        'created_at': comment.created_at.strftime('%Y.%m.%d %H:%M'),
        'parent_id': parent.pk if parent else None,
    })

# ── 댓글 삭제 (AJAX) ───────────────────────────────────────────
@login_required
@require_POST
def board_comment_delete(request, comment_pk):
    from blog.models import BoardComment as _BC
    comment = get_object_or_404(_BC, pk=comment_pk)
    if comment.author != request.user and not request.user.is_staff:
        return JsonResponse({'error': '권한 없음'}, status=403)
    comment.delete()
    return JsonResponse({'ok': True})

# ── 게시글 좋아요 (AJAX) ───────────────────────────────────────
@login_required
@require_POST
def board_post_like(request, board_slug, pk):
    from blog.models import Board as _Board, BoardPost as _BP, BoardPostLike as _BL
    post = get_object_or_404(_BP, pk=pk, board__slug=board_slug, is_blocked=False)
    obj, created = _BL.objects.get_or_create(post=post, user=request.user)
    if not created:
        obj.delete()
        liked = False
    else:
        liked = True
    return JsonResponse({'liked': liked, 'count': post.likes.count()})

# ── 악성글 실시간 검사 API (타이핑 중 미리 확인) ────────────────
@require_POST
def board_check_toxic(request):
    try:
        body = _json_mod.loads(request.body)
        text = body.get('text', '')
    except Exception:
        return JsonResponse({'ok': True})
    reason, is_toxic = _detect_toxic(text)
    return JsonResponse({'toxic': is_toxic, 'reason': reason or ''})

# ── 건의함 목록/제출 ───────────────────────────────────────────
@login_required
def suggestion_list(request):
    from blog.models import Suggestion as _Sugg
    my_suggestions = _Sugg.objects.filter(author=request.user)
    return render(request, 'blog/suggestion_list.html', {'suggestions': my_suggestions})

@login_required
def suggestion_create(request):
    from blog.models import Suggestion as _Sugg
    if request.method == 'POST':
        category    = request.POST.get('category', 'other')
        title       = request.POST.get('title', '').strip()
        content     = request.POST.get('content', '').strip()
        is_anonymous = request.POST.get('is_anonymous') == 'on'
        if not title or not content:
            return render(request, 'blog/suggestion_form.html', {
                'error': '제목과 내용을 입력하세요.',
                'categories': _Sugg.CATEGORY_CHOICES,
            })
        sugg = _Sugg.objects.create(
            author=request.user,
            category=category,
            title=title,
            content=content,
            is_anonymous=is_anonymous,
        )
        # ── 관리자 전체에게 알림 전송 ──
        from django.contrib.auth import get_user_model as _gum
        _User = _gum()
        admins = _User.objects.filter(is_staff=True)
        display_name = '익명' if is_anonymous else request.user.username
        for admin in admins:
            _send_notification(
                recipient=admin,
                sender=None if is_anonymous else request.user,
                ntype='mention',
                message=f'📬 새 건의사항: [{sugg.get_category_display()}] {title} (by {display_name})',
                url=f'/blog/suggestions/admin/{sugg.pk}/',
            )
        messages.success(request, '✅ 건의사항이 접수되었습니다. 관리자가 검토 후 답변드립니다.')
        return redirect('blog:suggestion_list')
    from blog.models import Suggestion as _Sugg2
    return render(request, 'blog/suggestion_form.html', {'categories': _Sugg2.CATEGORY_CHOICES})

# ── 건의함 관리자 목록 ──────────────────────────────────────────
@login_required
def suggestion_admin_list(request):
    from blog.models import Suggestion as _Sugg
    if not request.user.is_staff:
        return render(request, 'blog/suggestion_admin_list.html', {
            'suggestions': _Sugg.objects.none(),
            'status_choices': _Sugg.STATUS_CHOICES,
            'status_filter': '',
            'access_denied': True,
        })
    status_filter = request.GET.get('status', '')
    suggestions = _Sugg.objects.all()
    if status_filter:
        suggestions = suggestions.filter(status=status_filter)
    return render(request, 'blog/suggestion_admin_list.html', {
        'suggestions': suggestions,
        'status_choices': _Sugg.STATUS_CHOICES,
        'status_filter': status_filter,
        'access_denied': False,
    })

# ── 건의함 관리자 상세/답변 ─────────────────────────────────────
@staff_member_required
def suggestion_admin_detail(request, pk):
    from blog.models import Suggestion as _Sugg
    sugg = get_object_or_404(_Sugg, pk=pk)
    if request.method == 'POST':
        sugg.status      = request.POST.get('status', sugg.status)
        sugg.admin_reply = request.POST.get('admin_reply', '').strip()
        sugg.save()
        # 작성자에게 알림
        _send_notification(
            recipient=sugg.author,
            sender=request.user,
            ntype='mention',
            message=f'✅ 건의사항 "{sugg.title}"에 관리자 답변이 등록되었습니다.',
            url=f'/blog/suggestions/',
        )
        messages.success(request, '답변이 저장되었습니다.')
        return redirect('blog:suggestion_admin_detail', pk=pk)
    return render(request, 'blog/suggestion_admin_detail.html', {
        'sugg': sugg,
        'status_choices': _Sugg.STATUS_CHOICES,
    })



# ════════════════════════════════════════════════════════════════
#  가상 OS (Virtual OS) 뷰
# ════════════════════════════════════════════════════════════════

import os as _vos_os
import json as _vos_json

VIRT_OS_UPLOAD_DIR = '/tmp/syblog_vos_iso'


@login_required
def virtual_os_index(request):
    """가상 OS 메인 페이지 — 세션 목록"""
    from blog.models import VirtualOSSession
    sessions = VirtualOSSession.objects.filter(user=request.user)
    return render(request, 'blog/virtual_os.html', {'sessions': sessions})



@login_required
def virtual_os_session(request, pk=None):
    """가상 OS 에뮬레이터 페이지 — 신규 또는 기존 세션"""
    from blog.models import VirtualOSSession
    if pk:
        sess = get_object_or_404(VirtualOSSession, pk=pk, user=request.user)
        sess.boot_count += 1
        sess.save(update_fields=['boot_count', 'last_used'])
    else:
        sess = VirtualOSSession.objects.create(user=request.user)
    return render(request, 'blog/virtual_os_emulator.html', {'session': sess})

@login_required
def virtual_os_api_session(request, pk):
    """세션 설정 조회/수정 API"""
    from blog.models import VirtualOSSession
    sess = get_object_or_404(VirtualOSSession, pk=pk, user=request.user)

    if request.method == 'GET':
        return JsonResponse({
            'id': sess.pk,
            'name': sess.name,
            'cpu_id': sess.cpu_id,
            'ram_mb': sess.ram_mb,
            'vhd_size_gb': sess.vhd_size_gb,
            'has_state': bool(sess.state_data),
            'has_vhd': bool(sess.vhd_data),
            'iso_name': sess.iso_name,
            'boot_count': sess.boot_count,
        })

    if request.method == 'POST':
        try:
            body = _vos_json.loads(request.body)
        except Exception:
            return JsonResponse({'error': '잘못된 요청'}, status=400)
        for field in ['name', 'cpu_id', 'ram_mb', 'vhd_size_gb']:
            if field in body:
                setattr(sess, field, body[field])
        sess.save()
        return JsonResponse({'ok': True})

    return JsonResponse({'error': 'method not allowed'}, status=405)


@login_required
def virtual_os_save_state(request, pk):
    """에뮬레이터 상태 저장 (state ArrayBuffer → DB)"""
    from blog.models import VirtualOSSession
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)
    sess = get_object_or_404(VirtualOSSession, pk=pk, user=request.user)
    try:
        data = request.body  # raw binary
        # 최대 256MB 제한
        if len(data) > 256 * 1024 * 1024:
            return JsonResponse({'error': '상태 파일이 너무 큽니다 (최대 256MB)'}, status=413)
        sess.state_data = data
        sess.save(update_fields=['state_data', 'last_used'])
        return JsonResponse({'ok': True, 'size_mb': round(len(data) / 1024 / 1024, 2)})
    except Exception as e:
        return JsonResponse({'error': str(e)[:100]}, status=500)


@login_required
def virtual_os_load_state(request, pk):
    """저장된 상태 로드 (DB → binary response)"""
    from blog.models import VirtualOSSession
    sess = get_object_or_404(VirtualOSSession, pk=pk, user=request.user)
    if not sess.state_data:
        return JsonResponse({'error': '저장된 상태가 없습니다'}, status=404)
    from django.http import HttpResponse
    resp = HttpResponse(bytes(sess.state_data), content_type='application/octet-stream')
    resp['Content-Length'] = len(sess.state_data)
    return resp


@login_required
def virtual_os_save_vhd(request, pk):
    """가상 하드드라이브 데이터 저장 (JSON)"""
    from blog.models import VirtualOSSession
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)
    sess = get_object_or_404(VirtualOSSession, pk=pk, user=request.user)
    try:
        body = _vos_json.loads(request.body)
        vhd_json = body.get('vhd_data', '')
        if len(vhd_json) > 128 * 1024 * 1024:
            return JsonResponse({'error': 'VHD 데이터가 너무 큽니다'}, status=413)
        sess.vhd_data = vhd_json
        sess.save(update_fields=['vhd_data', 'last_used'])
        return JsonResponse({'ok': True})
    except Exception as e:
        return JsonResponse({'error': str(e)[:100]}, status=500)


@login_required
def virtual_os_upload_iso(request, pk):
    """ISO 파일 업로드"""
    from blog.models import VirtualOSSession
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)
    sess = get_object_or_404(VirtualOSSession, pk=pk, user=request.user)
    iso_file = request.FILES.get('iso')
    if not iso_file:
        return JsonResponse({'error': 'ISO 파일이 없습니다'}, status=400)
    # 최대 2GB
    if iso_file.size > 2 * 1024 * 1024 * 1024:
        return JsonResponse({'error': 'ISO 파일은 최대 2GB까지 지원합니다'}, status=413)

    upload_dir = _vos_os.path.join(VIRT_OS_UPLOAD_DIR, str(request.user.pk))
    _vos_os.makedirs(upload_dir, exist_ok=True)
    save_path = _vos_os.path.join(upload_dir, iso_file.name)

    try:
        with open(save_path, 'wb') as f:
            for chunk in iso_file.chunks(chunk_size=8 * 1024 * 1024):
                f.write(chunk)
        sess.iso_path = save_path
        sess.iso_name = iso_file.name
        sess.save(update_fields=['iso_path', 'iso_name', 'last_used'])
        return JsonResponse({
            'ok': True,
            'name': iso_file.name,
            'size_mb': round(iso_file.size / 1024 / 1024, 1),
        })
    except Exception as e:
        return JsonResponse({'error': str(e)[:100]}, status=500)


@login_required
def virtual_os_stream_iso(request, pk):
    """저장된 ISO 파일을 스트리밍 (v86 cdrom url로 사용)"""
    from blog.models import VirtualOSSession
    sess = get_object_or_404(VirtualOSSession, pk=pk, user=request.user)
    if not sess.iso_path or not _vos_os.path.exists(sess.iso_path):
        from django.http import Http404
        raise Http404('ISO 파일을 찾을 수 없습니다')
    from django.http import FileResponse
    return FileResponse(open(sess.iso_path, 'rb'),
                        content_type='application/octet-stream',
                        filename=sess.iso_name or 'disk.iso')


@login_required
def virtual_os_delete_session(request, pk):
    """세션 삭제"""
    from blog.models import VirtualOSSession
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)
    sess = get_object_or_404(VirtualOSSession, pk=pk, user=request.user)
    if sess.iso_path and _vos_os.path.exists(sess.iso_path):
        try:
            _vos_os.remove(sess.iso_path)
        except Exception:
            pass
    sess.delete()
    from django.shortcuts import redirect
    return redirect('blog:virtual_os_index')
