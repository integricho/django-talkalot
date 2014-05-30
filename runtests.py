import os
import sys

import django

from django.core.management import call_command


def runtests():
    failures = call_command('test',
                            'talkalot',
                            interactive=False,
                            failfast=False,
                            verbosity=2)
    sys.exit(bool(failures))


if __name__ == '__main__':
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'talkalot.tests.settings')

    if hasattr(django, 'setup'):
        django.setup()

    runtests()
