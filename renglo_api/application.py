"""
Production WSGI entrypoint for Renglo API.

Use with gunicorn/uwsgi and lambda adapters.
"""

from renglo_api.app import create_host_app

app = create_host_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
