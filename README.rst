QueueBot
========

.. |py3| image:: https://img.shields.io/badge/python-3.6-blue.svg

.. |license| image:: https://img.shields.io/badge/License-MIT-blue.svg
  :target: https://github.com/BlobEmoji/queuebot/blob/master/LICENSE

.. |travis| image:: https://img.shields.io/travis/BlobEmoji/queuebot/master.svg?label=TravisCI
  :target: https://travis-ci.org/BlobEmoji/queuebot

.. |circleci| image:: https://img.shields.io/circleci/project/github/BlobEmoji/queuebot/master.svg?label=CircleCI
  :target: https://circleci.com/gh/BlobEmoji/queuebot

.. |issues| image:: https://img.shields.io/github/issues/BlobEmoji/queuebot.svg?colorB=3333ff
  :target: https://github.com/BlobEmoji/queuebot/issues

.. |commits| image:: https://img.shields.io/github/commit-activity/w/BlobEmoji/queuebot.svg
  :target: https://github.com/BlobEmoji/queuebot/commits

|py3| |license| |travis| |circleci| |issues| |commits|

QueueBot manages suggestion queueing and approval for the Blob Emoji Discord guild.
It requires Python >=3.6 and the `discord.py@rewrite <https://github.com/Rapptz/discord.py/tree/rewrite/>`__ library.

It is not recommended to run an instance of this bot yourself. The code is here primarily for reference and bugfixing.


Prerequisites
-------------

This project has a number of requirements for deployment:

- ``git``, for acquiring ``discord.py@rewrite``
- A PostgreSQL >=13 server to store suggestion data
- A ``config.yaml`` file containing configuration data
- ``libuv`` to enable ``uvloop``
- Python requirements as in `requirements.txt <https://github.com/slice/queuebot/blob/master/requirements.txt>`__

git
###

Windows
+++++++

``git`` can be used in Windows either by `Git for Windows <https://git-for-windows.github.io/>`__ or subshells such as `MinGW <http://www.mingw.org/>`__.

Linux
+++++

``git`` should be available from your system package manager, for example in Debian-based systems:

.. code-block:: sh

  apt install git

and in Arch-based systems:

.. code-block:: sh

  pacman -S git

PostgreSQL >=13
################

Installation
++++++++++++

Installation for PostgreSQL varies based on system:

Windows
^^^^^^^

PostgreSQL for Windows can be installed via the `Windows installers <https://www.postgresql.org/download/windows/>`__ page.

Once you've installed PostgreSQL, open the Start Menu, search for "SQL Shell (psql)", and run it.

If you changed any of the credentials (such as the port) in the installer, type them in, otherwise just press Enter until it asks for your password.

Enter the password you entered into the installer, and psql should load into the postgres user.

Arch Linux
^^^^^^^^^^

Arch includes up to date PostgreSQL packages in their official repositories. To install, simply run:

.. code-block:: sh

  pacman -S postgresql

After installing, you can use ``sudo -u postgres -i psql`` to log in as the default PostgreSQL user.

Debian
^^^^^^

In order to get specific versions of PostgreSQL on Debian, you will need to add an apt repository.

As apt requires root, you must be superuser for all of the below. (you can become superuser using ``sudo su`` if you are not already.)

To add an apt repository, we need to edit ``/etc/apt/sources.list``, or a subrule for it (e.g. ``/etc/apt/sources.list.d/postgres.list``) to contain the following:

.. code-block:: sh

  deb http://apt.postgresql.org/pub/repos/apt/ stretch-pgdg main

(Vary ``stretch-pgdg`` to ``jessie-pgdg``, ``wheezy-pgdg`` depending on your installation)

Once this is done, you must add the PostgreSQL key to apt and update your local package list.

.. code-block:: sh

  wget --quiet -O - https://www.postgresql.org/media/keys/ACCC4CF8.asc | apt-key add -
  apt update

Finally, we can install PostgreSQL:

.. code-block:: sh

  apt install postgresql-13

Now that PostgreSQL is installed, you can use ``sudo -u postgres -i psql`` to log in as the default PostgreSQL user.

Setup
+++++

To create a new database and user, use the following commands:

.. code-block:: sql

  CREATE ROLE myuser LOGIN PASSWORD 'mypassword';
  CREATE DATABASE mydb OWNER myuser;

(Substitute ``myuser``, ``mypassword`` and ``mydb`` with whatever names you wish to call them).

Once these commands have completed, type ``\c mydb myuser`` into psql. It will prompt you for the password, enter the one you just created.

Create a new suggestions table as in `schema.sql <https://github.com/BlobEmoji/queuebot/blob/master/schema.sql>`__.

In Linux you can do this quickly by doing ``psql -d mydb -U myuser < schema.sql`` on the command line.

Your setup for PostgreSQL is now done and you can log out of psql by typing ``\q``.

config.yaml
###########

A ``config.yaml`` file should be placed in the project root, alongside ``run.py``.

You can find an example of how to create this config by referencing `config.example.yaml <https://github.com/BlobEmoji/queuebot/blob/master/config.example.yaml>`__.

libuv
#####

On Linux, libuv can usually be installed on your respective package manager.

On Debian:

.. code-block:: sh

  apt install libuv0.10

On Arch:

.. code-block:: sh

  pacman -S libuv

On Windows, libuv builds can either be built manually or experimental builds installed from the `distribution index <https://dist.libuv.org/dist/>`__.

requirements.txt
################

First, create a virtualenv for this project (you can skip this step if you already have one or don't want one).

On Linux:

.. code-block:: sh

  python -m virtualenv venv
  source venv/bin/activate

On Windows:

.. code-block:: sh

  python -m virtualenv venv
  "venv\Scripts\activate.bat"

Then use pip to install the requirements:

.. code-block:: sh

  pip install -r requirements.txt

If you created a virtualenv, once you are done with it you can disable it using ``deactivate``.
