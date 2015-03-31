from flask import Flask
from flask.ext.login import LoginManager
from flask.ext.migrate import Migrate
from flask.ext.script import Manager
from flask.ext.sqlalchemy import SQLAlchemy


app = Flask(__name__)
app.config.from_object('config')

db = SQLAlchemy(app)
migrate = Migrate(app, db)

manager = Manager(app)

login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'info'


from qa_reporting import models, views
