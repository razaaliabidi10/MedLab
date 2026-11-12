"""
extensions.py
=============
Centralized Flask extensions instances.
Decoupled from app.py to eliminate circular imports during blueprint loading.
"""

from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

login_manager = LoginManager()
csrf = CSRFProtect()
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],
    storage_uri="memory://"
)
