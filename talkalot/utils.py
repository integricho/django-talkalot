# -*- coding: utf-8 -*-
from __future__ import unicode_literals


def is_date_greater(date_a, date_b):
    """Return whether date_a is greater than date_b. In case any of them is
    None, treat the one with None as the lesser. If both of them are None,
    date_a will not be considered as greater."""
    if date_a is None and date_b is None:
        return False

    if date_a is None:
        return False

    if date_b is None:
        return True

    return date_a > date_b
