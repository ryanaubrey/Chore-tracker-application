from flask import Flask

from .config import configure, require_container_storage
from .database import build_engine, write_transaction
from .database.migrations import prepare_database
from .routes import web
from .services.invitations import initialize_setup


def create_app(config=None):
    app = Flask(__name__, static_folder=None)
    configure(app, config)
    app.register_blueprint(web)
    require_container_storage(app.config["DATABASE_URL"])
    engine = build_engine(app.config["DATABASE_URL"])
    app.extensions["chores_engine"] = engine
    prepare_database(engine)
    with app.app_context():
        with write_transaction() as db:
            initialize_setup(db, app.config["CHORES_SETUP_KEY"], app.config["CHORES_PUBLIC_URL"])
    return app
