# coding=utf-8
import logging

from django.contrib import messages
from django.contrib.auth import get_user_model

from ...models import Tag

logger = logging.getLogger(__name__)


def _split_csv(value):
    return [item.strip() for item in value.split(',') if item.strip()]


def _unique_in_order(values):
    seen = set()
    unique_values = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique_values.append(value)
    return unique_values


def _tags_from_post(post_data):
    tag_names = _unique_in_order(_split_csv(post_data.get('custom_tags', '')))
    tags = []
    for name in tag_names:
        tag, _ = Tag.objects.get_or_create(name=name)
        tags.append(tag)
    return tags


def _collaborators_from_post(post_data, request):
    usernames = _unique_in_order(_split_csv(post_data.get('collaborators', '')))
    if not usernames:
        return []

    users_by_username = get_user_model().objects.in_bulk(usernames, field_name='username')
    collaborators = []
    missing_usernames = []

    for username in usernames:
        user = users_by_username.get(username)
        if user:
            collaborators.append(user)
        else:
            missing_usernames.append(username)
            messages.error(request, f"用戶 「{username}」 不存在.")

    if missing_usernames:
        logger.warning(
            "Skipped missing collaborators for itinerary form: %s",
            ', '.join(missing_usernames),
        )

    return collaborators


def save_itinerary_relations_from_post(itinerary, post_data, request):
    tags = _tags_from_post(post_data)
    collaborators = _collaborators_from_post(post_data, request)

    itinerary.tags.set(tags)
    itinerary.collaborators.set(collaborators)

    logger.info(
        "Saved itinerary %s relations with %s tags and %s collaborators.",
        itinerary.id,
        len(tags),
        len(collaborators),
    )
