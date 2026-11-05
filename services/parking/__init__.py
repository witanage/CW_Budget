"""
Parking QR notifier module.

Mounted inside the main Flask app at /park but isolated from the budget app:
own tables (park_*), own session keys (park_*), own templates (templates/park/).
See docs/PARKING_QR_PLAN.md.
"""

import getpass

import click
from werkzeug.security import generate_password_hash

from . import repository, validators
from .routes import create_blueprint


def register_parking_routes(app, limiter):
    app.register_blueprint(create_blueprint(limiter))

    @app.cli.command('park-init-db')
    def park_init_db():
        """Create the park_* tables (idempotent)."""
        repository.init_schema()
        click.echo('Parking tables are ready.')

    @app.cli.command('park-create-admin')
    @click.option('--mobile', prompt='Mobile number')
    @click.option('--name', prompt='Full name', default='')
    @click.option('--country', default=validators.DEFAULT_COUNTRY, show_default=True)
    def park_create_admin(mobile, name, country):
        """Create a parking back-office admin account."""
        mobile_e164 = validators.normalize_mobile(mobile, country)
        password = getpass.getpass('Password (min 8 chars): ')
        validators.validate_password(password)
        if password != getpass.getpass('Confirm password: '):
            raise click.ClickException('Passwords do not match.')
        uid = repository.create_user(name, country.upper(), mobile_e164,
                                     generate_password_hash(password), is_admin=True)
        click.echo(f'Admin created (id={uid}, mobile={mobile_e164}).')
