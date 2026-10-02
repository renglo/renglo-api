# session_routes.py

from flask import Blueprint,request,redirect,url_for, jsonify, current_app, session, render_template, make_response
from renglo.auth.login_required import login_required
from flask_cognito import cognito_auth_required, current_user, current_cognito_jwt
from renglo.session.session_controller import SessionController
from renglo.agent.agent_controller import AgentController
from renglo.auth.auth_controller import AuthController
from renglo.data.data_controller import DataController
from renglo.schd.schd_controller import SchdController
from renglo.session.handler_error import surface_handler_failure
from functools import wraps
import time
import json
import boto3
from decimal import Decimal
from datetime import datetime

class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return int(obj) if obj % 1 == 0 else float(obj)
        return super(DecimalEncoder, self).default(obj)

app_session = Blueprint('app_session', __name__, url_prefix='/_session')

# Controllers - will be initialized when blueprint is registered
SSC = None
AGC = None
AUC = None
DAC = None
SHC = None

def _surface_call_failure(payload, response, status):
    """Save and push a handler failure the handler did not already report."""
    config = getattr(SHC, "config", None) or {}
    try:
        return surface_handler_failure(config, payload or {}, response, status)
    except Exception as exc:
        current_app.logger.error("surface_handler_failure failed: %s", exc)
        return None

@app_session.record_once
def on_load(state):
    """Initialize controllers with config when blueprint is registered."""
    global SSC, AGC, AUC, DAC, SHC
    config = state.app.renglo_config
    SSC = SessionController(config=config)
    AGC = AgentController(config=config)
    AUC = AuthController(config=config)
    DAC = DataController(config=config)
    SHC = SchdController(config=config)



def socket_auth_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        try:
            current_app.logger.info("Starting socket authentication process...")
            payload = request.get_json()
            
            if not payload or 'auth' not in payload:
                error_msg= "Missing payload or auth token in request"
                current_app.logger.error(error_msg)
                SSC.error_session(error_msg,payload['connection_id'])
                return jsonify({'error': error_msg}), 401
            
            auth_token = payload['auth']
            if not isinstance(auth_token, str):
                error_msg= "Invalid auth token format"
                current_app.logger.error(error_msg)
                SSC.error_session(error_msg,payload['connection_id'])
                return jsonify({'error': error_msg}), 401

            # Set the token in the request headers for cognito authentication
            with current_app.test_request_context(headers={'Authorization': f'Bearer {auth_token}'}):
                try:
                    cognito_auth_required(lambda: None)()
                except Exception as cognito_error:
                    current_app.logger.error(f"Cognito authentication failed: {str(cognito_error)}")
                    SSC.error_session(str(cognito_error),payload['connection_id'])
                    return jsonify({'error': 'Invalid or expired authentication token'}), 401

            current_app.logger.info("Socket authentication successful")
            return f(*args, **kwargs)
            
        except ValueError as ve:
            current_app.logger.error(f"Invalid request format: {str(ve)}")
            return jsonify({'error': 'Invalid request format'}), 400
        except Exception as e:
            current_app.logger.error(f"Unexpected error during socket authentication: {str(e)}")
            return jsonify({'error': 'Internal authentication error'}), 500
    return wrapped

   
    
 # Web Socket endpoints
 
@app_session.route('/message',methods=['POST'])
@socket_auth_required
def real_time_message():
    payload = {}
    try:
        current_app.logger.info("WEBSOCKET MESSAGE IN THE CHAT APP")
        payload = request.get_json() or {}
        if not payload:
            current_app.logger.error("No payload received")
            return jsonify({'error': 'No payload received'}), 400
            
        current_app.logger.info(payload)
        
        # Validate required fields
        required_fields = ['action', 'auth', 'data']
        missing_fields = [field for field in required_fields if field not in payload]
        if missing_fields:
            current_app.logger.error(f"Missing required fields: {missing_fields}")
            return jsonify({'error': f'Missing required fields: {missing_fields}'}), 400
        
        
        if 'core' in payload:
            if payload['core'] == 'default' or payload['core'] == '':
                response = AGC.triage(payload)
                status = 200
            else:    
                response, status = SHC.direct_run(payload['core'],payload)
        else:
            response = AGC.triage(payload)
            status = 200
        
        
        if isinstance(response, tuple):
            response, status = response
            
        current_app.logger.debug('TRACE >>')
        current_app.logger.debug(response)
        _surface_call_failure(payload, response, status)

        return jsonify({"statusCode": 200}), 200
            
    except Exception as e:
        current_app.logger.error(f"Error processing message: {str(e)}")
        _surface_call_failure(payload, str(e), 500)
        return jsonify({"statusCode": 200}), 200
    


#RESTful endpoints

# Finds conversation threads based on provided entity and entity_id
# The controller will verify if the requester has access to those entities.
# INPUT: Entity, Entity ID
# OUTPUT: List of Conversation Threads (most recent on top) 

@app_session.route('/')
@cognito_auth_required
def index():
    
    response = True
    return response


# Get a list of threads
# Shows the list of all threads related to an entity.
# SAMPLE URL https://<some_domain/_session/<entity_type>/<entity_id>
# INPUT: entity_type, entity_id
# OUTPUT: A list of threads that belong to the entity
@app_session.route('<string:portfolio>/<string:org>/<string:entity_type>/<string:entity_id>', methods=['GET','POST'])
@cognito_auth_required
def session_threads(portfolio,org,entity_type,entity_id): 
    # Authorization validation should be implemented here. Check if token is authorized to access portfolio/org
    # Even though the call is authorized, you still need to send portfolio and org to the controller and models as
    # data is segmented by portfolio and org
    
    if request.method == 'GET':
        response = SSC.list_threads(portfolio,org,entity_type,entity_id)   
    elif request.method == 'POST':
        response = SSC.create_thread(portfolio,org,entity_type,entity_id)
        
    return response


# Query for threads
# Shows the list of all threads related to an entity.
# SAMPLE URL https://<some_domain/_session/<entity_type>/<entity_id>
# INPUT: entity_type, query
# OUTPUT: A list of threads result of the query
@app_session.route('<string:portfolio>/<string:org>/<string:entity_type>/<string:query>/query', methods=['GET'])
@cognito_auth_required
def session_query(portfolio,org,entity_type,query):
    # Authorization validation should be implemented here. Check if token is authorized to access portfolio/org
    
    #Replace placeholder for empty query requests
    if query == '*':
        query = ''
             
    response = SSC.query_threads(portfolio,org,entity_type,query)   

    return response



# Get/post messages from a thread
# A conversation thread is a short lived and focused exchange of messages between an agent and a team, user or group of users.
# SAMPLE URL https://<some_domain/_session/<entity_type>/<entity_id>/<thread_id>/<messages>
# INPUT: entity_type, entity_id, thread_id
# OUTPUT: A list of messages that belong to the conversation thread
@app_session.route('<string:portfolio>/<string:org>/<string:entity_type>/<string:entity_id>/<string:thread_id>/messages', methods=['GET'])
@cognito_auth_required
def session_messages(portfolio,org,entity_type,entity_id,thread_id):
    # Authorization validation should be implemented here. Check if token is authorized to access portfolio/org
    
    if request.method == 'GET':
        # resolve=True: inline tmp artifacts for UI; agent/triage code must use SSC.list_turns(..., False)
        response = SSC.list_turns(portfolio,org,entity_type,entity_id,thread_id,True) 
        
     

        
    return response


# Get/post workspaces from a thread
# A conversation thread is a short lived and focused exchange of messages around workspaces between an agent and a team, user or group of users.
# SAMPLE URL https://<some_domain/_session/<entity_type>/<entity_id>/<thread_id>
# INPUT: entity_type, entity_id, thread_id
# OUTPUT: A list of messages that belong to the conversation thread
@app_session.route('<string:portfolio>/<string:org>/<string:entity_type>/<string:entity_id>/<string:thread_id>/workspaces', methods=['GET'])
@cognito_auth_required
def session_workspaces(portfolio,org,entity_type,entity_id,thread_id):
    # Authorization validation should be implemented here. Check if token is authorized to access portfolio/org
      
    if request.method == 'GET':
        response = SSC.list_workspaces(portfolio,org,entity_type,entity_id,thread_id)  
      
    return response



# Mutate the Workspace
@app_session.route('<string:portfolio>/<string:org>/<string:entity_type>/<string:entity_id>/<string:thread_id>/workspaces/<string:workspace_id>', methods=['GET','PUT'])
@cognito_auth_required
def session_one_workspace(portfolio,org,entity_type,entity_id,thread_id,workspace_id):
    # Authorization validation should be implemented here. Check if token is authorized to access portfolio/org
    
    if request.method == 'GET':
        response = SSC.get_workspace(portfolio,org,entity_type,entity_id,thread_id,workspace_id)  
    elif request.method == 'PUT':
        payload = request.get_json()
        response = SSC.update_workspace(portfolio,org,entity_type,entity_id,thread_id,workspace_id,payload) 
        
    return response


@app_session.route('<string:x>/<string:y>', methods=['GET'])
def dead_end(): 
    print('Dead End')
    return '',200



# TROUBLESHOOT (Please comment out)
@app_session.route('/tb', methods=['POST'])
@cognito_auth_required
def session_tb():
    
    '''
    Payload format
    {
      'action':'chat_message',
      'portfolio':<portfolio_id>,
      'org':<org_id>,
      'entity_type':<entity_type>,
      'entity_id':<entity_id>,
      'thread':<thread_id>,
      'core':<custom agent>,
      'data': <raw_message>
    }
    '''
    payload = request.get_json() or {}
    
    try:
        if 'core' in payload and payload['core'] != 'default':
            response, status = SHC.direct_run(payload['core'],payload)
        else:
            response = AGC.triage(payload)
            status = 200
    except Exception as exc:
        current_app.logger.error("Error processing /tb: %s", exc)
        message = _surface_call_failure(payload, str(exc), 500)
        return {'success': False, 'error': message}, 500

    current_app.logger.debug('TRACE >>')
    current_app.logger.debug(response)
    message = _surface_call_failure(payload, response, status)
    if message:
        return {'success': False, 'error': message, 'output': response}, status

    return response, status



# DEPRECATED. Use a handler instead
@app_session.route('/process-gupshup/', methods=['POST'])
def process_gupshup_event_with_slash():
    # Call the same function to avoid code duplication
    return process_gupshup_event()


# DEPRECATED. Use a handler instead
@app_session.route('/process-gupshup', methods=['POST'])
def process_gupshup_event():
    """
    Process Gupshup messages sent via EventBridge.
    This endpoint is called by EventBridge when a webhook event is received.
    """
    
    from .integrations.gupshup_integration import GupshupIntegration
    GSI = GupshupIntegration(SSC,AGC,current_app)
    
    current_app.logger.info("Processing EventBridge Gupshup event")
    
    try:
        # Extract and validate event data
        event_data = request.get_json()
        current_app.logger.info(f"Received EventBridge event: {event_data}")
        
        
        detail = event_data.get('detail', {})
        if not isinstance(detail, dict):
            current_app.logger.error(f"Invalid detail format: {type(detail)}")
            return "", 400
        portfolio = detail.get('portfolio')
        tool_id = detail.get('tool_id')
        gupshup_payload = detail.get('gupshup_payload')
        
        if not all([portfolio, tool_id, gupshup_payload]):
            current_app.logger.error("Missing required fields in EventBridge event")
            return "", 400
        
        # Process the message
        response = GSI.process_gupshup_message(portfolio, tool_id, gupshup_payload)
        
        current_app.logger.info(f"Gupshup Trace >> {response}")
        
        return response, 200
            
    except Exception as e:
        current_app.logger.error(f"Error processing Gupshup message: {e}")
        return "", 500




