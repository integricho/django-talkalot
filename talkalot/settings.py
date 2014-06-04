# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.conf import settings


PRIVATE_CONVERSATION_MEMBER_COUNT = 2

INBOX_CACHE_KEY_PATTERN = getattr(settings,
                                  'INBOX_CACHE_KEY_PATTERN',
                                  'inbox_for_{0}')
CONVERSATION_CACHE_KEY_PATTERN = getattr(settings,
                                         'CONVERSATION_CACHE_KEY_PATTERN',
                                         'conversation_{0}')
PARTICIPANTS_CACHE_KEY_PATTERN = getattr(settings,
                                         'PARTICIPANTS_CACHE_KEY_PATTERN',
                                         'participants_{0}')
