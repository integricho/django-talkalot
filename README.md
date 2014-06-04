# Talkalot [![Build Status](https://travis-ci.org/integricho/django-talkalot.svg?branch=master)](https://travis-ci.org/integricho/django-talkalot) [![Coverage Status](https://coveralls.io/repos/integricho/django-talkalot/badge.png?branch=master)](https://coveralls.io/r/integricho/django-talkalot?branch=master)

#### A django application to serve as a messaging backend.

Built to provide threaded messaging support for both private and group conversations. It's using fat models, and currently all the logic is located in `models.py`, as the intention is to make it usable by both web applications and web services.
A number of integration tests are written to cover all the scenarios I could think of, but there are probably still some uncovered cases. We've just began...
