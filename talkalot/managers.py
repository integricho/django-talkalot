# -*- coding: utf-8 -*-
from django.db import models
from django.db.models import Count


class ConversationManager(models.Manager):

    def for_participants(self, participants):
        annotation = dict(participant_count=Count('participations'))
        conversations = self.all().annotate(**annotation)

        for user in participants:
            condition = dict(participations__user=user)
            conversations = conversations.filter(**condition)

        return conversations.filter(participant_count=len(participants))


class ParticipationManager(models.Manager):

    def inbox_for(self, user):
        return self.filter(deleted_at__isnull=True, user=user)
