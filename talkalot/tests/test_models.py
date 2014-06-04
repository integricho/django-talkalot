# -*- coding: utf-8 -*-
try:
    # Django 1.5+
    from django.contrib.auth import get_user_model
except ImportError:
    # Django < 1.5
    def get_user_model():
        from django.contrib.auth.models import User
        return User

from django.core.cache import cache
from django.test import TestCase, TransactionTestCase

from ..exceptions import MessagingPermissionDenied
from ..models import Conversation, Participation, Message


def setup_users(func):
    def _setup_users(self, *args, **kwargs):
        self.users = dict()
        User = get_user_model()

        for prefix in ('friend', 'foe'):
            for i in range(5):
                username = '{0}{1}'.format(prefix, i)
                email = '{0}@gmail.com'.format(username)
                password = username
                self.users[username] = User.objects.create_user(username,
                                                                email,
                                                                password)
        return func(self, *args, **kwargs)
    return _setup_users


def setup_conversations(func):
    def _setup_conversations(self, *args, **kwargs):
        self.conv1 = Conversation.objects.create(creator=self.users['friend0'])
        self.conv2 = Conversation.objects.create(creator=self.users['foe0'])
        self.conv3 = Conversation.objects.create(creator=self.users['friend2'])
        self.conv4 = Conversation.objects.create(creator=self.users['friend0'])

        Participation.objects.create(conversation=self.conv1,
                                     user=self.users['friend0'])
        Participation.objects.create(conversation=self.conv1,
                                     user=self.users['friend1'])

        Participation.objects.create(conversation=self.conv2,
                                     user=self.users['foe0'])
        Participation.objects.create(conversation=self.conv2,
                                     user=self.users['foe1'])

        Participation.objects.create(conversation=self.conv3,
                                     user=self.users['friend2'])
        Participation.objects.create(conversation=self.conv3,
                                     user=self.users['friend1'])

        Participation.objects.create(conversation=self.conv4,
                                     user=self.users['friend0'])
        Participation.objects.create(conversation=self.conv4,
                                     user=self.users['friend1'])
        Participation.objects.create(conversation=self.conv4,
                                     user=self.users['friend3'])
        return func(self, *args, **kwargs)
    return _setup_conversations


class BaseMessagingTest(object):

    def assert_participants(self, conversation, participants):
        self.assertEqual(conversation.active_participations.count(),
                         len(participants))
        for participant in conversation.active_participations.all():
            self.assertIn(participant.user, participants)

    def tearDown(self):
        cache.clear()


class BaseMessagingTestCase(BaseMessagingTest, TestCase):
    pass


class BaseMessagingTransactionTestCase(BaseMessagingTest, TransactionTestCase):
    pass


class ConversationTestCase(BaseMessagingTestCase):

    @setup_users
    @setup_conversations
    def test_get_participants(self):
        participants = [self.users['friend0'], self.users['friend1']]
        (conversation,) = Conversation.objects.for_participants(participants)

        for user in conversation.participants:
            self.assertIn(user, participants)

    @setup_users
    @setup_conversations
    def test_get_participant_names(self):
        participants = [self.users['friend0'], self.users['friend1']]
        (conversation,) = Conversation.objects.for_participants(participants)

        for username in conversation.participant_names:
            self.assertIn(username, ['friend0', 'friend1'])

    @setup_users
    @setup_conversations
    def test_conversation_exists(self):
        participants = [self.users['friend0'], self.users['friend1']]
        conversations = Conversation.objects.for_participants(participants)
        (conversation,) = conversations
        self.assertEqual(conversation.pk, self.conv1.pk)

        participants = [self.users['friend0'],
                        self.users['friend1'],
                        self.users['friend3']]
        conversations = Conversation.objects.for_participants(participants)
        (conversation,) = conversations
        self.assertEqual(conversation.pk, self.conv4.pk)

    @setup_users
    @setup_conversations
    def test_conversation_does_not_exists(self):
        participants = [self.users['friend0'], self.users['friend3']]
        conversations = Conversation.objects.for_participants(participants)
        self.assertTrue(not conversations.exists())

        participants = [self.users['foe0']]
        conversations = Conversation.objects.for_participants(participants)
        self.assertTrue(not conversations.exists())

    @setup_users
    def test_start_new_private_conversation(self):
        creator = self.users['friend0']
        participants = [self.users['friend0'], self.users['friend1']]

        conversation = Conversation.start(creator=creator,
                                          participants=participants)

        self.assertEqual(conversation.creator.pk, creator.pk)
        self.assertEqual(conversation.latest_message, None)
        self.assert_participants(conversation, participants)

    @setup_users
    def test_start_new_group_conversation(self):
        creator = self.users['friend1']
        participants = [self.users['friend1'],
                        self.users['friend2'],
                        self.users['friend3']]

        conversation = Conversation.start(creator=creator,
                                          participants=participants)

        self.assertEqual(conversation.creator.pk, creator.pk)
        self.assertEqual(conversation.latest_message, None)
        self.assert_participants(conversation, participants)


class MessageTestCase(BaseMessagingTestCase):

    def check_conv_of(self, message, parent, sender, conversation_creator,
                      conversation_participants):
        self.assertEqual(message.sender.pk, sender.pk)
        self.assertEqual(message.parent, parent)
        self.assertEqual(message.conversation.latest_message, message)
        self.assertEqual(message.conversation.creator.pk,
                         conversation_creator.pk)
        self.assert_participants(message.conversation,
                                 conversation_participants)

    @setup_users
    def test_string_representations(self):
        """Tests the __str__ methods of all models"""
        body = 'group message'
        sender = self.users['friend0']
        recipients = [self.users['friend1']]
        message = Message.send_to_users(body, sender, recipients)
        participation = (message.conversation.participations
                                             .get(user=self.users['friend0']))

        # {{ sender_username }} - {{ sent_at }}
        self.assertEqual(
            str(message),
            "{0} - {1}".format(message.sender.username, message.sent_at)
        )
        # {{ primary_key }} - {{ str(latest_message) }}
        self.assertEqual(
            str(message.conversation),
            "{0} - {1}".format(message.conversation.pk,
                               message.conversation.latest_message)
        )
        # {{ participant_username }} - {{ str(conversation) }}
        self.assertEqual(
            str(participation),
            "{0} - {1}".format(participation.user.username,
                               participation.conversation)
        )

    def _send_to_users_test(self, participants):
        """Starts a new group conversation from scratch, and replies to it,
        always using only the usernames of the recipients"""
        body = 'group message'

        sender1 = self.users['friend0']
        recipients1 = [self.users['friend1'], self.users['friend3']]
        message1 = Message.send_to_users(body, sender1, recipients1)

        self.check_conv_of(message=message1,
                           parent=None,
                           sender=sender1,
                           conversation_creator=sender1,
                           conversation_participants=participants)

        sender2 = self.users['friend1']
        recipients2 = [self.users['friend0'], self.users['friend3']]
        message2 = Message.send_to_users(body, sender2, recipients2)

        self.check_conv_of(message=message2,
                           parent=message1,
                           sender=sender2,
                           conversation_creator=sender1,
                           conversation_participants=participants)

        # there should be one and only one conversation so far
        self.assertEqual(message2.conversation.pk, message1.conversation.pk)

    @setup_users
    def test_send_to_users_list(self):
        participants = [self.users['friend0'],
                        self.users['friend1'],
                        self.users['friend3']]
        self._send_to_users_test(participants)

    @setup_users
    def test_send_to_users_queryset(self):
        User = get_user_model()
        usernames = ['friend0', 'friend1', 'friend3']
        participants = User.objects.filter(username__in=usernames)
        self._send_to_users_test(participants)

    def _send_to_conversation_test(self, new_participants):
        """Starts a new group conversation from scratch, then tries to reply to
        the conversation itself, not through the usernames only, and include
        additional participants."""
        # send first group message
        body = 'group message'

        initial_participants = [self.users['friend0'],
                                self.users['friend1'],
                                self.users['friend3']]

        sender1 = self.users['friend0']
        recipients1 = [self.users['friend1'], self.users['friend3']]
        message1 = Message.send_to_users(body, sender1, recipients1)

        self.check_conv_of(message=message1,
                           parent=None,
                           sender=sender1,
                           conversation_creator=sender1,
                           conversation_participants=initial_participants)

        # reply to it and attach new user
        sender2 = self.users['friend1']
        message2 = Message.send_to_conversation(
            body,
            sender2,
            message1.conversation,
            new_participants=new_participants
        )
        merged_participants = (list(initial_participants) +
                               list(new_participants))

        self.check_conv_of(message=message2,
                           parent=message1,
                           sender=sender2,
                           conversation_creator=sender1,
                           conversation_participants=merged_participants)

        # still the same conversation as new members attached to a group
        # conversation (unlike to private conversations) inherit the history
        self.assertEqual(message2.conversation.pk, message1.conversation.pk)

    @setup_users
    def test_send_to_conversation_list(self):
        new_participants = [self.users['friend2']]
        self._send_to_conversation_test(new_participants)

    @setup_users
    def test_send_to_conversation_queryset(self):
        User = get_user_model()
        new_participants = User.objects.filter(username='friend2')
        self._send_to_conversation_test(new_participants)

    @setup_users
    def test_leave_then_rejoin_group_conversation(self):
        """Starts a new group conversation, the started leaves the conversation
        but get's invited back by another member."""
        # send first group message
        body = 'group message'

        initial_participants = [self.users['friend0'],
                                self.users['friend1'],
                                self.users['friend3']]

        sender1 = self.users['friend0']
        recipients1 = [self.users['friend1'], self.users['friend3']]
        message1 = Message.send_to_users(body, sender1, recipients1)

        self.check_conv_of(message=message1,
                           parent=None,
                           sender=sender1,
                           conversation_creator=sender1,
                           conversation_participants=initial_participants)

        # friend0 leaves the conversation
        p1 = (message1.conversation
                      .participations
                      .get(user=self.users['friend0']))
        p1.leave_conversation()

        self.check_conv_of(message=message1,
                           parent=None,
                           sender=sender1,
                           conversation_creator=sender1,
                           conversation_participants=[self.users['friend1'],
                                                      self.users['friend3']])

        # reply to conversation, and add friend0 back
        sender2 = self.users['friend1']
        message2 = Message.send_to_conversation(
            body,
            sender2,
            message1.conversation,
            new_participants=[self.users['friend0']]
        )

        self.check_conv_of(message=message2,
                           parent=message1,
                           sender=sender2,
                           conversation_creator=sender1,
                           conversation_participants=initial_participants)

        # still the same conversation as new members attached to a group
        # conversation (unlike to private conversations) inherit the history
        self.assertEqual(message2.conversation.pk, message1.conversation.pk)

    @setup_users
    def test_cant_leave_private_conversation(self):
        """Starts a private conversation, then tries to leave it without
        success."""
        # send first private message
        body = 'private message'

        sender1 = self.users['friend0']
        message1 = Message.send_to_users(body,
                                         sender1,
                                         [self.users['friend1']])
        conv1_participants = [self.users['friend0'], self.users['friend1']]

        self.check_conv_of(message=message1,
                           parent=None,
                           sender=sender1,
                           conversation_creator=sender1,
                           conversation_participants=conv1_participants)

        self.assertEqual(message1.conversation.is_private, True)

        # friend0 tries to leave the conversation
        p1 = (message1.conversation
                      .participations
                      .get(user=self.users['friend0']))
        p1.leave_conversation()

        self.check_conv_of(message=message1,
                           parent=None,
                           sender=sender1,
                           conversation_creator=sender1,
                           conversation_participants=conv1_participants)

    @setup_users
    def test_send_to_private_conversation(self):
        """Starts a private conversation, then upgrades it into a group."""
        # send first private message
        body = 'private message'

        sender1 = self.users['friend0']
        message1 = Message.send_to_users(body,
                                         sender1,
                                         [self.users['friend1']])
        conv1_participants = [self.users['friend0'], self.users['friend1']]

        self.check_conv_of(message=message1,
                           parent=None,
                           sender=sender1,
                           conversation_creator=sender1,
                           conversation_participants=conv1_participants)

        # reply to private message
        sender2 = self.users['friend1']
        message2 = Message.send_to_conversation(body,
                                                sender2,
                                                message1.conversation)

        self.check_conv_of(message=message2,
                           parent=message1,
                           sender=sender2,
                           conversation_creator=sender1,
                           conversation_participants=conv1_participants)

        self.assertEqual(message2.conversation.pk, message1.conversation.pk)

        # reply again and include the third participant now
        message3 = Message.send_to_conversation(
            body,
            sender1,
            message1.conversation,
            new_participants=[self.users['friend2']]
        )

        conv2_participants = [self.users['friend0'],
                              self.users['friend1'],
                              self.users['friend2']]

        self.check_conv_of(message=message3,
                           parent=None,
                           sender=sender1,
                           conversation_creator=sender1,
                           conversation_participants=conv2_participants)

        self.assertNotEqual(message2.conversation.pk, message3.conversation.pk)

    @setup_users
    def test_send_to_conversation_with_no_permission(self):
        body = 'private message'

        # a private conversation has been started
        message1 = Message.send_to_users(body,
                                         self.users['friend0'],
                                         [self.users['friend1']])
        Message.send_to_users(body,
                              self.users['friend1'],
                              [self.users['friend0']])

        # the enemy decides to drop in this conversation
        with self.assertRaises(MessagingPermissionDenied):
            Message.send_to_conversation('hi jack!',
                                         self.users['foe0'],
                                         message1.conversation)

        self.assert_participants(
            message1.conversation,
            [self.users['friend0'], self.users['friend1']]
        )
        self.assertEqual(message1.conversation.messages.count(), 2)

    @setup_users
    def test_send_to_conversation_previously_left(self):
        # start group conversation
        body = 'group message'

        initial_participants = [self.users['friend0'],
                                self.users['friend1'],
                                self.users['friend3']]

        sender1 = self.users['friend0']
        recipients1 = [self.users['friend1'], self.users['friend3']]
        message1 = Message.send_to_users(body, sender1, recipients1)

        self.check_conv_of(message=message1,
                           parent=None,
                           sender=sender1,
                           conversation_creator=sender1,
                           conversation_participants=initial_participants)

        # friend0 leaves the conversation
        p1 = (message1.conversation
                      .participations
                      .get(user=self.users['friend0']))
        p1.leave_conversation()

        # friend0 regrets his decision to leave the conversation, tries to
        # resume it, but now there's now way back on his own
        with self.assertRaises(MessagingPermissionDenied):
            Message.send_to_conversation('hi jack!',
                                         self.users['friend0'],
                                         message1.conversation)

        self.assert_participants(
            message1.conversation,
            [self.users['friend1'], self.users['friend3']]
        )
        self.assertEqual(message1.conversation.messages.count(), 1)


class DataIntegrityTestCase(BaseMessagingTransactionTestCase):

    @setup_users
    def test_atomicity(self):
        # set up an initial conversation
        message = Message.send_to_users(
            'msg',
            self.users['friend0'],
            [self.users['friend1'], self.users['friend2']]
        )
        Message.send_to_conversation('msg2',
                                     self.users['friend1'],
                                     message.conversation)
        # make sure it has the right number of messages and participants
        expected_participants = [self.users['friend0'],
                                 self.users['friend1'],
                                 self.users['friend2']]
        expected_message_count = 2

        self.assert_participants(message.conversation, expected_participants)
        self.assertEqual(message.conversation.messages.count(),
                         expected_message_count)

        # create a deliberate bug during message sending
        old_save = Conversation.save

        def failing_save(*args, **kwargs):
            raise Exception()

        Conversation.save = failing_save

        with self.assertRaises(Exception):
            Message.send_to_conversation(
                'msg',
                self.users['friend0'],
                message.conversation,
                new_participants=[self.users['friend3']]
            )

        Conversation.save = old_save

        # make sure no side effects happened
        self.assert_participants(message.conversation, expected_participants)
        self.assertEqual(message.conversation.messages.count(),
                         expected_message_count)


class ParticipationTestCase(BaseMessagingTestCase):

    def verify_participation(self, user, inbox):
        for participation in inbox:
            self.assertIn(user, participation.conversation.participants)

    @setup_users
    def test_get_inbox(self):
        body = 'private message'

        # send three private messages to three different users
        for recipient in [self.users['friend1'],
                          self.users['friend2'],
                          self.users['friend3']]:
            Message.send_to_users(body, self.users['friend0'], [recipient])

        # send one more message to first user (tricky)
        Message.send_to_users(body,
                              self.users['friend0'],
                              [self.users['friend1']])

        # create a group conversation with two other users
        group_message = Message.send_to_users(
            body,
            self.users['friend0'],
            [self.users['friend1'], self.users['friend3']]
        )

        # send one reply to friend0 (should not affect conversation count)
        Message.send_to_users(body,
                              self.users['friend1'],
                              [self.users['friend0']])

        # friend2 and friend1 exchange a couple of words
        Message.send_to_users(body,
                              self.users['friend2'],
                              [self.users['friend1']])

        expected_conversation_count_friend0 = 4
        friend0_inbox = Participation.objects.inbox_for(self.users['friend0'])
        self.assertEqual(friend0_inbox.count(),
                         expected_conversation_count_friend0)
        self.verify_participation(self.users['friend0'], friend0_inbox)

        expected_conversation_count_friend1 = 3
        friend1_inbox = Participation.objects.inbox_for(self.users['friend1'])
        self.assertEqual(friend1_inbox.count(),
                         expected_conversation_count_friend1)
        self.verify_participation(self.users['friend1'], friend1_inbox)

        expected_conversation_count_friend2 = 2
        friend2_inbox = Participation.objects.inbox_for(self.users['friend2'])
        self.assertEqual(friend2_inbox.count(),
                         expected_conversation_count_friend2)
        self.verify_participation(self.users['friend2'], friend2_inbox)

        expected_conversation_count_friend3 = 2
        friend3_inbox = Participation.objects.inbox_for(self.users['friend3'])
        self.assertEqual(friend3_inbox.count(),
                         expected_conversation_count_friend3)
        self.verify_participation(self.users['friend3'], friend3_inbox)

        # after friend0 leaves a group conversation, it should reduce the
        # conversation count
        (group_message.conversation.active_participations
                                   .get(user=self.users['friend0'])
                                   .leave_conversation())

        expected_conversation_count_friend0 = 3
        friend0_inbox = Participation.objects.inbox_for(self.users['friend0'])
        self.assertEqual(friend0_inbox.count(),
                         expected_conversation_count_friend0)
        self.verify_participation(self.users['friend0'], friend0_inbox)

    def verify_is_read(self, message, by_user, should_have_read):
        participation = message.conversation.participations.get(user=by_user)
        if should_have_read:
            self.assertNotEqual(participation.read_at, None)
        else:
            self.assertEqual(participation.read_at, None)

    def verify_is_read_block(self, expectations):
        for message, participants in expectations:
            for username, should_have_read in participants:
                self.verify_is_read(message,
                                    by_user=self.users[username],
                                    should_have_read=should_have_read)

    @setup_users
    def test_conversation_read_at(self):
        body = 'private message'

        message1 = Message.send_to_users(body,
                                         self.users['friend0'],
                                         [self.users['friend1']])
        message2 = Message.send_to_users(body,
                                         self.users['friend0'],
                                         [self.users['friend2']])
        message3 = Message.send_to_users(body,
                                         self.users['friend0'],
                                         [self.users['friend3']])

        # no one "read" the message except sender
        expectations = ((message1, (('friend0', True), ('friend1', False))),
                        (message2, (('friend0', True), ('friend2', False))),
                        (message3, (('friend0', True), ('friend3', False))))
        self.verify_is_read_block(expectations)

        # friend1 reads it
        p1 = (message1.conversation
                      .participations
                      .get(user=self.users['friend1']))
        p1.read_conversation()
        # no one "read" the message except sender and friend1
        expectations = ((message1, (('friend0', True), ('friend1', True))),
                        (message2, (('friend0', True), ('friend2', False))),
                        (message3, (('friend0', True), ('friend3', False))))
        self.verify_is_read_block(expectations)

        # friend2 reads it too
        p2 = (message2.conversation
                      .participations
                      .get(user=self.users['friend2']))
        p2.read_conversation()
        # no one "read" the message except sender and friend1
        expectations = ((message1, (('friend0', True), ('friend1', True))),
                        (message2, (('friend0', True), ('friend2', True))),
                        (message3, (('friend0', True), ('friend3', False))))
        self.verify_is_read_block(expectations)

    def verify_has_replied(self, message, by_user, should_have_replied):
        participation = message.conversation.participations.get(user=by_user)
        if should_have_replied:
            self.assertNotEqual(participation.replied_at, None)
        else:
            self.assertEqual(participation.replied_at, None)

    def verify_has_replied_block(self, expectations):
        for message, participants in expectations:
            for username, shr in participants:
                self.verify_has_replied(message,
                                        by_user=self.users[username],
                                        should_have_replied=shr)

    @setup_users
    def test_conversation_replied_at(self):
        body = 'private message'

        message1 = Message.send_to_users(body,
                                         self.users['friend0'],
                                         [self.users['friend1']])
        message2 = Message.send_to_users(body,
                                         self.users['friend0'],
                                         [self.users['friend2']])
        message3 = Message.send_to_users(body,
                                         self.users['friend0'],
                                         [self.users['friend3']])

        # no one replied to the conversation except sender
        expectations = ((message1, (('friend0', True), ('friend1', False))),
                        (message2, (('friend0', True), ('friend2', False))),
                        (message3, (('friend0', True), ('friend3', False))))
        self.verify_has_replied_block(expectations)

        # friend1 replies to conversation
        Message.send_to_conversation(body,
                                     self.users['friend1'],
                                     message1.conversation)
        # no one replied to the conversation except sender and friend1
        expectations = ((message1, (('friend0', True), ('friend1', True))),
                        (message2, (('friend0', True), ('friend2', False))),
                        (message3, (('friend0', True), ('friend3', False))))
        self.verify_has_replied_block(expectations)

        # friend2 replies too
        Message.send_to_conversation(body,
                                     self.users['friend2'],
                                     message2.conversation)
        # no one "read" the message except sender and friend1
        expectations = ((message1, (('friend0', True), ('friend1', True))),
                        (message2, (('friend0', True), ('friend2', True))),
                        (message3, (('friend0', True), ('friend3', False))))
        self.verify_has_replied_block(expectations)

    @setup_users
    def test_conversation_scenario_replied_at_and_read_at_flags(self):
        body = 'private message'

        message = Message.send_to_users(body,
                                        self.users['friend0'],
                                        [self.users['friend1'],
                                         self.users['friend2'],
                                         self.users['friend3']])

        # no one replied to the conversation except sender
        expectations = [(message, (('friend0', True),
                                   ('friend1', False),
                                   ('friend2', False),
                                   ('friend3', False)))]
        self.verify_has_replied_block(expectations)

        # no one "read" the messages except sender (reply implies read state
        # only for the first message)
        expectations = [(message, (('friend0', True),
                                   ('friend1', False),
                                   ('friend2', False),
                                   ('friend3', False)))]
        self.verify_is_read_block(expectations)

        ##########

        # friend1 replies to conversation without seeing the conversation,
        # which is hightly improbable but possible through the API
        Message.send_to_conversation(body,
                                     self.users['friend1'],
                                     message.conversation)
        # no one replied to the conversation except sender and friend1
        expectations = [(message, (('friend0', True),
                                   ('friend1', True),
                                   ('friend2', False),
                                   ('friend3', False)))]
        self.verify_has_replied_block(expectations)

        # all the participants got their "read" flag reset because a new
        # message arrived on the conversation. the sender didnt get his "read"
        # mark, because he didnt read the previous message, just sent a new one
        expectations = [(message, (('friend0', False),
                                   ('friend1', False),
                                   ('friend2', False),
                                   ('friend3', False)))]
        self.verify_is_read_block(expectations)

        ##########

        # previous sender (friend1) finally decides to see the messages
        p1 = (message.conversation
                     .participations
                     .get(user=self.users['friend1']))
        p1.read_conversation()
        # now he is the only one in the conversation who have seen all messages
        expectations = [(message, (('friend0', False),
                                   ('friend1', True),
                                   ('friend2', False),
                                   ('friend3', False)))]
        self.verify_is_read_block(expectations)

        ##########

        # friend2 decides to check the messages too
        p2 = (message.conversation
                     .participations
                     .get(user=self.users['friend2']))
        p2.read_conversation()
        # now both friend 1 and friend2 have seen all messages
        expectations = [(message, (('friend0', False),
                                   ('friend1', True),
                                   ('friend2', True),
                                   ('friend3', False)))]
        self.verify_is_read_block(expectations)

        ##########

        # friend2 sends something
        Message.send_to_conversation(body,
                                     self.users['friend2'],
                                     message.conversation)
        # everyone except friend3 replied
        expectations = [(message, (('friend0', True),
                                   ('friend1', True),
                                   ('friend2', True),
                                   ('friend3', False)))]
        self.verify_has_replied_block(expectations)

        # as friend2 sent the message, and he saw the previous messages, he's
        # the only one now who have seen all messages
        expectations = [(message, (('friend0', False),
                                   ('friend1', False),
                                   ('friend2', True),
                                   ('friend3', False)))]
        self.verify_is_read_block(expectations)
