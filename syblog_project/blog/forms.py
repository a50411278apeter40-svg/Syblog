from django import forms
from .models import Comment, Post, Series

class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ['content']
        widgets = {
            'content': forms.Textarea(attrs={'rows': 3, 'placeholder': '댓글을 입력하세요...'}),
        }
        labels = {'content': ''}

class PostForm(forms.ModelForm):
    tags_str = forms.CharField(required=False, label='태그 (;로 구분)',
                               widget=forms.TextInput(attrs={'placeholder': 'tag1; tag2; tag3'}))
    class Meta:
        model = Post
        fields = ['title', 'hook_text', 'content', 'head_image', 'file_upload', 'url_embed', 'category', 'series', 'series_order']

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super(PostForm, self).__init__(*args, **kwargs)
        if user:
            self.fields['series'].queryset = Series.objects.filter(author=user).order_by('-created_at')

class PostFormWithSchedule(PostForm):
    """예약 게시 기능이 포함된 PostForm 확장"""
    publish_at = forms.DateTimeField(
        required=False,
        label='예약 게시 시각 (비우면 즉시 공개)',
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}),
        input_formats=['%Y-%m-%dT%H:%M'],
    )

class SeriesForm(forms.ModelForm):
    class Meta:
        model = Series
        fields = ['title', 'description', 'thumbnail']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }
