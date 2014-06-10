# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.core.cache import cache
from django.db import models
from django.db.models import Count, F, Q

from .settings import (INBOX_CACHE_KEY_PATTERN,
                       UNREAD_CACHE_KEY_PATTERN,
                       PARTICIPANTS_CACHE_KEY_PATTERN)


class ConversationManager(models.Manager):

    def for_participants(self, participants):
        """Query a specific conversation for a specified list of participants.
        If possible, retrieve it from cache (no invalidation required) as a
        unique set of participants can have only one conversation."""
        user_ids = sorted(user.pk for user in participants)
        str_ids = '_'.join(str(uid) for uid in user_ids)
        key = PARTICIPANTS_CACHE_KEY_PATTERN.format(str_ids)
        conversations = cache.get(key)

        if conversations:
            # retrieved from cache
            return conversations

        # not found in cache, do the query
        annotation = dict(participant_count=Count('participations'))
        conversations = self.all().annotate(**annotation)

        for user in participants:
            condition = dict(participations__user=user)
            conversations = conversations.filter(**condition)

        qs = conversations.filter(participant_count=len(participants))
        cache.set(key, qs)
        return qs


class ParticipationManager(models.Manager):

    def inbox_for(self, user):
        """Return a QuerySet of participations for a specific user, which
        essentially represents that user's inbox."""
        key = INBOX_CACHE_KEY_PATTERN.format(user.pk)
        cached_qs = cache.get(key)

        if cached_qs:
            return cached_qs
        else:
            qs = self.filter(deleted_at__isnull=True, user=user)
            cache.set(key, qs)
            return qs

    def unread_for(self, user):
        """Return a users inbox, but filtered only for those conversations that
        have not been read either completely or partially."""
        key = UNREAD_CACHE_KEY_PATTERN.format(user.pk)
        cached_qs = cache.get(key)

        if cached_qs:
            return cached_qs
        else:
            qs = self.inbox_for(user).filter(
                Q(read_at__isnull=True) |
                Q(read_at__lt=F('conversation__latest_message__sent_at'))
            )
            cache.set(key, qs)
            return qs
