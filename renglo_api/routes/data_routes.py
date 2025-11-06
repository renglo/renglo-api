#app_data.py
from flask import Blueprint,request,redirect,url_for, jsonify, current_app, session, render_template, make_response
from renglo.auth.login_required import login_required
from renglo.auth.auth_controller import AuthController
from renglo.data.data_controller import DataController
from flask_cognito import cognito_auth_required, current_user, current_cognito_jwt

import time,json,csv
import io
import urllib.parse
import boto3
from decimal import Decimal


app_data = Blueprint('app_data', __name__, template_folder='templates',url_prefix='/_data')

# Controllers - will be initialized when blueprint is registered
AUC = None
DAC = None

@app_data.record_once
def on_load(state):
    """Initialize controllers with config when blueprint is registered."""
    global AUC, DAC
    config = state.app.renglo_config
    AUC = AuthController(config=config)
    DAC = DataController(config=config)

# Set the route and accepted methods



@app_data.route('/')
@cognito_auth_required
def index():
   #Nothing to show here
    return jsonify(message='')


#TEST (DELETE)
@app_data.route('/t1')
def t1():

    current_app.logger.info('t1')
    return jsonify(message="t1")
    

@app_data.route('/<string:portfolio>/<string:org>/<string:ring>', methods=['GET'])
@cognito_auth_required
def route_a_b_get(portfolio, org, ring):

    limit = request.args.get('limit', default=987, type=int)  # Retrieve limit, default to 1000
    lastkey = request.args.get('lastkey')  # Retrieve lastkey, default to None
    sort = request.args.get('sort')  # Retrieve sort, default to None
    all = request.args.get('all')
    refresh = request.args.get('refresh')  # Check for refresh parameter

    response = []
    
    if all or refresh:  # Check if 'all' or 'refresh' is present
        s3_client = boto3.client('s3')
        bucket_name = current_app.config['S3_BUCKET_NAME']  
        file_path = f'data/{portfolio}/{org}/{ring}'
        
        try:
            # Check if this document already exists in S3
            s3_client.head_object(Bucket=bucket_name, Key=file_path)
            # If it exists and refresh is set, raise an exception to trigger regeneration
            if refresh:
                current_app.logger.debug('Document exists, but refresh is set. Raising exception to regenerate document.')
                raise Exception("Force regeneration due to refresh flag.")
            else:
                response = s3_client.get_object(Bucket=bucket_name, Key=file_path)
                document = json.loads(response['Body'].read())
                current_app.logger.debug('Document already exists, retrieving from S3')
                return jsonify(document), 200
        except (s3_client.exceptions.ClientError, Exception) as e:
            # If it does not exist or if we raised an exception, call DAC.get_a_b()
            DAC.refresh_s3_cache(portfolio, org, ring, sort)
        
    else:
        response = DAC.get_a_b(portfolio, org, ring, limit, lastkey, sort)
        return jsonify(response), 200  # Ensure a consistent JSON response
    

@app_data.route('/<string:portfolio>/_all/<string:ring>', methods=['POST'])
@cognito_auth_required
def route_a_all_post(portfolio,ring):
    
    payload = request.get_json()
    response, status = DAC.post_a_b(portfolio,'_all',ring,payload)
    DAC.refresh_s3_cache(portfolio, '_all', ring, None)
    return response, status
    

@app_data.route('/<string:portfolio>/<string:org>/<string:ring>', methods=['POST'])
@cognito_auth_required
def route_a_b_post(portfolio,org,ring):
    
    payload = request.get_json()
    response, status = DAC.post_a_b(portfolio,org,ring,payload)
    DAC.refresh_s3_cache(portfolio, org, ring, None)
    return response, status



@app_data.route('/<string:portfolio>/<string:org>/<string:ring>/_query', methods=['POST'])
@cognito_auth_required
def route_a_b_query(portfolio, org, ring):
    
    limit = request.args.get('limit', default=999, type=int)  # Retrieve limit, default to 1000
    lastkey = request.args.get('lastkey')  # Retrieve lastkey, default to None
    sort = request.args.get('sort')  # Retrieve sort, default to None
    payload = request.get_json()
    
    '''
    Payload sample 1
    The value is any string at the end of the index string portfolio:org:ring:<any_string>
    {
        'operator':'begins_with',
        'value':'123453:active',
        'filter':{
            'operator':'greater_than',
            'field':'launch_time'
            'value':'17234432453'
        },
        'sort':'desc'
    }
    
    Payload sample 2
    This is a special case where the index is a timestamp  portfolio:org:ring:<timestamp> 
    In the background it is a 'begins_with' with an empty sufix
    Value is always empty. 
    Returns a list of items ordered chronologically. 
    The filter is optional but recommended to shorten the response size
    {
        'operator':'chrono',
        'filter':{
            'operator':'greater_than',
            'value':'17234432453'
        },
        'sort':'desc'
    }
    '''
       
    query = {
        'portfolio':portfolio,
        'org':org,
        'ring':ring,
        'operator':payload.get('operator', None),
        'value':payload.get('value', None),
        'filter':payload.get('filter',{}),
        'limit':limit,
        'lastkey':lastkey,
        'sort': payload.get('sort', sort)
    }
       
    response = DAC.get_a_b_query(query)
    return response, 200



@app_data.route('/<string:portfolio>/<string:org>/<string:ring>/<string:idx>', methods=['GET'])
@cognito_auth_required
def route_a_b_c_get(portfolio,org,ring,idx):

    return DAC.get_a_b_c(portfolio,org,ring,idx)

    
@app_data.route('/<string:portfolio>/<string:org>/<string:ring>/<string:idx>', methods=['PUT'])
@cognito_auth_required
def route_a_b_c_put(portfolio,org,ring,idx):
    
    payload = request.get_json()
    response, status = DAC.put_a_b_c(portfolio,org,ring,idx,payload)
    DAC.refresh_s3_cache(portfolio, org, ring, None)
    return response, status


@app_data.route('/<string:portfolio>/<string:org>/<string:ring>/<string:idx>', methods=['DELETE'])
@cognito_auth_required
def route_a_b_c_delete(portfolio,org,ring,idx):

    response, status = DAC.delete_a_b_c(portfolio,org,ring,idx)
    DAC.refresh_s3_cache(portfolio, org, ring, None)
    return response, status




    
