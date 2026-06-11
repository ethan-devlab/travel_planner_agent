# coding=utf-8

from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login, logout, authenticate
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from django.shortcuts import render, redirect
import logging

from ...demo import create_demo_session, end_demo_session, is_demo_user
from ...forms import LoginForm, RegisterForm

logger = logging.getLogger(__name__)


@require_http_methods(["GET", "POST"])
def register(request):
    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("search")
        else:
            messages.error(request, "註冊失敗，請檢查輸入的資料是否正確。")

    else:
        form = RegisterForm()
    return render(request, "auth/register.html", {"form": form})


@require_http_methods(["GET", "POST"])
def login_view(request):
    if request.method == "POST":
        form = LoginForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data.get("username")
            password = form.cleaned_data.get("password")
            user = authenticate(request, username=username, password=password)
            print(f"Attempting to log in user: {username}")
            if user is not None:
                login(request, user)
                return redirect("search")
            messages.error(request, "帳戶或密碼錯誤，請再試一次。")
    else:
        form = LoginForm()
    return render(request, "auth/login.html", {"form": form})


@require_http_methods(["GET"])
def demo_login_view(request):
    demo_session = create_demo_session(request)
    logger.info("Started demo login flow for demo session %s.", demo_session.id)
    return redirect("planner_agent")


def logout_view(request):
    if is_demo_user(request.user):
        end_demo_session(request)
    else:
        logout(request)
    return redirect("search")
