import sys

try:
    # Django 1.7+
    from django import setup as django_setup
except ImportError:
    django_setup = None

from django.conf import settings
from django.core.management import call_command


def runtests():
    if not settings.configured:
        # Choose database for settings
        DATABASES = {
            'default': {
                'ENGINE': 'django.db.backends.sqlite3',
                'NAME': ':memory:'
            }
        }

        # Configure test environment
        settings.configure(
            DATABASES=DATABASES,
            INSTALLED_APPS=(
                'django.contrib.auth',
                'django.contrib.contenttypes',
                'talkalot',
            ),
            ROOT_URLCONF=None,
            LANGUAGES=(
                ('en', 'English'),
            ),
        )

    failures = call_command(
        'test', 'talkalot', interactive=False, failfast=False, verbosity=2)
    sys.exit(bool(failures))


if __name__ == '__main__':
    if django_setup:
        django_setup()

    runtests()
