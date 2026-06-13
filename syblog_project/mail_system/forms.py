from django import forms

class ComposeMailForm(forms.Form):
    recipient_username = forms.CharField(
        max_length=150,
        label='받는 사람 (username)',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '사용자명 입력'})
    )
    subject = forms.CharField(
        max_length=200,
        label='제목',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '제목'})
    )
    body = forms.CharField(
        label='내용',
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 8, 'placeholder': '내용을 입력하세요'})
    )
