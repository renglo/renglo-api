"""
WSGI middleware to strip a configurable URL prefix from the request path.

Different deployment services add path segments before the application routes:
- API Gateway: xyz.execute-api.region.amazonaws.com/prod/_data/...
- Service A: someservice.com/x/y/_data/...
- Service B: anotherservice.io/x/k/q/w/_data/...

Set URL_PREFIX in your environment to strip the prefix before Flask routing.
Supports any depth:  "x/y", "x/k/q/w", etc.
"""

import os


def strip_url_prefix(app, url_prefix=None):
    """
    WSGI middleware that strips a configurable path prefix from PATH_INFO when present.

    Args:
        app: The WSGI application to wrap.
        url_prefix: Path prefix to strip
                    If None, reads from URL_PREFIX env var.
                    Leading/trailing slashes are normalized. When empty, no stripping occurs.

    Returns:
        Wrapped WSGI application.
    """
    raw = url_prefix if url_prefix is not None else os.environ.get("URL_PREFIX", "")
    prefix = raw.strip().strip("/")
    if not prefix:
        return app

    path_prefix = "/" + prefix
    path_prefix_slash = path_prefix + "/"

    def middleware(environ, start_response):
        path_info = environ.get("PATH_INFO", "")
        if path_info == path_prefix or path_info.startswith(path_prefix_slash):
            new_path = path_info[len(path_prefix) :] or "/"
            environ["PATH_INFO"] = new_path
        return app(environ, start_response)

    return middleware
