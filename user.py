# user.py

from flask_login import UserMixin

class User(UserMixin):
    def __init__(self, id, username, email, role='user'):
        self.id = id
        self.username = username
        self.email = email
        self.role = role  # store role from DB: 'admin' or 'user'

    def get_id(self):
        return str(self.id)

    @property
    def is_admin(self):
        return self.role == 'admin'
