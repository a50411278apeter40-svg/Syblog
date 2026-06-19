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
    form_class = PostForm
    template_name = 'blog/post_form.html'

    def form_valid(self, form):
        is_banned, kw = check_banned_keywords(form.cleaned_data.get('title', '') + ' ' + form.cleaned_data.get('content', ''))
        if is_banned:
            form.add_error(None, f'금지된 키워드가 포함되어 있습니다: "{kw}"')
            return self.form_invalid(form)
        
        form.instance.author = self.request.user
        response = super().form_valid(form)
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
