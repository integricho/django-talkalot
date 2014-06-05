# Talkalot [![Build Status](https://travis-ci.org/integricho/django-talkalot.svg?branch=master)](https://travis-ci.org/integricho/django-talkalot) [![Coverage Status](https://coveralls.io/repos/integricho/django-talkalot/badge.png?branch=master)](https://coveralls.io/r/integricho/django-talkalot?branch=master)

#### A django application to serve as a messaging backend.

Built to provide threaded messaging support for both private and group conversations. It's using fat models, and currently all the logic is located in `models.py`, as the intention is to make it usable by both web applications and web services.
A number of integration tests are written to cover all the scenarios I could think of, but there are probably still some uncovered cases. We've just began...

#### These are the rules being followed:

- A private conversation can be started between two users
- A group conversation can be started between any number of users
- A private conversation can be upgraded into a group conversation
- A group conversation can include additional members after being started
- Members included into a group conversation will inherit it's history
- Members included into a private conversation will NOT inherit it's history, instead the private conversation is left as it is, and a new conversation will be started for the newly formed group
- A member can not leave a private conversation
- A member can leave a group conversation
- A member who left a group conversation can not go back by his/her will
- A member who left a group conversation can be invited back again by other members
- The inbox is considered as being a users list of conversations(techincally the users participations), so two newly received messages in the same conversation will not show up twice in the inbox, because they are under the same conversation

#### Usage:

1. Add *talkalot* to the `INSTALLED_APPS`:

    INSTALLED_APPS = (
        ...
        'talkalot',
        ...
    )

2. Run a `syncdb`.

3. Write your views / api endpoints however you wish, just see the examples below on how to use *talkalot*:


    from django.contrib.auth import get_user_model

    from talkalot.models import Message, Participation


    User = get_user_model()


    # create a list or QuerySet of User objects who are the recipients
    recipients = User.objects.filter(username__in=['alice', 'bob'])
    message = Message.send_to_users('my first message', request.user, recipients)

    # the conversation, where the message belongs can be accessed through the message
    Message.send_to_conversation('a reply coming', request.user, message.conversation)

    # fetch inbox of user
    participations = Participation.objects.inbox_for(request.user)
    # now through the returned QuerySet of participations you get access to the
    # conversations as well, which can be returned as the user's inbox
    inbox_latest_messages = [p.conversation.latest_message for p in participations]

    participation = Participation.objects.get(user=request.user, conversation=message.conversation)
    # leave a conversation
    participation.revoke()
    # re-join conversation
    participation.reinstate()

    # invite a new member into the conversation
    new_users = User.objects.filter(username__in=['frodo', 'sam'])
    message.conversation.add_participants(new_users)

    # include additional members into the conversation along with message sending
    more_users = User.objects.filter(username__in=['gandalf', 'saruman'])
    Message.send_to_conversation('another reply', request.user, message.conversation, new_participants=more_users)


#### API Stability

Be warned, this app is still in it's very early stage of development, and it's API might very easily change, until we settle with the most comfortable combinations and move out of alpha. Also, despite all the tests passing currently, it's not guaranteed to be bug-free and "stuff" might happen.
