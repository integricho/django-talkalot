# -*- coding: utf-8 -*-
from django.dispatch import Signal


message_sent = Signal(providing_args=['instance'])
