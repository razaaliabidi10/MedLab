from functools import wraps
from flask import abort
from flask_login import UserMixin, current_user
from db import query_db


class User(UserMixin):
    def __init__(self, row):
        self.id = row["user_id"]
        self.email = row["email"]
        self.full_name = row["full_name"]
        self.phone = row["phone"]
        self.role_id = row["role_id"]
        self.role_name = row.get("role_name", "")
        self.avatar_url = row.get("avatar_url", "default_avatar.png")
        self.is_active_flag = bool(row.get("is_active", True))
        self.must_change_password = bool(row.get("must_change_password", False))

    def get_id(self):
        return str(self.id)

    @property
    def is_active(self):
        return self.is_active_flag

    @property
    def is_admin(self):
        return self.role_id == 1

    @property
    def is_receptionist(self):
        return self.role_id == 2

    @property
    def is_technician(self):
        return self.role_id == 3

    @property
    def is_patient(self):
        return self.role_id == 4

    @property
    def is_collector(self):
        return self.role_id == 5

    @property
    def is_pathologist(self):
        return self.role_id == 6

    @staticmethod
    def load(user_id):
        row = query_db(
            "SELECT u.*, r.role_name FROM users u JOIN roles r ON u.role_id=r.role_id "
            "WHERE u.user_id=%s",
            (user_id,), one=True
        )
        if not row or not row.get("is_active", True):
            return None
        return User(row)


def role_required(*roles):
    """Decorator: abort 403 if current_user.role_id not in roles."""
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if current_user.role_id not in roles:
                abort(403)
            return f(*args, **kwargs)
        return wrapped
    return decorator
