# -*- coding: utf-8 -*-
from django.db import models
from django.db.models import Count


class ConversationManager(models.Manager):

    def for_participants(self, participants):
        conversations = (self.all()
                             .annotate(participants=Count('participations')))

        for username in participants:
            condition = dict(participations__user__username=username)
            conversations = conversations.filter(**condition)

        return conversations.filter(participants=len(participants))


class ParticipationManager(models.Manager):

    def inbox_for(self, user):
        return self.filter(deleted_at__isnull=True, user=user)
