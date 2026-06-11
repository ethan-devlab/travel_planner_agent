import logging
import secrets
from dataclasses import dataclass
from datetime import timedelta

from django.contrib.auth import get_user_model, login, logout
from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import DemoSession

logger = logging.getLogger(__name__)

DEMO_ROLE = "demo_user"
DEMO_PERMISSIONS = "limited"
DEMO_SESSION_SECONDS = 2 * 60 * 60
DEMO_USERNAME_PREFIX = "demo_user_"
DEMO_AI_TOTAL_LIMIT = 10
DEMO_AI_WINDOW_LIMIT = 3
DEMO_AI_WINDOW_SECONDS = 60

DEMO_EXPIRED_CODE = "demo_session_expired"
DEMO_TOTAL_LIMIT_CODE = "demo_ai_total_limit"
DEMO_RATE_LIMIT_CODE = "demo_ai_rate_limit"
DEMO_SESSION_MISSING_CODE = "demo_session_missing"

DEMO_EXPIRED_MESSAGE = "Demo session has expired. Please start a new demo."
DEMO_TOTAL_LIMIT_MESSAGE = "Demo AI request limit reached for this demo session."
DEMO_RATE_LIMIT_MESSAGE = "Demo AI rate limit reached. Please wait before trying again."


@dataclass(frozen=True)
class DemoQuotaResult:
    allowed: bool
    error_code: str = ""
    message: str = ""
    status_code: int = 200
    retry_after: int = 0


def is_demo_user(user):
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    return get_demo_session(user) is not None


def get_demo_session(user):
    if user is None or not getattr(user, "is_authenticated", False):
        return None
    try:
        return user.demo_session
    except (DemoSession.DoesNotExist, ObjectDoesNotExist):
        return None


def create_demo_session(request):
    """Create an isolated temporary user and bind it to the current session."""
    _logout_existing_user(request)

    expires_at = timezone.now() + timedelta(seconds=DEMO_SESSION_SECONDS)
    user = _create_unique_demo_user()
    demo_session = DemoSession.objects.create(
        user=user,
        role=DEMO_ROLE,
        permissions=DEMO_PERMISSIONS,
        expires_at=expires_at,
    )

    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    request.session["demo_role"] = DEMO_ROLE
    request.session["demo_permissions"] = DEMO_PERMISSIONS
    request.session["demo_expires_at"] = expires_at.isoformat()
    request.session.set_expiry(timedelta(seconds=DEMO_SESSION_SECONDS))
    logger.info("Created demo session %s for temporary user %s.", demo_session.id, user.id)
    return demo_session


def end_demo_session(request):
    """Log out the current request and delete demo-owned data if applicable."""
    user = getattr(request, "user", None)
    demo_user_id = getattr(user, "id", None) if is_demo_user(user) else None
    logout(request)
    if demo_user_id:
        delete_demo_user_by_id(demo_user_id)


def expire_demo_session_if_needed(request):
    demo_session = get_demo_session(getattr(request, "user", None))
    if demo_session is None or demo_session.expires_at > timezone.now():
        return False

    logger.info("Expiring demo session %s for temporary user %s.", demo_session.id, demo_session.user_id)
    end_demo_session(request)
    return True


def cleanup_expired_demo_sessions(limit=50):
    """Delete expired demo users; owned itineraries and events cascade with them."""
    expired_sessions = list(
        DemoSession.objects.filter(expires_at__lte=timezone.now())
        .select_related("user")
        .order_by("expires_at")[:limit]
    )
    deleted_count = 0
    for demo_session in expired_sessions:
        user_id = demo_session.user_id
        demo_session.user.delete()
        deleted_count += 1
        logger.info("Cleaned expired demo session %s for temporary user %s.", demo_session.id, user_id)
    return deleted_count


def delete_demo_user_by_id(user_id):
    user_model = get_user_model()
    deleted_count, _ = user_model.objects.filter(id=user_id, demo_session__isnull=False).delete()
    if deleted_count:
        logger.info("Deleted temporary demo user %s and related data.", user_id)
    return deleted_count


def consume_demo_ai_quota(user):
    """Consume one AI request for demo users; normal users are always allowed."""
    if not is_demo_user(user):
        return DemoQuotaResult(allowed=True)

    with transaction.atomic():
        try:
            demo_session = DemoSession.objects.select_for_update().get(user=user)
        except DemoSession.DoesNotExist:
            return DemoQuotaResult(
                allowed=False,
                error_code=DEMO_SESSION_MISSING_CODE,
                message=DEMO_EXPIRED_MESSAGE,
                status_code=403,
            )

        now = timezone.now()
        if demo_session.expires_at <= now:
            return DemoQuotaResult(
                allowed=False,
                error_code=DEMO_EXPIRED_CODE,
                message=DEMO_EXPIRED_MESSAGE,
                status_code=403,
            )

        if demo_session.ai_request_count >= DEMO_AI_TOTAL_LIMIT:
            logger.warning("Demo session %s hit the total AI request limit.", demo_session.id)
            return DemoQuotaResult(
                allowed=False,
                error_code=DEMO_TOTAL_LIMIT_CODE,
                message=DEMO_TOTAL_LIMIT_MESSAGE,
                status_code=429,
            )

        window_start = demo_session.minute_window_started_at
        if window_start is None or (now - window_start).total_seconds() >= DEMO_AI_WINDOW_SECONDS:
            window_start = now
            demo_session.minute_window_started_at = window_start
            demo_session.minute_request_count = 0

        if demo_session.minute_request_count >= DEMO_AI_WINDOW_LIMIT:
            elapsed = int((now - window_start).total_seconds())
            retry_after = max(1, DEMO_AI_WINDOW_SECONDS - elapsed)
            logger.warning("Demo session %s hit the per-minute AI request limit.", demo_session.id)
            return DemoQuotaResult(
                allowed=False,
                error_code=DEMO_RATE_LIMIT_CODE,
                message=DEMO_RATE_LIMIT_MESSAGE,
                status_code=429,
                retry_after=retry_after,
            )

        demo_session.ai_request_count += 1
        demo_session.minute_request_count += 1
        demo_session.save(update_fields=[
            "ai_request_count",
            "minute_window_started_at",
            "minute_request_count",
            "updated_at",
        ])

    return DemoQuotaResult(allowed=True)


def _logout_existing_user(request):
    user = getattr(request, "user", None)
    if not getattr(user, "is_authenticated", False):
        return
    end_demo_session(request) if is_demo_user(user) else logout(request)


def _create_unique_demo_user():
    user_model = get_user_model()
    for _ in range(8):
        username = f"{DEMO_USERNAME_PREFIX}{secrets.token_hex(6)}"
        user = user_model(
            username=username,
            email=f"{username}@demo.local",
            first_name="Demo",
            last_name="User",
            is_staff=False,
            is_superuser=False,
        )
        user.set_unusable_password()
        try:
            user.save()
        except IntegrityError:
            continue
        logger.debug("Created temporary demo user with username length %s.", len(username))
        return user
    raise RuntimeError("Could not create a unique demo user.")
