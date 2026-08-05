"""ASGI entry point without import-time network access."""

from composition import create_application

app = create_application()

__all__ = ["app"]
