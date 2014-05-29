import os
from setuptools import setup

README = open(os.path.join(os.path.dirname(__file__), 'README.md')).read()

os.chdir(os.path.normpath(os.path.join(os.path.abspath(__file__), os.pardir)))

setup(
    name='django-talkalot',
    version='0.1',
    packages=['talkalot'],
    include_package_data=True,
    install_requires=['django>=1.5,<1.6'],
    license='BSD License',
    description='A django application to serve as a messaging backend.',
    long_description=README,
    url='https://github.com/integricho/django-talkalot',
    author='Andrean Franc',
    author_email='andrean.franc@gmail.com',
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'Environment :: Web Environment',
        'Framework :: Django',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Topic :: Internet :: WWW/HTTP',
        'Topic :: Internet :: WWW/HTTP :: Dynamic Content',
    ],
)
