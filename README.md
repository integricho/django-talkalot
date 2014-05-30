# Talkalot [![Build Status](https://travis-ci.org/integricho/django-talkalot.svg?branch=master)](https://travis-ci.org/integricho/talkalot.svg?branch=master) [![Coverage Status](https://img.shields.io/coveralls/integricho/django-talkalot.svg)](https://coveralls.io/r/integricho/talkalot)

#### A django application to serve as a messaging backend.

Built to provide threaded messaging support for both private and group conversations. It's using fat models, and currently all the logic is located in `models.py`, as the intention is to make it usable by both web applications and web services.
A number of integration tests are written to cover all the scenarios I could think of, but there are probably still some uncovered cases. We've just began...
