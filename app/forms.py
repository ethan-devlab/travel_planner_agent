# coding=utf-8
from django import forms
from .models import Itinerary, Expense
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.models import User


class ItineraryForm(forms.ModelForm):
    collaborators = forms.CharField(
        required=False,
        label="協作者",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '請輸入協作者帳戶 (用逗號分隔)'
        }))

    custom_tags = forms.CharField(
        required=False,
        label="標籤",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '如：韓國, 旅遊, 美食 (用逗號分隔)'
        }))

    class Meta:
        model = Itinerary
        fields = ['title', 'start_date', 'end_date', 'location', 'budget', 'description', 'is_public', 'status']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '請輸入行程標題'}),
            'start_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'end_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'location': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '請輸入地點或國家'}),
            'budget': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '請輸入預算'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': '請輸入行程描述'}),
            'is_public': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }
        labels = {
            'title': '行程標題',
            'start_date': '開始日期',
            'end_date': '結束日期',
            'budget': '預算金額',
            'description': '行程描述',
            'is_public': '是否公開',
            'location': '地點 / 國家',
            'status': '行程狀態',
        }


class RegisterForm(UserCreationForm):
    username = forms.CharField(
        max_length=24,
        required=True,
        label="帳戶",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '帳戶'}),
        error_messages={'required': '帳戶不能為空', 'max_length': '帳戶長度不能超過24個字元'},
        label_suffix=""  # clear colon
    )

    email = forms.EmailField(
        max_length=128,
        required=True,
        label="電子郵件",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '電子郵件'}),
        error_messages={'required': '電子郵件不能為空', 'max_length': '電子郵件長度不能超過128個字元'},
        label_suffix=""  # clear colon
    )

    password1 = forms.CharField(
        max_length=128,
        required=True,
        label="密碼",
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': '密碼'}),
        error_messages={'required': '密碼不能為空', 'max_length': '密碼長度不能超過128個字元'},
        label_suffix=""  # clear colon
    )

    password2 = forms.CharField(
        max_length=128,
        required=True,
        label="確認密碼",
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': '確認密碼'}),
        error_messages={'required': '確認密碼不能為空', 'max_length': '確認密碼長度不能超過128個字元'},
        label_suffix=""  # clear colon
    )

    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2']


class LoginForm(forms.Form):
    username = forms.CharField(
        max_length=24,
        required=True,
        label="帳戶",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '帳戶'}),
        error_messages={'required': '帳戶不能為空', 'max_length': '帳戶長度不能超過24個字元'},
        label_suffix=""  # clear colon
    )
    password = forms.CharField(
        max_length=128,
        required=True,
        label="密碼",
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': '密碼'}),
        error_messages={'required': '密碼不能為空', 'max_length': '密碼長度不能超過128個字元'},
        label_suffix=""  # clear colon
    )

class SearchForm(forms.Form):
    q = forms.CharField(
        required=False,
        label="關鍵字",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '輸入關鍵字'})
    )
    travel_method = forms.CharField(
        required=False, 
        label="旅遊方式",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '如步行、開車、搭飛機等'})
    )
    budget = forms.CharField(
        required=False, 
        label="預算",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '輸入預算'})
    )
    location = forms.CharField(
        required=False, 
        label="地點/國家",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '如台灣、韓國等'})
    )
    transport = forms.CharField(
        required=False, 
        label="交通",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '如地鐵、巴士等'})
    )
    start_date = forms.DateField(
        required=False, 
        label="開始日期", 
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    end_date = forms.DateField(
        required=False, 
        label="結束日期", 
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )


class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = ['expense_type', 'amount']
        widgets = {
            'expense_type': forms.Select(attrs={'class': 'form-select'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '支出金額'}),
        }
        labels = {
            'expense_type': '支出類型',
            'amount': '金額',
        }
