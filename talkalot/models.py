# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.conf import settings
from django.core.cache import cache
from django.db import models
from django.db.models.signals import post_save
try:
    from django.db.transaction import atomic
except ImportError:
    from django.db.transaction import commit_on_success as atomic

from django.utils.encoding import python_2_unicode_compatible
from django.utils.timezone import now

from .exceptions import MessagingPermissionDenied
from .managers import ConversationManager, ParticipationManager
from .settings import (PRIVATE_CONVERSATION_MEMBER_COUNT,
                       INBOX_CACHE_KEY_PATTERN,
                       CONVERSATION_CACHE_KEY_PATTERN)
from .utils import is_date_greater


AUTH_USER_MODEL = getattr(settings, 'AUTH_USER_MODEL', 'auth.User')


@python_2_unicode_compatible
class Participation(models.Model):
    conversation = models.ForeignKey('Conversation',
                                     related_name='participations')
    user = models.ForeignKey(AUTH_USER_MODEL, related_name='participations')
    # messages in conversation seen at
    read_at = models.DateTimeField(null=True, blank=True, db_index=True)
    # replied to conversation at
    replied_at = models.DateTimeField(null=True, blank=True, db_index=True)
    # deleted conversation at
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)

    objects = ParticipationManager()

    class Meta:
        ordering = ['-read_at', 'conversation']
        unique_together = ('conversation', 'user')

    def __str__(self):
        return "{0} - {1}".format(self.user.username, self.conversation)

    @property
    def is_deleted(self):
        return self.deleted_at is not None

    def read_conversation(self):
        """Gets all the messages from the current conversation and marks them
        as read by the participant who requested it."""
        messages = self.conversation.get_messages()

        # mark the conversation as read by the current participator only
        self.read_at = now()
        self.save()

        return messages

    def revoke(self):
        """Sets the deleted_at field of the participation to the time when the
        member in question left the conversation or was kicked out of it."""
        if self.conversation.is_private:
            # can't leave one-on-one conversations
            return

        self.deleted_at = now()
        self.save()

    def reinstate(self):
        """Clears the deleted_at field of the participation, meaning the user
        re-joined the conversation."""
        self.deleted_at = None
        self.save()


@python_2_unicode_compatible
class Conversation(models.Model):
    latest_message = models.ForeignKey('Message',
                                       related_name='conversation_of_latest',
                                       null=True,
                                       blank=True)
    creator = models.ForeignKey(AUTH_USER_MODEL,
                                related_name='created_conversation')

    objects = ConversationManager()

    class Meta:
        ordering = ['latest_message']

    def __str__(self):
        return "{0} - {1}".format(self.pk, self.latest_message)

    @property
    def active_participations(self):
        """Returns a queryset of active participations, meaning that revoked
        participations(when a user leaves a conversation) won't be included."""
        return self.participations.filter(deleted_at__isnull=True)

    def add_participants(self, participants):
        """Adds participants to an existing conversation.

        :param participants: A QuerySet or list of user objects, who will be
                             added to the conversation as participants."""
        for user in participants:
            participation, created = Participation.objects.get_or_create(
                conversation=self,
                user=user
            )
            if not created and participation.is_deleted:
                # participation already exists and it was marked as deleted, so
                # the user most likely left the conversation, but someone
                # re-added him/her
                participation.reinstate()

    def remove_participants(self, participants):
        """Removes participants from an existing conversation.

        :param participants: A QuerySet or list of user objects, whose
                             participations will be revoked."""
        for user in participants:
            participation = self.participations.get(user=user)
            participation.revoke()

    @property
    def participants(self):
        """Returns a list of user objects participating in this conversation"""
        return [p.user for p in self.active_participations.all()]

    @property
    def participant_names(self):
        """Returns a list of usernames who participate in this conversation."""
        return list(self.active_participations.values_list('user__username',
                                                           flat=True))

    def has_participant(self, user):
        """Returns whether this user participates in this conversation.

        :param user: A User object (request.user probably)"""
        return self.active_participations.filter(user=user).exists()

    @property
    def is_private(self):
        """Returns whether the conversation is private or not.
        If there are more than PRIVATE_CONVERSATION_MEMBER_COUNT (2)
        participants in the conversation, it is not private."""
        return (self.participations.count() ==
                PRIVATE_CONVERSATION_MEMBER_COUNT)

    def get_messages(self):
        key = CONVERSATION_CACHE_KEY_PATTERN.format(self.pk)
        messages = cache.get(key)

        if not messages:
            messages = self.messages.all()
            cache.set(key, messages)

        return messages

    @classmethod
    def start(cls, creator, participants):
        """Starts a new conversation between the specified participants.

        :param creator: A User object (request.user probably)
        :param participants: A QuerySet or list of user objects, who will be
                             added to the conversation as participants."""
        conversation = cls.objects.create(creator=creator)
        conversation.add_participants(participants)
        return conversation


@python_2_unicode_compatible
class Message(models.Model):
    body = models.TextField()
    parent = models.ForeignKey('self',
                               related_name='next_messages',
                               blank=True,
                               null=True)
    sender = models.ForeignKey(AUTH_USER_MODEL, related_name='sent_messages')
    sent_at = models.DateTimeField(auto_now_add=True, db_index=True)
    conversation = models.ForeignKey('Conversation', related_name='messages')

    class Meta:
        ordering = ['-sent_at']

    def __str__(self):
        return "{0} - {1}".format(self.sender.username, self.sent_at)

    @classmethod
    def __send_to_conversation(cls, body, sender, conversation,
                               new_participants=None):
        """Internally used by both send_to_conversation and __send_to_users
        methods. Refactored as a separate method to avoid nesting the atomic
        decorator when __send_to_users needs to call __send_to_conversation."""
        new_participants = list(new_participants) if new_participants else []

        # check whether the sender is participating in the conversation or not
        # without this, arbitary users could send messages into conversations
        # which they're not even part of
        if not conversation.has_participant(sender):
            msg = "{0} not participating".format(sender.username)
            raise MessagingPermissionDenied(msg)

        if new_participants and conversation.is_private:
            # this conversation can NOT be extended to include additional
            # participants, instead a new conversation has to be started which
            # will include all the participants, but not the history of the
            # private conversation
            recipients = conversation.participants + new_participants
            return cls.__send_to_users(body, sender, recipients)

        # this was already a group conversation, so just add the new
        # participants to it
        conversation.add_participants(new_participants)

        message = cls.objects.create(body=body,
                                     parent=conversation.latest_message,
                                     sender=sender,
                                     conversation=conversation)
        # update latest message of conversation
        conversation.latest_message = message
        conversation.save()

        p_sender = sender.participations.get(conversation=conversation)
        p_recipients = conversation.active_participations.exclude(user=sender)
        # mark conversation as not read for all participants except the sender
        p_recipients.update(read_at=None)

        if not any(is_date_greater(pr.replied_at, p_sender.read_at)
                   for pr in p_recipients):
            # if the sender's read_at time is greater than all the other
            # participant's replied_at time, it means the sender already read
            # all the messages the other's sent, so update the sender's read_at
            # value again, to reflect that the sender read it's own (just now
            # sent) message.
            fields = dict(replied_at=now(), read_at=now())
        else:
            # if the sender's read_at time is less than any of the other
            # participants replied_at time, it means the sender didn't yet
            # read the other replier's message, so do not touch the sender's
            # read_at time.
            # this also means that if the sender replies to the conversation,
            # it doesnt't imply that he/she also read the latest message sent
            # before his/her message
            fields = dict(replied_at=now())

        conversation.participations.filter(user=sender).update(**fields)

        return message

    @classmethod
    def __send_to_users(cls, body, sender, recipients):
        """Internally used by both send_to_users and __send_to_conversation
        methods. Refactored as a separate method to avoid nesting the atomic
        decorator when __send_to_conversation needs to call __send_to_users."""
        participants = list(recipients)

        # if sender is the only participant, deny message sending
        if sender in participants and len(participants) == 1:
            raise MessagingPermissionDenied("No self-messaging allowed.")

        participants.append(sender)
        conversations = Conversation.objects.for_participants(participants)

        if not conversations.exists():
            # no conversation exists between the specified participants, so
            # create a new one
            conversation = Conversation.start(creator=sender,
                                              participants=participants)
        else:
            # a conversation exists between the specified participants, so send
            # the message to that conversation
            (conversation,) = conversations

        return cls.__send_to_conversation(body, sender, conversation)

    @classmethod
    @atomic
    def send_to_conversation(cls, body, sender, conversation,
                             new_participants=None):
        """Sends a message to a specific conversation.

        The transaction is atomic, so if anything fails during message sending,
        nothing will be committed.

        :param body: Body of the new message
        :param sender: A User object (request.user probably)
        :param conversation: Conversation instance
        :param new_participants: Optional, if specified it should be a Queryset
                                 or list of user objects, who will be added to
                                 the existing conversation as new participants.
        """
        return cls.__send_to_conversation(body,
                                          sender,
                                          conversation,
                                          new_participants)

    @classmethod
    @atomic
    def send_to_users(cls, body, sender, recipients):
        """Sends a message to a list of users.

        The transaction is atomic, so if anything fails during message sending,
        nothing will be committed.

        :param body: Body of the new message
        :param sender: A User object (request.user probably)
        :param recipients: Queryset or list of user objects who will receive
                           the message."""
        return cls.__send_to_users(body, sender, recipients)


def clear_cached_inbox_of_participant(sender, instance, **kwargs):
    """When a participation is changed, either revoked or reinstated, the inbox
    of the participant shall be invalidated, to reflect the current list of
    active conversations."""
    key = INBOX_CACHE_KEY_PATTERN.format(instance.user.pk)
    cache.delete(key)


def clear_cached_inbox_of_all_participants(sender, instance, **kwargs):
    """When a message is sent, the cached inboxes of all the participants of
    the conversation where the message is sent shall be invalidated as the lead
    message has changed, and the order of the conversations in their inboxes
    will be different."""
    for participation in instance.conversation.participations.all():
        key = INBOX_CACHE_KEY_PATTERN.format(participation.user.pk)
        cache.delete(key)


def clear_conversation_cache(sender, instance, **kwargs):
    """When a message is sent, the cached conversation (all of it's messages)
    shall be invalidated."""
    key = CONVERSATION_CACHE_KEY_PATTERN.format(instance.conversation.pk)
    cache.delete(key)


post_save.connect(clear_cached_inbox_of_participant,
                  sender=Participation,
                  dispatch_uid="clear_cached_inbox_of_participant")


post_save.connect(clear_cached_inbox_of_all_participants,
                  sender=Message,
                  dispatch_uid="clear_cached_inbox_of_all_participants")


post_save.connect(clear_conversation_cache,
                  sender=Message,
                  dispatch_uid="clear_conversation_cache")
