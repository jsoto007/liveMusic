"""Gunicorn entrypoint: `gunicorn wsgi:app`."""

from app import create_app

app = create_app()

if __name__ == "__main__":  # pragma: no cover - local convenience only
    app.run(host="127.0.0.1", port=5001, debug=True)
