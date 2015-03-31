from flask.ext.login import UserMixin
from sqlalchemy import func, Index
from werkzeug.security import check_password_hash, generate_password_hash

from qa_reporting import db


class User(UserMixin, db.Model):
    __tablename__ = 'user'
    __table_args__ = (
        Index('uix_user_email', func.lower('email'), unique=True),
    )

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column('email', db.String(128))
    password = db.Column('password', db.String(128))

    def __init__(self, email=None, password=None):
        self.email = email
        if password is not None:
            self.set_password(password)

    def set_password(self, password):
        self.password = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password, password)

    def __repr__(self):
        return '<User %r>' % (self.email)

    def __unicode__(self):
        return '%s' % (self.email)
