QueueBot
========

.. image:: https://img.shields.io/badge/python-3.6-blue.svg

.. image:: https://img.shields.io/badge/License-MIT-blue.svg
  :target: https://github.com/slice/queuebot/blob/master/LICENSE

QueueBot manages suggestion queueing and approval for the Google Emoji Discord guild.
It requires Python >=3.6 and the `discord.py@rewrite <https://github.com/Rapptz/discord.py/tree/rewrite/>`__ library.

It is not recommended to run an instance of this bot yourself. The code is here primarily for reference and bugfixing.


Prerequisites
-------------

This project has a number of requirements for deployment:

- ``git``, for acquiring ``discord.py@rewrite``
- A PostgreSQL >=10 server to store suggestion data
- A ``config.py`` file containing configuration data
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

PostgreSQL >=10
###############

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

  apt install postgresql-10

Now that PostgreSQL is installed, you can use ``sudo -u postgres -i psql`` to log in as the default PostgreSQL user.

Setup
+++++

To create a new database and user, use the following commands:

.. code-block:: sql

  CREATE ROLE myuser LOGIN PASSWORD 'mypassword';
  CREATE DATABASE mydb OWNER myuser;

(Substitute ``myuser``, ``mypassword`` and ``mydb`` with whatever names you wish to call them).

Once these commands have completed, type ``\c mydb myuser`` into psql. It will prompt you for the password, enter the one you just created.

Create a new suggestions table as in `schema.sql <https://github.com/slice/queuebot/blob/master/schema.sql>`__.

In Linux you can do this quickly by doing ``psql -d mydb -U myuser < schema.sql`` on the command line.

Your setup for PostgreSQL is now done and you can log out of psql by typing ``\q``.

config.py
#########

A ``config.py`` file should be placed in the project root, alongside ``run.py``.

Its basic structure is as follows:

.. code-block:: python

  token = "mytoken"

  pg_credentials = {
    "host": "localhost",
    "port": 5432,
    "user": "myuser",
    "database": "mydb",
    "password": "mypassword",
    "timeout": 60
  }

  bot_log = 1234567890  # replace this with the ID of your bot logging channel
  
  admins = [1234567890, 9876543210]  # add IDs of anyone who needs admin perms on this bot

  authority_roles = [1234567890, 9876543210]  # IDs of roles that have authority over this bot (Blob Police, etc)

  council_roles = [1234567890, 9876543210]  # IDs of roles considered Council (Blob Council, Blob Council Lite, etc)

  blob_guilds = [37428175841, ]  # IDs of all guilds the bot updates an emoji list in

  approve_emoji_id = 1234567890  # ID of the approval emoji
  deny_emoji_id = 1234567890  # ID of the denial emoji

  approve_emoji = "name:1234567890"  # representation of the approval emoji
  deny_emoji = "name:1234567890"  # representation of the denial emoji

  suggestions_channel = 1234567890  # ID of the suggestions channel
  council_queue = 1234567890  # ID of the council queue channel
  approval_queue = 1234567890  # ID of the approval queue channel

  suggestions_log = 1234567890  # ID of the suggestions log channel
  council_changelog = 1234567890  # ID of the council changelog channel

Substitute values here for your own.

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
