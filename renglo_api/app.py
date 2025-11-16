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
    # Define the WSGI application object
    app = Flask(__name__, 
                static_folder='../static/dist',
                static_url_path='/')
    
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
                "http://127.0.0.1:3000"
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
        CORS(app, resources={r"/*": {
            "origins": [
                "http://127.0.0.1:5173",
                "http://127.0.0.1:5174",
                "http://127.0.0.1:3000"
            ]
        }})
    
    # Initialize CognitoAuth
    cognito = CognitoAuth(app)
    
    # Register blueprints (routes)
    from renglo_api.routes.auth_routes import app_auth
    from renglo_api.routes.data_routes import app_data
    from renglo_api.routes.blueprint_routes import app_blueprint
    from renglo_api.routes.docs_routes import app_docs
    from renglo_api.routes.schd_routes import app_schd
    from renglo_api.routes.chat_routes import app_chat
    from renglo_api.routes.state_routes import app_state
    
    app.register_blueprint(app_data)
    app.register_blueprint(app_blueprint)
    app.register_blueprint(app_auth)
    app.register_blueprint(app_docs)
    app.register_blueprint(app_schd)
    app.register_blueprint(app_chat)
    app.register_blueprint(app_state)
    
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
    
    # Error handler for 404
    @app.errorhandler(404)
    def not_found(error):
        renglo_fe_url = app.config.get('FE_BASE_URL', 'https://your-frontend-url.com')
        return jsonify({'error': f'Static site has moved, go to: {renglo_fe_url}'}), 301
    
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


def run(host='0.0.0.0', port=5000, debug=True):
    """
    Convenience function to run the app for local development.
    """
    app = create_app()
    app.run(host=host, port=port, debug=debug)


# For Zappa deployment - create app instance at module level
app = create_app()

