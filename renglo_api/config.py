"""
Configuration management for Renglo API.

This module provides utilities for loading and managing configuration
that can be injected into renglo controllers.
"""

import importlib.util
import os
import sys


def _load_config_module_from_path(config_path):
    spec = importlib.util.spec_from_file_location("env_config", config_path)
    env_config = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(env_config)
    return env_config


def load_env_config(config_path=None):
    """
    Load environment configuration from env_config.py and/or environment variables.
    Returns a dictionary of configuration values.
    
    This allows renglo-lib (which is framework-agnostic) to receive config
    via constructor injection rather than importing it directly.
    
    Args:
        config_path (str): Optional path to config module. If not provided,
                          uses RENGLO_CONFIG_PATH when set, otherwise looks
                          in current working directory.
    
    Priority:
        1. Load from env_config.py file (if available)
        2. Override with environment variables (for Lambda/Docker)
        3. Environment variables take precedence
    """
    config = {}
    
    resolved_config_path = config_path or os.getenv("RENGLO_CONFIG_PATH")

    # Try to load from explicit path first
    try:
        if resolved_config_path:
            env_config = _load_config_module_from_path(resolved_config_path)
        elif os.path.exists(os.path.join(os.getcwd(), "env_config.py")):
            env_config = _load_config_module_from_path(os.path.join(os.getcwd(), "env_config.py"))
        else:
            env_config = None

        if env_config:
            # Extract all uppercase variables (convention for config constants)
            for key in dir(env_config):
                if key.isupper() and not key.startswith('_'):
                    config[key] = getattr(env_config, key)
                
    except ImportError:
        print("Info: Using environment variables", file=sys.stderr)
    except Exception as e:
        source = resolved_config_path or os.path.join(os.getcwd(), "env_config.py")
        print(f"Warning: Error loading config from {source}: {e}", file=sys.stderr)
    
    # Load from environment variables (takes precedence over file)
    # This is critical for Lambda/Docker deployments
    env_var_keys = [
        'WL_NAME', 'BASE_URL', 'FE_BASE_URL', 'DOC_BASE_URL',
        'APP_FE_BASE_URL', 'API_GATEWAY_ARN', 'ROLE_ARN', 'SYS_ENV',
        'DYNAMODB_ENTITY_TABLE', 'DYNAMODB_BLUEPRINT_TABLE', 
        'DYNAMODB_RINGDATA_TABLE', 'DYNAMODB_REL_TABLE', 'DYNAMODB_CHAT_TABLE',
        'DYNAMODB_SESSION_TABLE', 'DYNAMODB_SEARCH_TABLE', 'DYNAMODB_GRAPH_TABLE',
        'GRAPH_DB_ENABLED',
        'CSRF_SESSION_KEY', 'SECRET_KEY',
        'COGNITO_REGION', 'COGNITO_USERPOOL_ID', 'COGNITO_APP_CLIENT_ID',
        'COGNITO_CHECK_TOKEN_EXPIRATION',
        'PREVIEW_LAYER', 'S3_BUCKET_NAME',
        'OPENAI_API_KEY', 'WEBSOCKET_CONNECTIONS', 'ALLOW_DEV_ORIGINS',
        'AGENT_API_OUTPUT', 'AGENT_API_HANDLER', 'EXTERNAL_HANDLERS',
        'OPENSEARCH_ENDPOINT', 'OPENSEARCH_INDEX', 'OPENSEARCH_REFRESH'
    ]
    
    for key in env_var_keys:
        if key in os.environ:
            config[key] = os.environ[key]
    
    return config


def get_config_for_flask(app):
    """
    Get configuration dict suitable for injecting into renglo controllers
    when running in Flask context.
    
    Args:
        app: Flask application instance
        
    Returns:
        dict: Configuration dictionary
    """
    # In Flask, we can merge Flask config with env_config
    config = load_env_config()
    
    # Flask config takes precedence
    config.update(app.config)
    
    return config


def get_config_for_lambda():
    """
    Get configuration dict suitable for injecting into renglo controllers
    when running in AWS Lambda context.
    
    For Lambda, configuration typically comes from:
    1. Environment variables
    2. env_config.py if deployed with the function
    
    Returns:
        dict: Configuration dictionary
    """
    config = load_env_config()
    
    # Override with environment variables if set
    # This allows Lambda environment variables to override file-based config
    env_var_keys = [
        'DYNAMODB_ENTITY_TABLE', 'DYNAMODB_BLUEPRINT_TABLE', 
        'DYNAMODB_RINGDATA_TABLE', 'DYNAMODB_REL_TABLE', 'DYNAMODB_CHAT_TABLE',
        'DYNAMODB_SESSION_TABLE', 'DYNAMODB_SEARCH_TABLE', 'DYNAMODB_GRAPH_TABLE',
        'GRAPH_DB_ENABLED',
        'COGNITO_REGION', 'COGNITO_USERPOOL_ID', 'COGNITO_APP_CLIENT_ID',
        'OPENAI_API_KEY', 'WEBSOCKET_CONNECTIONS', 'BASE_URL',
        'AGENT_API_OUTPUT', 'AGENT_API_HANDLER', 'S3_BUCKET_NAME'
    ]
    
    for key in env_var_keys:
        if key in os.environ:
            config[key] = os.environ[key]
    
    return config

