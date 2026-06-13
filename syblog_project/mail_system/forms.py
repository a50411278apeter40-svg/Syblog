from django import forms
from django.contrib.auth.models import User


class ComposeMailForm(forms.Form):
    recipient_username = forms.CharField(
        max_length=150,
        label='받는 사람',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '사용자명 입력 또는 검색',
            'autocomplete': 'off',
        })
    )
    subject = forms.CharField(
        max_length=200,
        label='제목',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '메일 제목'
        })
    )
    body = forms.CharField(
        label='내용',
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 10,
            'placeholder': '내용을 입력하세요'
        })
    )

    def clean_recipient_username(self):
        return self.cleaned_data['recipient_username'].strip()

    def clean_subject(self):
        return self.cleaned_data['subject'].strip()

    def clean_body(self):
        return self.cleaned_data['body'].strip()
