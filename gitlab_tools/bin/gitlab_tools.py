#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Main entry-point into the 'GitLab Tools' Flask application.

This is a GitLab Tools

License: GPL-3.0
Website: https://github.com/Salamek/gitlab-tools

Command details:
    server              Run the application using the Flask Development
                        Server. Auto-reloads files when they change.
    shell               Starts a Python interactive shell with the Flask
                        application context.
    create_all          Only create database tables if they don't exist and
                        then exit
    db                  Migrations
    list_routes         List all available routes
    post_install        Post install script
    celerybeat          Run a Celery Beat periodic task scheduler.
    celeryworker        Run a Celery worker process.
    celerydev           Starts a Celery worker with Celery Beat in the same
                        process.
    setup               Setup application

Usage:
    gitlab-tools server [-p NUM] [-l DIR] [--config_prod]
    gitlab-tools list_routes
    gitlab-tools shell [--config_prod]
    gitlab-tools create_all [--config_prod]
    gitlab-tools post_install [--config_prod] [--user=USER]
    gitlab-tools db [<action>] [<param1>] [--config_prod]
    gitlab-tools celerydev [-l DIR] [--config_prod]
    gitlab-tools celerybeat [-s FILE] [--pid=FILE] [-l DIR] [--config_prod]
    gitlab-tools celeryworker [-n NUM] [-l DIR] [--config_prod]
    gitlab-tools setup [--config_prod]
    gitlab-tools (-h | --help)

Options:
    --config_prod               Load the production configuration instead of
                                development.
    -l DIR --log_dir=DIR        Log all statements to file in this directory
                                instead of stdout.
                                Only ERROR statements will go to stdout. stderr
                                is not used.
    -n NUM --name=NUM           Celery Worker name integer.
                                [default: 1]
    --pid=FILE                  Celery Beat PID file.
                                [default: ./celery_beat.pid]
    -p NUM --port=NUM           Flask will listen on this port number.
    -s FILE --schedule=FILE     Celery Beat schedule database file.
                                [default: ./celery_beat.db]
"""

from __future__ import print_function

import logging
import logging.handlers
import os
import signal
import subprocess  # nosec B404
import sys
import tempfile
import urllib.parse
from functools import wraps

import flask
import yaml
from celery.app.log import Logging
from celery.utils.nodenames import default_nodename, host_format, node_format
from docopt import docopt
from flask_migrate import stamp


from gitlab_tools.application import create_app, get_config
from gitlab_tools.config import Config
from gitlab_tools.extensions import db, celery
from gitlab_tools.tools.crypto import random_password
from gitlab_tools.tools.helpers import get_home_dir, get_user_group_id, get_user_id, get_repository_storage, \
    get_ssh_storage

OPTIONS = docopt(__doc__)


class CustomFormatter(logging.Formatter):
    LEVEL_MAP = {logging.FATAL: 'F', logging.ERROR: 'E', logging.WARN: 'W', logging.INFO: 'I', logging.DEBUG: 'D'}

    def format(self, record):
        record.levelletter = self.LEVEL_MAP[record.levelno]
        return super().format(record)


def setup_logging(name: str=None, level: int=logging.DEBUG):
    """Setup Google-Style logging for the entire application.

    At first I hated this but I had to use it for work, and now I prefer it. Who knew?
    From: https://github.com/twitter/commons/blob/master/src/python/twitter/common/log/formatters/glog.py

    Always logs DEBUG statements somewhere.

    Positional arguments:
    name -- Append this string to the log file filename.
    """
    log_to_disk = False
    if OPTIONS['--log_dir']:
        if not os.path.isdir(OPTIONS['--log_dir']):
            print('ERROR: Directory {} does not exist.'.format(OPTIONS['--log_dir']))
            sys.exit(1)
        if not os.access(OPTIONS['--log_dir'], os.W_OK):
            print('ERROR: No permissions to write to directory {}.'.format(OPTIONS['--log_dir']))
            sys.exit(1)
        log_to_disk = True

    fmt = '%(levelletter)s%(asctime)s.%(msecs).03d %(process)d %(filename)s:%(lineno)d] %(message)s'
    datefmt = '%m%d %H:%M:%S'
    formatter = CustomFormatter(fmt, datefmt)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(console_handler)

    if log_to_disk:
        file_name = os.path.join(OPTIONS['--log_dir'], 'gitlab-tools_{}.log'.format(name))
        file_handler = logging.handlers.TimedRotatingFileHandler(file_name, when='d', backupCount=7)
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)


def log_messages(app):
    """Log messages common to Tornado and devserver."""
    log = logging.getLogger(__name__)
    log.info('Server is running at http://%s:%s/', app.config['HOST'], app.config['PORT'])
    log.info('Flask version: %s', flask.__version__)
    log.info('DEBUG: %s', app.config['DEBUG'])
    log.info('STATIC_FOLDER: %s', app.static_folder)


def parse_options() -> Config:
    """Parses command line options for Flask.

    Returns:
    Config instance to pass into create_app().
    """
    # Figure out which class will be imported.
    if OPTIONS['--config_prod']:
        config_class_string = 'gitlab_tools.config.Production'
    else:
        config_class_string = 'gitlab_tools.config.Config'
    config_obj = get_config(config_class_string)

    # Force port from commandline
    if OPTIONS['--port']:
        if not OPTIONS['--port'].isdigit():
            print('ERROR: Port should be a number.')
            sys.exit(1)
        config_obj.PORT = OPTIONS['--port']

    return config_obj


def command(name: str = None):
    """Decorator that registers the chosen command/function.

    If a function is decorated with @command but that function name is not a valid "command" according to the docstring,
    a KeyError will be raised, since that's a bug in this script.

    If a user doesn't specify a valid command in their command line arguments, the above docopt(__doc__) line will print
    a short summary and call sys.exit() and stop up there.

    If a user specifies a valid command, but for some reason the developer did not register it, an AttributeError will
    raise, since it is a bug in this script.

    Finally, if a user specifies a valid command and it is registered with @command below, then that command is "chosen"
    by this decorator function, and set as the attribute `chosen`. It is then executed below in
    `if __name__ == '__main__':`.

    Doing this instead of using Flask-Script.

    Positional arguments:
    func -- the function to decorate
    """

    def function_wrap(func):

        @wraps(func)
        def wrapped():
            return func()

        command_name = name if name else func.__name__

        # Register chosen function.
        if command_name not in OPTIONS:
            raise KeyError('Cannot register {}, not mentioned in docstring/docopt.'.format(command_name))
        if OPTIONS[command_name]:
            command.chosen = func

        return wrapped

    return function_wrap


@command()
def server() -> None:
    options = parse_options()
    setup_logging('server', logging.DEBUG if options.DEBUG else logging.WARNING)
    app = create_app(options)
    log_messages(app)
    app.run(host=app.config['HOST'], port=int(app.config['PORT']), debug=app.config['DEBUG'])


@command()
def create_all() -> None:
    setup_logging('create_all')
    app = create_app(parse_options())
    log = logging.getLogger(__name__)
    with app.app_context():
        tables_before = set(db.engine.table_names())
        db.create_all()
        tables_after = set(db.engine.table_names())
    created_tables = tables_after - tables_before
    for table in created_tables:
        log.info('Created table: %s', table)


@command()
def list_routes() -> None:
    output = []
    app = create_app(parse_options())
    app.config['SERVER_NAME'] = 'example.com'
    with app.app_context():
        for rule in app.url_map.iter_rules():

            integer_replaces = {}
            options = {}
            integer = 0
            for arg in rule.arguments:
                options[arg] = str(integer)
                integer_replaces[str(integer)] = "[{0}]".format(arg)
                integer = +1

            methods = ','.join(rule.methods)
            url = flask.url_for(rule.endpoint, **options)
            for integer_replace in integer_replaces:
                url = url.replace(integer_replace, integer_replaces[integer_replace])
            line = urllib.parse.unquote("{:50s} {:20s} {}".format(rule.endpoint, methods, url))
            output.append(line)

        for line in sorted(output):
            print(line)


@command()
def post_install() -> None:
    if not os.geteuid() == 0:
        sys.exit('Script must be run as root')

    app = create_app(parse_options())
    config_path = os.path.join('/', 'etc', 'gitlab-tools', 'config.yml')

    configuration = {}
    if os.path.isfile(config_path):
        with open(config_path) as f:
            loaded_data = yaml.load(f, Loader=yaml.SafeLoader)
            if isinstance(loaded_data, dict):
                configuration.update(loaded_data)

    if not configuration.get('USER') and OPTIONS['--user']:
        app.config['USER'] = configuration['USER'] = OPTIONS['--user']

    # Generate database and config if nothing is specified
    if 'SQLALCHEMY_DATABASE_URI' not in configuration or not configuration['SQLALCHEMY_DATABASE_URI']:

        database_path = 'sqlite:///{}/gitlab-tools.db'.format(get_home_dir(app.config['USER']))

        configuration['SQLALCHEMY_DATABASE_URI'] = database_path

        # We need to set DB config to make stamp work
        app.config['SQLALCHEMY_DATABASE_URI'] = configuration['SQLALCHEMY_DATABASE_URI']

        # Create empty database
        with app.app_context():
            db.create_all()

        with app.app_context():
            stamp()

        # Generate secret key
    if 'SECRET_KEY' not in configuration or not configuration['SECRET_KEY']:
        app.config['SECRET_KEY'] = configuration['SECRET_KEY'] = random_password()

    # Set port and host
    if 'HOST' not in configuration or not configuration['HOST']:
        configuration['HOST'] = '0.0.0.0'  # nosec B104

    if 'PORT' not in configuration or not configuration['PORT']:
        configuration['PORT'] = 80

    # Write new configuration
    with open(config_path, 'w') as f:
        yaml.dump(configuration, f, default_flow_style=False, allow_unicode=True)


@command()
def setup() -> None:
    # !FIXME this should be fixed...
    # pylint: disable=too-many-locals
    # pylint: disable=too-many-statements
    if not os.geteuid() == 0:
        sys.exit('Script must be run as root')

    app = create_app(parse_options())
    config_path = os.path.join('/', 'etc', 'gitlab-tools', 'config.yml')

    configuration = {}
    if os.path.isfile(config_path):
        with open(config_path) as f:
            loaded_data = yaml.safe_load(f)
            if isinstance(loaded_data, dict):
                configuration.update(loaded_data)

    def required_input(text):
        return input(text) or required_input(text)

    def database_sqlite():
        print('SQLite configuration:')

        home_dir = get_home_dir(configuration['USER'])
        database_path_default = os.path.join(home_dir, 'gitlab-tools.db')
        connection_info = urllib.parse.urlparse(
            configuration.get('SQLALCHEMY_DATABASE_URI', 'sqlite:///{}'.format(database_path_default))
        )

        if connection_info.scheme == 'sqlite':
            database_path = os.path.join('/', connection_info.path.lstrip('/'))
        else:
            database_path = database_path_default

        database_location = input('Location [{}]: '.format(database_path)) or database_path
        database_config_uri = 'sqlite:///{}'.format(database_location)

        app.config['SQLALCHEMY_DATABASE_URI'] = database_config_uri
        configuration['SQLALCHEMY_DATABASE_URI'] = database_config_uri

    def database_mysql():
        print('MySQL configuration:')
        database_login('mysql')

    def database_postgresql():
        print('PostgreSQL configuration:')
        database_login('postgresql')

    def database_login(database_type):

        connection_info = urllib.parse.urlparse(
            configuration.get(
                'SQLALCHEMY_DATABASE_URI',
                '{}://gitlab-tools:password@127.0.0.1/gitlab-tools'.format(database_type)
            )
        )

        if connection_info.scheme == database_type:
            database_name = connection_info.path
            database_server = connection_info.netloc
            database_user = connection_info.username
            database_password = connection_info.password
        else:
            database_name = 'gitlab-tools'
            database_server = '127.0.0.1'
            database_user = 'gitlab-tools'
            database_password = None

        database_server = input('Server [{}]: '.format(database_server)) or database_server
        database_name = input('Database [{}]: '.format(database_name)) or database_name
        database_user = input('User [{}]: '.format(database_user)) or database_user
        if not database_password:
            database_password = required_input('Password (required):')
        else:
            database_password = input('Password [{}]: '.format('*' * len(database_password))) or database_password

        app.config['SQLALCHEMY_DATABASE_URI'] = configuration['SQLALCHEMY_DATABASE_URI'] = '{}://{}:{}@{}/{}'.format(
            database_type,
            database_user,
            database_password,
            database_server,
            database_name
        )

    def ignore():
        pass

    print('Default application user (must exists):')
    default_user = configuration.get('USER', app.config.get('USER'))
    app.config['USER'] = configuration['USER'] = input('[{}]: '.format(default_user)) or default_user

    # Check if repository storage directory exists
    repository_storage_path = get_repository_storage(app.config['USER'])
    if not os.path.isdir(repository_storage_path):
        print('Creating {}'.format(repository_storage_path))
        os.mkdir(repository_storage_path)

    os.chown(repository_storage_path, get_user_id(app.config['USER']), get_user_group_id(app.config['USER']))

    # Check if ssh storage directory exists
    ssh_storage_path = get_ssh_storage(app.config['USER'])
    if not os.path.isdir(ssh_storage_path):
        print('Creating {}'.format(ssh_storage_path))
        os.mkdir(ssh_storage_path)

    os.chown(ssh_storage_path, get_user_id(app.config['USER']), get_user_group_id(app.config['USER']))

    database_types = {
        0: {'name': 'Ignore', 'default': True, 'call': ignore},
        1: {'name': 'SQLite', 'default': False, 'call': database_sqlite},
        2: {'name': 'PostgreSQL [Recommended]', 'default': False, 'call': database_postgresql},
        3: {'name': 'MySQL', 'default': False, 'call': database_mysql},
    }

    print('Choose database type you want to use:')
    db_type_default = None
    for db_type in database_types:
        if database_types[db_type]['default']:
            db_type_default = db_type
        print('{}) {}{}'.format(
            db_type,
            database_types[db_type]['name'],
            ' (default)' if database_types[db_type]['default'] else '')
        )

    database_type = int(input('Database type [{}]: '.format(db_type_default)) or db_type_default)
    if database_type not in database_types:
        print('Invalid option selected')
        sys.exit(1)

    database_types[database_type]['call']()

    print('Webserver configuration:')
    webserver_host = configuration.get('HOST', '127.0.0.1')
    webserver_port = configuration.get('PORT', '80')
    configuration['HOST'] = input('Host (for integrated web server - when used) [{}]: '.format(webserver_host)) or webserver_host
    configuration['PORT'] = input('Port (for integrated web server - when used) [{}]: '.format(webserver_port)) or webserver_port
    server_name = '{}:{}'.format(configuration['HOST'], configuration['PORT'])
    configuration['SERVER_NAME'] = input(
        'Server name (on what domain or ip+port is this application available) [{}]: '.format(server_name)
    ) or server_name

    print('Gitlab configuration:')
    default_gitlab_url = configuration.get('GITLAB_URL', 'https://gitlab.com')
    default_gitlab_app_id = configuration.get('GITLAB_APP_ID')
    default_gitlab_app_secret = configuration.get('GITLAB_APP_SECRET')
    default_gitlab_ssh = configuration.get('GITLAB_SSH', 'gitlab.com:22')
    configuration['GITLAB_URL'] = input('Gitlab URL [{}]:'.format(default_gitlab_url)) or default_gitlab_url
    configuration['GITLAB_SSH'] = input('Gitlab URL [{}]:'.format(default_gitlab_ssh)) or default_gitlab_ssh
    configuration['GITLAB_APP_ID'] = input('Gitlab APP ID [{}]:'.format(default_gitlab_app_id)) or default_gitlab_app_id
    configuration['GITLAB_APP_SECRET'] = input(
        'Gitlab APP SECRET [{}]:'.format(default_gitlab_app_secret)
    ) or default_gitlab_app_secret

    print('Save new configuration ?')

    for item in configuration:
        print('{}: {}'.format(item, configuration[item]))

    save_configuration = input('Save ? (y/n) [y]: ') or 'y'
    if save_configuration == 'y':
        # Write new configuration
        with open(config_path, 'w') as f:
            yaml.dump(configuration, f, default_flow_style=False, allow_unicode=True)

        print('Configuration saved.')

    recreate_database = input('Recreate database ? (y/n) [n]: ') or 'n'
    if recreate_database == 'y':
        # Create empty database
        with app.app_context():

            # Create tables
            db.create_all()

            # Since we are running this script as root,
            # make sure that SQlite database (if used) is writable by application user
            database_configuration_info = urllib.parse.urlparse(
                configuration.get('SQLALCHEMY_DATABASE_URI')
            )

            if database_configuration_info.scheme == 'sqlite':
                os.chown(database_configuration_info.path, get_user_id(app.config['USER']), get_user_group_id(app.config['USER']))

            # Stamp database to lates migration
            stamp()

            print('Database has been created')

    restart_services = input('Restart services to load new configuration ? (y/n) [n]: ') or 'n'
    if restart_services == 'y':
        subprocess.call(['systemctl', 'restart', 'gitlab-tools_celeryworker'])  # nosec B607, B603
        subprocess.call(['systemctl', 'restart', 'gitlab-tools_celerybeat'])  # nosec B607, B603
        subprocess.call(['systemctl', 'restart', 'gitlab-tools'])  # nosec B607, B603


@command()
def celerydev():
    options = parse_options()
    setup_logging('celerydev', logging.DEBUG if options.DEBUG else logging.WARNING)
    Logging._setup = True
    app = create_app(options, no_sql=True)
    with app.app_context():
        hostname = OPTIONS['--name'] if OPTIONS['--name'] else host_format(default_nodename(None))
        worker = celery.Worker(
            hostname=hostname, pool_cls=None, loglevel='WARNING',
            logfile=None,  # node format handled by celery.app.log.setup
            pidfile=node_format(None, hostname),
            statedb=node_format(None, hostname),  # ctx.obj.app.conf.worker_state_db
            no_color=False,
            concurrency=5,
            schedule=os.path.join(tempfile.gettempdir(), 'celery.db'),
            beat=True

        )
        worker.start()
        return worker.exitcode


@command()
def celerybeat():
    options = parse_options()
    setup_logging('celerybeat', logging.DEBUG if options.DEBUG else logging.WARNING)
    Logging._setup = True
    app = create_app(options)
    with app.app_context():
        return celery.Beat(
            logfile=None,
            pidfile=OPTIONS['--pid'],
            schedule=OPTIONS['--schedule']
        ).run()


@command()
def celeryworker():
    options = parse_options()
    setup_logging('celeryworker{}'.format(OPTIONS['--name']), logging.DEBUG if options.DEBUG else logging.WARNING)
    Logging._setup = True
    app = create_app(options, no_sql=True)
    with app.app_context():
        hostname = OPTIONS['--name'] if OPTIONS['--name'] else host_format(default_nodename(None))
        worker = celery.Worker(
            hostname=hostname, pool_cls=None, loglevel='WARNING',
            logfile=None,  # node format handled by celery.app.log.setup
            pidfile=node_format(None, hostname),
            statedb=node_format(None, hostname),  # ctx.obj.app.conf.worker_state_db
            no_color=False,
            autoscale='10,1',
            without_gossip=True

        )
        worker.start()
        return worker.exitcode


@command(name='db')
def _db():
    from flask.cli import FlaskGroup # pylint: disable=import-outside-toplevel
    cli = FlaskGroup(create_app=lambda: create_app(parse_options()))
    cli.main(args=sys.argv[1:])


def main() -> None:
    signal.signal(signal.SIGINT, lambda *_: sys.exit(0))  # Properly handle Control+C
    getattr(command, 'chosen')()  # Execute the function specified by the user.


if __name__ == '__main__':
    main()
