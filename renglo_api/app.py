"""
Renglo API - Flask application factory
"""

from flask import Flask, jsonify, request, session, g
from flask_caching import Cache
from flask_cors import CORS
from flask_cognito import CognitoAuth, cognito_auth_required
import logging
import time
import os
import sys
from pathlib import Path
from renglo_api.apigw_stage_middleware import strip_url_prefix
from renglo_api.config import load_env_config


def create_app(config=None, config_path=None):
    """
    Factory function to create and configure the Flask app.
    Can be imported and run from anywhere.
    
    Args:
        config (dict): Configuration dictionary to use. If provided, takes precedence.
        config_path (str): Path to env_config.py file. If not provided, looks in current directory.
    
    Usage:
        # Option 1: Pass config dict directly (recommended for production)
        app = create_app(config={'DYNAMODB_CHAT_TABLE': 'prod_chat', ...})
        
        # Option 2: Load from env_config.py in current directory
        app = create_app()
        
        # Option 3: Load from specific path
        app = create_app(config_path='/path/to/env_config.py')
    """
    # static_url_path must not be '/': a root catch-all <path:filename> would match
    # every path (e.g. /_files/...), miss the file, 404, and the global 404 handler would run.
    app = Flask(__name__, 
                static_folder='../static/dist',
                static_url_path='/_st')
    
    # Load environment-specific config if not provided directly
    if config is None:
        env_config = load_env_config(config_path)
        app.config.update(env_config)
    else:
        # Use provided config directly
        app.config.update(config)
    
    # Make config available for controller instantiation
    app.renglo_config = dict(app.config)
    
    # Setup cache
    cache = Cache(app)
    app.cache = cache
    
    # Set up logging
    logging.basicConfig(level=logging.INFO)
    logging.getLogger('zappa').setLevel(logging.WARNING)
    app.logger.info(f'Python Version: {sys.version}')
    
    # Determine if the app is running on AWS Lambda or locally
    if os.getenv('AWS_LAMBDA_FUNCTION_NAME'):
        app.config['IS_LAMBDA'] = True
    else:
        app.config['IS_LAMBDA'] = False
    
    # Setup CORS based on environment
    if app.config['IS_LAMBDA']:
        app.logger.info('RUNNING ON LAMBDA ENVIRONMENT')
        app.logger.info('BASE_URL:' + str(app.config.get('BASE_URL', 'NOT SET')))
        app.logger.info('FE_BASE_URL:' + str(app.config.get('FE_BASE_URL', 'NOT SET')))
        
        # Build origins list safely - PRODUCTION ONLY
        renglo_fe_url = app.config.get('FE_BASE_URL', '').rstrip('/')
        origins = [renglo_fe_url] if renglo_fe_url else []
        
        # Add APP_FE_BASE_URL if it exists in config
        if 'APP_FE_BASE_URL' in app.config and app.config['APP_FE_BASE_URL']:
            app.logger.info('APP_FE_BASE_URL:' + str(app.config['APP_FE_BASE_URL']))
            origins.append(app.config['APP_FE_BASE_URL'])
        
        # Add development origins only if explicitly enabled
        if app.config.get('ALLOW_DEV_ORIGINS', False):
            app.logger.warning('DEVELOPMENT ORIGINS ENABLED - NOT RECOMMENDED FOR PRODUCTION')
            origins.extend([
                "http://127.0.0.1:5173",
                "http://127.0.0.1:5174",
                "http://127.0.0.1:3000",
                "http://localhost:3000"
            ])
        
        app.logger.info(f'CORS Origins configured: {origins}')
        CORS(
            app,
            resources={r"*": {"origins": origins}},
            supports_credentials=False,
            methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            expose_headers=["*"],
            allow_headers="*"
        )
    else:
        app.logger.info('RUNNING ON LOCAL ENVIRONMENT')
        origins = [
            "http://127.0.0.1:5173",
            "http://127.0.0.1:5174",
            "http://127.0.0.1:3000",
            "http://localhost:3000",
        ]
        renglo_fe_url = str(app.config.get('FE_BASE_URL') or '').rstrip('/')
        if renglo_fe_url and renglo_fe_url not in origins:
            origins.append(renglo_fe_url)
        app_fe_url = str(app.config.get('APP_FE_BASE_URL') or '').rstrip('/')
        if app_fe_url and app_fe_url not in origins:
            origins.append(app_fe_url)
        app.logger.info(f'CORS Origins configured: {origins}')
        CORS(app, resources={r"/*": {"origins": origins}})
    
    # Initialize CognitoAuth
    cognito = CognitoAuth(app)
    
    # Register blueprints (routes)
    from renglo_api.routes.auth_routes import app_auth
    from renglo_api.routes.data_routes import app_data
    from renglo_api.routes.search_routes import app_search
    from renglo_api.routes.graph_routes import app_graph
    from renglo_api.routes.vector_routes import app_vector
    from renglo_api.routes.rag_routes import app_rag
    from renglo_api.routes.blueprint_routes import app_blueprint
    from renglo_api.routes.files_routes import app_files
    from renglo_api.routes.schd_routes import app_schd
    from renglo_api.routes.chat_routes import app_chat
    from renglo_api.routes.state_routes import app_state
    from renglo_api.routes.session_routes import app_session

    app.register_blueprint(app_data)
    app.register_blueprint(app_search)
    app.register_blueprint(app_graph)
    app.register_blueprint(app_vector)
    app.register_blueprint(app_rag)
    app.register_blueprint(app_blueprint)
    app.register_blueprint(app_auth)
    app.register_blueprint(app_files)
    app.register_blueprint(app_schd)
    app.register_blueprint(app_chat)
    app.register_blueprint(app_state)
    app.register_blueprint(app_session)
    
    # Template Filters
    @app.template_filter()
    def diablify(string):
        return '666' + str(string)
    
    @app.template_filter()
    def nonone(val):
        if not val is None:
            return val
        else:
            return ''
    
    @app.template_filter()
    def is_list(val):
        return isinstance(val, list)
    
    # Unmatched route / true 404 — do not return 301 (bad for APIs and browser caching).
    @app.errorhandler(404)
    def not_found(error):
        renglo_fe_url = app.config.get('FE_BASE_URL', '')
        return jsonify({'error': f'Not found. FE: {renglo_fe_url}'}), 404
    
    # Basic routes
    @app.route('/')
    def index():
        app.logger.info('Hitting the root')
        try:
            return app.send_static_file('index.html')
        except:
            return jsonify({'message': 'Renglo API is running', 'version': '1.0.0'}), 200
    
    @app.route('/time')
    @cognito_auth_required
    def get_current_time():
        return {'time': time.time()}
    
    @app.route('/timex')
    def get_current_timex():
        session['current_user'] = '7e5fb15bb'
        return {'time': time.time()}
    
    @app.route('/ping')
    def ping():
        app.logger.info("Ping!: %s", time.time())
        return {
            'pong': True,
            'time': time.time(),
        }
    
    @app.route('/message', methods=['POST'])
    def real_time_message():
        app.logger.info("WEBSOCKET MESSAGE!: %s", time.time())
        payload = request.get_json()
        app.logger.info(payload)
        return {
            'ws': True,
            'time': time.time(),
            'input': payload,
        }
    
    return app


def create_host_app(config=None, config_path=None, with_stage_prefix_middleware=True):
    """
    Build the host-facing WSGI app used by gunicorn/lambda.

    This wraps the API app with API Gateway stage-prefix stripping middleware
    when requested.
    """
    host_app = create_app(config=config, config_path=config_path)
    if with_stage_prefix_middleware:
        host_app = strip_url_prefix(host_app)
    return host_app


_SKIP_RELOAD_DIR_NAMES = frozenset(
    {".venv", "venv", "node_modules", "__pycache__", ".git", "site-packages"}
)


def _workspace_root() -> Path | None:
    """Workspace root (contains dev/ and extensions/)."""
    env_root = os.getenv("RENGLO_WORKSPACE_ROOT", "").strip()
    if env_root:
        candidate = Path(env_root).expanduser().resolve()
        if (candidate / "extensions").is_dir() and (candidate / "dev").is_dir():
            return candidate

    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "extensions").is_dir() and (parent / "dev").is_dir():
            return parent

    config_path = os.getenv("RENGLO_CONFIG_PATH", "").strip()
    if config_path:
        cfg = Path(config_path).expanduser()
        if not cfg.is_absolute():
            cfg = (Path.cwd() / cfg).resolve()
        else:
            cfg = cfg.resolve()
        for parent in cfg.parents:
            if (parent / "extensions").is_dir() and (parent / "dev").is_dir():
                return parent

    for parent in Path.cwd().resolve().parents:
        if (parent / "extensions").is_dir() and (parent / "dev").is_dir():
            return parent

    return None


def _should_skip_reload_path(path: Path) -> bool:
    parts = set(path.parts)
    if parts & _SKIP_RELOAD_DIR_NAMES:
        return True
    if path.name in {"docs", "build"}:
        return True
    text = str(path)
    if "/build/lib/" in text:
        return True
    return False


def _add_reload_root(seen: set[str], roots: list[str], path: Path) -> None:
    if not path.is_dir() or _should_skip_reload_path(path):
        return
    key = str(path.resolve())
    if key not in seen:
        seen.add(key)
        roots.append(key)


def _editable_install_roots() -> list[str]:
    """Discover source directories from pip editable (__editable__.*.pth) installs."""
    import ast
    import re
    import site

    seen: set[str] = set()
    roots: list[str] = []

    site_dirs = []
    try:
        site_dirs.extend(site.getsitepackages())
    except Exception:
        pass
    try:
        user_site = site.getusersitepackages()
        if user_site:
            site_dirs.append(user_site)
    except Exception:
        pass

    dict_pattern = re.compile(
        r"(MAPPING|NAMESPACES):\s*dict\[str,\s*[^\]]+\]\s*=\s*(\{.*?\})\n",
        re.DOTALL,
    )

    for site_dir in site_dirs:
        site_path = Path(site_dir)
        if not site_path.is_dir():
            continue
        for finder_path in site_path.glob("__editable___*_finder.py"):
            try:
                text = finder_path.read_text(encoding="utf-8")
            except OSError:
                continue
            for match in dict_pattern.finditer(text):
                label, blob = match.group(1), match.group(2)
                try:
                    data = ast.literal_eval(blob)
                except (SyntaxError, ValueError):
                    continue
                if label == "MAPPING":
                    values = data.values()
                else:
                    values = (
                        path
                        for paths in data.values()
                        for path in paths
                    )
                for value in values:
                    _add_reload_root(seen, roots, Path(value))

    return roots


def _workspace_reload_roots(workspace: Path) -> list[str]:
    seen: set[str] = set()
    roots: list[str] = []

    for relative in (
        Path("dev/renglo-api/renglo_api"),
        Path("dev/renglo-lib/renglo"),
    ):
        _add_reload_root(seen, roots, workspace / relative)

    extensions = workspace / "extensions"
    if extensions.is_dir():
        for ext_dir in sorted(extensions.iterdir()):
            if not ext_dir.is_dir():
                continue
            package = ext_dir / "package"
            if package.is_dir():
                _add_reload_root(seen, roots, package)

    return roots


def _collect_reload_extra_files(debug: bool) -> tuple[list[str], list[str]]:
    """Return (watch_roots, individual_files) for Werkzeug auto-reload."""
    if not debug:
        return [], []

    seen: set[str] = set()
    roots: list[str] = []

    api_root = Path(__file__).resolve().parent.parent
    _add_reload_root(seen, roots, api_root / "renglo_api")

    workspace = _workspace_root()
    if workspace:
        for root in _workspace_reload_roots(workspace):
            _add_reload_root(seen, roots, Path(root))

    for root in _editable_install_roots():
        _add_reload_root(seen, roots, Path(root))

    files: list[str] = []
    config_path = os.getenv("RENGLO_CONFIG_PATH")
    if config_path:
        cfg = Path(config_path).expanduser()
        if not cfg.is_absolute():
            cfg = (Path.cwd() / cfg).resolve()
        else:
            cfg = cfg.resolve()
        if cfg.is_file():
            files.append(str(cfg))

    if workspace:
        extensions = workspace / "extensions"
        if extensions.is_dir():
            for ext_dir in extensions.iterdir():
                handlers_cfg = ext_dir / "package" / "handlers_config.json"
                if handlers_cfg.is_file():
                    files.append(str(handlers_cfg.resolve()))

    return roots, files


def _format_reload_root(root: str, workspace: Path | None) -> str:
    path = Path(root)
    if workspace:
        try:
            return str(path.relative_to(workspace))
        except ValueError:
            pass
    return root


def _reloader_type() -> str:
    try:
        import watchdog  # noqa: F401

        return "watchdog"
    except ImportError:
        return "stat"


def run(host='0.0.0.0', port=5000, debug=True, config=None, config_path=None):
    """
    Convenience function to run the app for local development.
    """
    app = create_host_app(
        config=config,
        config_path=config_path,
        with_stage_prefix_middleware=False,
    )
    extra_roots, extra_files = _collect_reload_extra_files(debug)
    extra_watch = extra_roots + extra_files
    run_kwargs = {
        "host": host,
        "port": port,
        "debug": debug,
        "use_reloader": debug,
        "use_debugger": debug,
    }
    if debug:
        run_kwargs["reloader_type"] = _reloader_type()
        if extra_watch:
            run_kwargs["extra_files"] = extra_watch
            workspace = _workspace_root()
            app.logger.info(
                "Dev auto-reload (%s) watching %s roots and %s files",
                run_kwargs["reloader_type"],
                len(extra_roots),
                len(extra_files),
            )
            for root in extra_roots:
                app.logger.info("  reload root: %s", _format_reload_root(root, workspace))
            for path in extra_files:
                app.logger.info("  reload file: %s", _format_reload_root(path, workspace))
    app.run(**run_kwargs)


# For Zappa deployment - create app instance at module level
app = create_host_app()

