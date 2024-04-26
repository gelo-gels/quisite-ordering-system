import os
import sqlite3
from .math import distance_between_locations
from flask import Flask, g

sqlite3.enable_callback_tracebacks(True)

# Adjust the path to your database file accordingly
DATABASE = os.path.join(os.path.dirname(__file__), "../HWDB.db")
SCHEMA = os.path.join(os.path.dirname(__file__), "../schema.sql")

# distance boundary
DISTANCE_BOUNDARY = {'medium': 200, 'far': 600}

app = Flask(__name__, template_folder='../templates', static_folder='../static')
app.config['SECRET_KEY'] = os.urandom(99)

def get_db():
    '''
    helper function to get database connection
    '''
    db = getattr(g, '_database', None)
    if db is None:
        db = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
        db.create_function('_GIO_DIS', 4, distance_between_locations)
        g._database = db
    db.cursor().execute("PRAGMA foreign_keys=ON")
    return db

@app.teardown_appcontext
def close_connection(exception):
    '''
    close database after session ends
    '''
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    '''
    initialize database
    '''
    with app.app_context():
        db = get_db()
        try:
            with app.open_resource(SCHEMA, mode='r') as f:
                db.cursor().executescript(f.read())  # executescript can run multiple commands
            db.commit()
        except sqlite3.Error as e:
            print("Error initializing database:", e)

    from .login import user # Adjust the import path according to your project structure
    app.register_blueprint(user)

    from .views import main  # Adjust the import path according to your project structure
    app.register_blueprint(main, url_prefix="/")

    from .admin import manager # Adjust the import path according to your project structure
    app.register_blueprint(manager)

    from .user import costumer # Adjust the import path according to your project structure
    app.register_blueprint(costumer)

    return app

@app.errorhandler(Exception)
def all_exception_handler(error):
    print("**all_exception_handler**")
    print(error)
    return "invalid", 500
