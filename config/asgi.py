"""
ASGI config for core project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/asgi/
"""

import os
import django
from django.db import close_old_connections
from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

class DBConnectionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        close_old_connections()
        try:
            return await call_next(request)
        finally:
            close_old_connections()

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

django.setup()

from django.conf import settings
from django.core.asgi import get_asgi_application

STATIC_DIR = settings.BASE_DIR / "static"

django_app = get_asgi_application()

from api import web_api

web_api.add_middleware(DBConnectionMiddleware)

application = Starlette(
    routes=[
        Mount("/api", app=web_api),
        Mount("/admin", app=django_app),
        Mount(
            "/",
            app=StaticFiles(directory=STATIC_DIR, html=True, check_dir=False),
            name="static",
        ),
    ]
)