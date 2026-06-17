import sys
import re

with open('/app/syblog_project/blog/views.py', 'r') as f:
    content = f.read()

# 1. Add SeriesDelete and search_view
append_code = """
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
"""

with open('/app/syblog_project/blog/views.py', 'a') as f:
    f.write("\n" + append_code)

print("Appended views successfully")
