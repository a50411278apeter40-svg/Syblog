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
        fields = ['title', 'hook_text', 'content', 'head_image', 'file_upload', 'category', 'series', 'series_order']

class SeriesForm(forms.ModelForm):
    class Meta:
        model = Series
        fields = ['title', 'description', 'thumbnail']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }
