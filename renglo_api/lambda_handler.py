"""
AWS Lambda entrypoint for Renglo API.
"""

from apig_wsgi import make_lambda_handler

from renglo_api.application import app

lambda_handler = make_lambda_handler(app)
