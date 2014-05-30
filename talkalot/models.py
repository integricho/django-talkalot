# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.conf import settings
try:
    # Django 1.5+
    from django.contrib.auth import get_user_model
except ImportError:
    # Django < 1.5
    def get_user_model():
        from django.contrib.auth.models import User
        return User

from django.db import models
try:
    from django.db.transaction import atomic
except ImportError:
    from django.db.transaction import commit_on_success as atomic

from django.utils.encoding import python_2_unicode_compatible
from django.utils.timezone import now

from .exceptions import MessagingPermissionDenied
from .managers import ConversationManager, ParticipationManager


AUTH_USER_MODEL = getattr(settings, 'AUTH_USER_MODEL', 'auth.User')
PRIVATE_CONVERSATION_MEMBER_COUNT = 2


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

    def read_conversation(self):
        """Gets all the messages from the current conversation and marks it
        read by the participant who requested it.
        """
        messages = self.conversation.messages.all()
        self.read_at = now()
        self.save()
        return messages

    def leave_conversation(self):
        """Sets the deleted_at field of the participation to the time when the
        member in question left the conversation."""
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

        :param participants: A list of usernames, who will be added to the
                             conversation as participants.
        """
        if not participants:
            # don't bother with querying if it's not worth it
            return

        User = get_user_model()
        users = User.objects.filter(username__in=participants)

        for participant in users:
            participation, created = Participation.objects.get_or_create(
                conversation=self,
                user=participant
            )
            if not created:
                # participation already exists, so the user most likely left
                # the conversation, but someone re-added him/her
                participation.reinstate()

    @property
    def participant_names(self):
        """Returns a list of usernames who participate in this conversation."""
        return list(self.active_participations.values_list('user__username',
                                                           flat=True))

    @property
    def is_private(self):
        """Returns whether the conversation is private or not.
        If there are more than PRIVATE_CONVERSATION_MEMBER_COUNT (2)
        participants in the conversation, it is not private.
        """
        return (self.participations.count() ==
                PRIVATE_CONVERSATION_MEMBER_COUNT)

    def has_participant(self, user):
        """Returns whether this user participates in this conversation.

        :param user: A User object (request.user probably)
        """
        return self.active_participations.filter(user=user).exists()

    @classmethod
    def start(cls, creator, participants):
        """Starts a new conversation between the specified participants.

        :param creator: A User object (request.user probably)
        :param participants: A list of usernames, who will be added to the
                             conversation as participants.
        """
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
            recipients = conversation.participant_names + new_participants
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

        # mark conversation as not read for all other participants
        (conversation.active_participations.exclude(user=sender)
                                           .update(read_at=None))

        if not message.parent:
            # if this is the first message of the conversation, the sender's
            # participation should indicate that he/she has both replied to and
            # read this conversation
            fields = dict(replied_at=now(), read_at=now())
        else:
            # if this is not the first message, the sender's replied indicator
            # should be updated only, because the read_at field already has a
            # state, depending whether the sender read the conversation before
            # or not.
            # this means that if the sender sends a reply to the conversation,
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
        participants = list(recipients) + [sender.username]

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
        :param new_participants: Optional, if specified it should be a list of
                                 usernames, who will be added to the existing
                                 conversation as new participants.
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
        :param recipients: List of usernames who will receive the message
        """
        return cls.__send_to_users(body, sender, recipients)
