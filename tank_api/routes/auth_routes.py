#app_auth.py
from flask import Flask, redirect, request, session, url_for,Blueprint, jsonify, current_app
from tank.common import *
import re
import json
import boto3



from tank.app_auth.auth_controller import AuthController
from flask_cognito import cognito_auth_required, current_user, current_cognito_jwt

app_auth = Blueprint('app_auth', __name__, template_folder='templates',url_prefix='/_auth')

# Controllers - will be initialized when blueprint is registered
AUC = None
JWKS_URL = None

@app_auth.record_once
def on_load(state):
    """Initialize controllers with config when blueprint is registered."""
    global AUC, JWKS_URL
    config = state.app.tank_config
    AUC = AuthController(config=config)
    cognito_region = config.get('COGNITO_REGION', 'us-east-1')
    cognito_pool_id = config.get('COGNITO_USERPOOL_ID', '')
    JWKS_URL = f'https://cognito-idp.{cognito_region}.amazonaws.com/{cognito_pool_id}/.well-known/jwks.json'


# WILL DEPRECATE : Use the get_current_user() in auth_controller instead
def get_current_user():

    if "cognito:username" in current_cognito_jwt:
        # IdToken was used
        user_id = create_md5_hash(current_cognito_jwt["cognito:username"],9)
    else:
        # AccessToken was used
        user_id = create_md5_hash(current_cognito_jwt["username"],9)

    return user_id


#TANK-FE
def authorization_check(app_id,action,entity_id=''):

    user_id = get_current_user()
    current_app.logger.debug('Checking whether '+ str(user_id) +' is authorized to run '+ str(action) +' in app '+ str(app_id) + ' on entity '+ str(entity_id))
    return {
            "success":True, 
            "message": "Authorized", 
            "status" :200
            }



#TANK-FE
@app_auth.route('/', methods=['GET'])
@cognito_auth_required
def index():
    #Nothing to show here yet
    return jsonify(message='')


#TANK-FE
def detect_injection_characters(input_string):
    # Pattern excludes periods (.), @ symbol, dashes (-), and underscores (_) commonly used in emails
    pattern = r'[{};:\/\'\"\\\(\)\[\]\$\|&<>]'
    
    # Find all matches of potentially harmful characters
    injection_chars = re.findall(pattern, input_string)
    
    if injection_chars:
        return True 
    else:
        return False 
    

def remove_non_alphanum(input_string):
    # Keep alphanumeric characters and spaces
    return re.sub(r'[^a-zA-Z0-9\s]', '', input_string)
    

def validate_payload(payload,allowed_keys):


    if any(key not in allowed_keys for key in payload):
        return {
            "success": False,
            "message": "Payload contains invalid attributes",
            "status": 400
        }
     

    clean_payload = {}
    for key in allowed_keys: 
        if key in payload:
            if detect_injection_characters(payload[key]):
                current_app.logger.debug('Injection detected:'+str(payload[key]))
                continue
            else:
            #    clean_payload[key] = remove_non_alphanum(payload[key])
                clean_payload[key] = payload[key]

    return {
            "success":True, 
            "message": "Payload sanitized", 
            "document": clean_payload,
            "status" :400
            }


#-------------------------------------------------ROUTES/USERS


#TANK-FE
@app_auth.route('/user/invite', methods=['POST'])
@cognito_auth_required
def invite_user_post():
    '''
    Invites user to a team
    '''

    raw_payload = request.get_json()
    required_keys = ['email','team_id','portfolio_id'] 
    if not all(key in raw_payload for key in required_keys):
        return{
            "success":False, 
            "message": "Missing attributes", 
            "status" :400
            }

    response_1 = validate_payload(raw_payload,['email','team_id','portfolio_id'])
    if not response_1['success']:
        return jsonify(response_1), response_1['status']
    
    payload = response_1['document']
    #current_app.logger.debug('Payload:'+str(payload))

    response_2 = authorization_check('_auth','inviteUser',entity_id = payload['team_id'])
    if not response_2['success']:
        return response_2
    
    sender_id = get_current_user()
    response = AUC.invite_user(payload['email'],payload['team_id'],payload['portfolio_id'],sender_id)

    return jsonify(response), response['status']



#TANK-FE
@app_auth.route('/user/invite', methods=['PUT'])
#@cognito_auth_required > NO AUTH REQUIRED BECAUSE ANONYMOUS UNAUTHENTICATED USER IS SOLVING THE CHALLENGE
def invite_user_put():
    '''
    Verifies that hash and email make a valid invitation 
    '''
    payload = request.get_json()
    # Check for minimum requirements
    required_keys = ['code','email','first','last','pass'] 
    if not all(key in payload for key in required_keys):
        return{
            "success":False, 
            "message": "Missing attributes", 
            "status" :400
            }

    response = AUC.invite_create_user_funnel(**payload)

    return jsonify(response), response['status']



#TANK-FE
@app_auth.route('/user/token', methods=['GET'])
@cognito_auth_required
def get_user_token():
    '''
    Returns JWT token from the Authorization header
    '''
    
    if not authorization_check('_auth','getJWT'):
        return False

    # Get the raw JWT token from the Authorization header
    auth_header = request.headers.get('Authorization')
    if auth_header and auth_header.startswith('Bearer '):
        token = auth_header.split(' ')[1]  # Get the token part after 'Bearer '
        return {'success': True, 'output': token}, 200
    else:      
        return {'success': False, 'message': 'No valid token found'}, 400

    


#TANK-FE
@app_auth.route('/user', methods=['GET'])
@cognito_auth_required
def get_user():
    '''
    Returns User document
    '''

    if not authorization_check('_auth','getOwnUser'):
        return False

    if "cognito:username" in current_cognito_jwt:
        # IdToken was used
        #current_app.logger.debug(current_cognito_jwt["cognito:username"])
        user_id = create_md5_hash(current_cognito_jwt["cognito:username"],9)
    else:
        # AccessToken was used
        #current_app.logger.debug(current_cognito_jwt["username"])
        user_id = create_md5_hash(current_cognito_jwt["username"],9)

    #current_app.logger.debug(current_cognito_jwt)
    data = {}
    data['user_id'] = user_id
    
    type = 'user'
    response = AUC.get_entity(type,**data)
    if response['success']:
        return jsonify(response['document']), response['status']
    else:
        return jsonify(response), response['status']


#TANK-FE
@app_auth.route('/user', methods=['PUT'])
@cognito_auth_required
def update_user():
    '''
    Updates an attribute of an existing user 
    or creates a new user document if it doesn't exist

    - We are using /user[PUT] to create the new user 
    document as /user[POST] won't exist to avoid creating an explicit
    endpoint to create users. We are only creating a new user document indirectly
    if it is discovered that it doesn't exist. 
    - We are only allowing partial PUTs in the user document to avoid attempts
    to override certain parts of the documents that shouldn't be requested directly. 
    '''

    #AUTH-CHECK
    if not authorization_check('_auth','modifyOwnUser'):
        return False
    
    if "cognito:username" in current_cognito_jwt:
        # IdToken was used
        #current_app.logger.debug(current_cognito_jwt["cognito:username"])
        user_id = create_md5_hash(current_cognito_jwt["cognito:username"],9)
        name = current_cognito_jwt["given_name"]
        last = current_cognito_jwt["family_name"]
    else:
        # AccessToken was used
        #current_app.logger.debug(current_cognito_jwt["username"])
        user_id = create_md5_hash(current_cognito_jwt["username"],9)
        name = ''
        last = ''
    
    data = {}
    #We don't acquire the user_id from the request or the url. Instead we will get it from the AccessToken
    data['ip'] = request.headers.get('X-Forwarded-For', request.remote_addr)
    data['lan'] = request.headers.get('Accept-Language')
    data['user_id'] = user_id
    data['name'] = name
    data['slot_a'] = last
    data['payload'] = request.get_json()
    
    type = 'user'
    response = AUC.update_entity(type,**data)
    return jsonify(response), response['status']



#-------------------------------------------------ROUTES/PORTFOLIOS

#TANK-FE
@app_auth.route('/tree/refresh', methods=['GET'])
@cognito_auth_required
def refresh_tree():
    
    # Generate tree
    current_app.logger.error(f"Refreshing tree")
    data = {}
    data['user_id'] = get_current_user()
    response = AUC.get_tree_full(**data)

    # Initialize S3 client and define bucket name and file path
    s3_client = boto3.client('s3')  # Ensure boto3 is imported
    bucket_name = current_app.config['S3_BUCKET_NAME']  
    file_path = f'auth/tree/{data["user_id"]}'

    # Store the new version in S3
    try:
        s3_client.put_object(Bucket=bucket_name, Key=file_path, Body=json.dumps(response['document']))
    except Exception as e:
        current_app.logger.error(f"Failed to upload to S3: {str(e)}")
        return jsonify({"success": False, "message": "Failed to upload to S3", "status": 500}), 500
    
    if response['success']:
        return jsonify(response['document']), response['status']
    else:
        return jsonify(response), response['status']
    
    
    
    
    
    
    


#TANK-FE
@app_auth.route('/tree', methods=['GET'])
@cognito_auth_required
def get_tree():

    #AUTH-CHECK
    if not authorization_check('_auth','ListOwnTree'):
        return False
    
    data = {}
    data['user_id'] = get_current_user()
    
    # Check if the document already exists in the S3 bucket
    s3_client = boto3.client('s3')
    bucket_name = current_app.config['S3_BUCKET_NAME']  
    file_path = f'auth/tree/{data["user_id"]}'
    
    try:
        s3_client.head_object(Bucket=bucket_name, Key=file_path)
        # If it exists, return the document from the S3 bucket
        response = s3_client.get_object(Bucket=bucket_name, Key=file_path)
        document = json.loads(response['Body'].read())
        current_app.logger.debug('Tree already exists, retrieving from S3:'+str(document))
        return jsonify(document), 200
    except s3_client.exceptions.ClientError:
        # If it does not exist, call AUC.get_tree_full()
        current_app.logger.debug('Tree not found in s3, creating new one')
        response = AUC.get_tree_full(**data)
        s3_client.put_object(Bucket=bucket_name, Key=file_path, Body=json.dumps(response['document']))
    
    if response['success']:
        return jsonify(response['document']), response['status']
    else:
        return jsonify(response), response['status']
    




#TANK-FE
@app_auth.route('/portfolios', methods=['GET'])
@cognito_auth_required
def list_portfolio():

    #AUTH-CHECK
    if not authorization_check('_auth','ListOwnPortfolio'):
        return False
    
    data = {}
    data['user_id'] = get_current_user()

    type = 'portfolio'
    response = AUC.list_entity(type,**data)
    if response['success']:
        return jsonify(response['document']), response['status']
    else:
        return jsonify(response), response['status']
    

#TANK-FE
#UPDATES TREE
@app_auth.route('/portfolios', methods=['POST'])
@cognito_auth_required
def create_portfolio():

    # AUTH-CHECK
    if not authorization_check('_auth', 'createOwnPortfolio'):
        return jsonify({"success": False, "message": "Unauthorized", "status": 403}), 403

    data = request.get_json()
    if data is None:
        return jsonify({"success": False, "message": "Invalid JSON", "status": 400}), 400

    data['ip'] = request.headers.get('X-Forwarded-For', request.remote_addr)
    data['lan'] = request.headers.get('Accept-Language')
    data['user_id'] = get_current_user()
    
    response = AUC.create_portfolio_funnel(**data)
    
    if not response['success']:
        return jsonify(response), response['status']
    
    refresh_tree()
    return jsonify(response), response['status']
    


#TANK-FE
@app_auth.route('/portfolios/<string:portfolio_id>', methods=['GET'])
@cognito_auth_required
def get_portfolio(portfolio_id):

    #AUTH-CHECK
    if not authorization_check('_auth','getPortfolio',entity_id=portfolio_id):
        return False
    
    data = {}
    data['portfolio_id'] = portfolio_id
    
    type = 'portfolio'
    response = AUC.get_entity(type,**data)
    if response['success']:
        return jsonify(response['document']), response['status']
    else:
        return jsonify(response), response['status']


#TANK-FE
#UPDATES TREE
@app_auth.route('/portfolios/<string:portfolio_id>', methods=['PUT'])
@cognito_auth_required
def update_portfolio(portfolio_id):

    # AUTH-CHECK
    if not authorization_check('_auth', 'updatePortfolio', entity_id=portfolio_id):
        return jsonify({"success": False, "message": "Unauthorized", "status": 403}), 403

    data = {}
    data['ip'] = request.headers.get('X-Forwarded-For', request.remote_addr)
    data['lan'] = request.headers.get('Accept-Language')
    data['user_id'] = get_current_user()
    data['portfolio_id'] = portfolio_id
    
    payload = request.get_json()
    if payload is None:
        return jsonify({"success": False, "message": "Invalid JSON", "status": 400}), 400
    data['payload'] = payload
    
    type = 'portfolio'
    response = AUC.update_entity(type, **data)
    
    if not response['success']:
        return jsonify(response), response['status']
    
    refresh_tree()
    return jsonify(response), response['status']









#-------------------------------------------------ROUTES/ORGS
# _auth/orgs/* use a composed id : <PORTFOLIO_ID>-<ORG_ID>

#TANK-FE
@app_auth.route('/orgs/<string:portfolio_org_id>', methods=['GET'])
@cognito_auth_required
def get_org(portfolio_org_id):

    portfolio_id, org_id = portfolio_org_id.split('-', 1)

    #AUTH-CHECK
    if not authorization_check('_auth','getOrg',entity_id=portfolio_org_id):
        return False
    

    data = {}
    data['portfolio_id'] = portfolio_id
    data['org_id'] = org_id
    

    type = 'org'
    response = AUC.get_entity(type,**data)
    if response['success']:
        return jsonify(response['document']), response['status']
    else:
        return jsonify(response), response['status']


#TANK-FE
#UPDATES TREE
@app_auth.route('/orgs/<string:portfolio_org_id>', methods=['PUT'])
@cognito_auth_required
def update_org(portfolio_org_id):

    portfolio_id, org_id = portfolio_org_id.split('-', 1)

    # AUTH-CHECK
    if not authorization_check('_auth', 'updateOrg', entity_id=portfolio_org_id):
        return jsonify({"success": False, "message": "Unauthorized", "status": 403}), 403

    data = request.get_json()
    if data is None:
        return jsonify({"success": False, "message": "Invalid JSON", "status": 400}), 400

    data['ip'] = request.headers.get('X-Forwarded-For', request.remote_addr)
    data['lan'] = request.headers.get('Accept-Language')
    data['user_id'] = get_current_user()
    data['portfolio_id'] = portfolio_id
    data['org_id'] = org_id

    type = 'org'
    response = AUC.update_entity(type, **data)
    
    if not response['success']:
        return jsonify(response), response['status']
    
    refresh_tree()
    return jsonify(response), response['status']



#TANK-FE
#UPDATES TREE
@app_auth.route('/orgs/<string:portfolio_id>', methods=['POST'])
@cognito_auth_required
def create_org(portfolio_id):

    # AUTH-CHECK
    if not authorization_check('_auth', 'createOrg', entity_id=portfolio_id):
        return jsonify({"success": False, "message": "Unauthorized", "status": 403}), 403

    data = request.get_json()
    if data is None:
        return jsonify({"success": False, "message": "Invalid JSON", "status": 400}), 400

    # Validate required keys in the payload
    required_keys = ['name']
    if not all(key in data for key in required_keys):
        return jsonify({"success": False, "message": "Missing required attributes", "status": 400}), 400

    data['ip'] = request.headers.get('X-Forwarded-For', request.remote_addr)
    data['lan'] = request.headers.get('Accept-Language')
    data['user_id'] = get_current_user()
    data['portfolio_id'] = portfolio_id

    response = AUC.create_org_funnel(**data)
    
    if not response['success']:
        return jsonify(response), response['status']
    
    refresh_tree()
    return jsonify(response), response['status']


#UPDATES TREE
@app_auth.route('/portfolios/<string:portfolio_id>/orgs/<string:org_id>', methods=['PUT'])
@cognito_auth_required
def put_org(portfolio_id, org_id):

    # AUTH-CHECK
    if not authorization_check('_auth', 'editOrgs', entity_id=org_id):
        return jsonify({"success": False, "message": "Unauthorized", "status": 403}), 403

    payload = request.get_json()
    if payload is None:
        return jsonify({"success": False, "message": "Invalid JSON", "status": 400}), 400

    response_1 = validate_payload(payload, ['name'])
    if not response_1['success']:
        return jsonify(response_1), response_1['status']
    
    data = {}
    data['payload'] = response_1['document']
    data['ip'] = request.headers.get('X-Forwarded-For', request.remote_addr)
    data['user_id'] = get_current_user()
    data['portfolio_id'] = portfolio_id
    data['org_id'] = org_id

    response = AUC.update_entity('org', **data)
    
    if not response['success']:
        return jsonify(response), response['status']
    
    refresh_tree()
    return jsonify(response['document']), response['status']
    

#TANK-FE
# UPDATES TREE
@app_auth.route('/portfolios/<string:portfolio_id>/orgs/<string:org_id>', methods=['DELETE'])
@cognito_auth_required
def delete_org(portfolio_id, org_id):

    # AUTH-CHECK
    if not authorization_check('_auth', 'deleteOrgs', entity_id=org_id):
        return jsonify({"success": False, "message": "Unauthorized", "status": 403}), 403

    # Get the request data
    data = request.get_json()
    if data is None:
        return jsonify({"success": False, "message": "Invalid JSON", "status": 400}), 400

    data['ip'] = request.headers.get('X-Forwarded-For', request.remote_addr)
    data['user_id'] = get_current_user()
    data['portfolio_id'] = portfolio_id
    data['org_id'] = org_id

    response = AUC.remove_org_funnel(**data)
    
    if not response['success']:
        return jsonify(response), response['status']
    
    refresh_tree()
    return jsonify(response['document']), response['status']





#-------------------------------------------------ROUTES/TEAMS
# _auth/teams/* use a composed id : <PORTFOLIO_ID>-<TEAM_ID>


#TANK-FE NOT USED
@app_auth.route('/teams/<string:portfolio_team_id>', methods=['GET'])
@cognito_auth_required
def get_team(portfolio_team_id):

    portfolio_id, team_id = portfolio_team_id.split('-', 1)

    #AUTH-CHECK
    if not authorization_check('_auth','getTeam',entity_id=portfolio_team_id):
        return False
    

    data = {}
    data['portfolio_id'] = portfolio_id
    data['team_id'] = team_id
    

    type = 'team'
    response = AUC.get_entity(type,**data)
    if response['success']:
        return jsonify(response['document']), response['status']
    else:
        return jsonify(response), response['status']
    


#TANK-FE
#UPDATES TREE
@app_auth.route('/portfolios/<string:portfolio_id>/teams/<string:team_id>', methods=['PUT'])
@cognito_auth_required
def put_team(portfolio_id, team_id):

    # AUTH-CHECK
    if not authorization_check('_auth', 'editTeams', entity_id=team_id):
        return jsonify({"success": False, "message": "Unauthorized", "status": 403}), 403

    payload = request.get_json()
    if payload is None:
        return jsonify({"success": False, "message": "Invalid JSON", "status": 400}), 400

    response_1 = validate_payload(payload, ['name'])
    if not response_1['success']:
        return jsonify(response_1), response_1['status']
    
    data = {}
    data['payload'] = response_1['document']
    data['ip'] = request.headers.get('X-Forwarded-For', request.remote_addr)
    data['user_id'] = get_current_user()
    data['portfolio_id'] = portfolio_id
    data['team_id'] = team_id

    response = AUC.update_entity('team', **data)
    
    if not response['success']:
        return jsonify(response), response['status']
    
    refresh_tree()
    return jsonify(response['document']), response['status']
    

#TANK-FE
#UPDATE TREE
@app_auth.route('/portfolios/<string:portfolio_id>/teams/<string:team_id>', methods=['DELETE'])
@cognito_auth_required
def delete_team(portfolio_id, team_id):

    # AUTH-CHECK
    if not authorization_check('_auth', 'deleteTeams', entity_id=team_id):
        return jsonify({"success": False, "message": "Unauthorized", "status": 403}), 403

    # Get the request data
    data = request.get_json()
    if data is None:
        return jsonify({"success": False, "message": "Invalid JSON", "status": 400}), 400

    data['ip'] = request.headers.get('X-Forwarded-For', request.remote_addr)
    data['user_id'] = get_current_user()
    data['portfolio_id'] = portfolio_id
    data['team_id'] = team_id

    response = AUC.remove_team_funnel(**data)
    
    if not response['success']:
        return jsonify(response), response['status']
    
    refresh_tree()
    return jsonify(response['document']), response['status']




#TANK-FE
@app_auth.route('/teams/<string:team_id>/users', methods=['GET'])
@cognito_auth_required
def get_team_users(team_id):

    #AUTH-CHECK
    if not authorization_check('_auth','getTeamUsers',entity_id=team_id):
        return False
    

    data = {}
    data['user_id'] = get_current_user()
    data['team_id'] = team_id
    
    response = AUC.get_team_users(**data) 
    if response['success']:
        return jsonify(response['document']), response['status']
    else:
        return jsonify(response), response['status']
    

#TANK-FE
#UPDATES TREE
@app_auth.route('/teams/<string:team_id>/users/<string:user_id>', methods=['DELETE'])
@cognito_auth_required
def remove_team_users(team_id, user_id):

    # AUTH-CHECK
    if not authorization_check('_auth', 'removeTeamUsers', entity_id=team_id):
        return jsonify({"success": False, "message": "Unauthorized", "status": 403}), 403
    
    if get_current_user() == user_id:        
        return jsonify({
            "success": False, 
            "message": "You cannot remove yourself from a team.", 
            "status": 403
        }), 403

    data = {}
    data['user_id'] = user_id
    data['team_id'] = team_id
    
    response = AUC.remove_user_from_team_funnel(**data) 
    
    if not response['success']:
        return jsonify(response), response['status']
    
    refresh_tree()
    return jsonify(response['document']), response['status']



    


#TANK-FE
# UPDATES TREE
@app_auth.route('/teams/<string:portfolio_team_id>', methods=['PUT'])
@cognito_auth_required
def update_team(portfolio_team_id):

    portfolio_id, team_id = portfolio_team_id.split('-', 1)

    # AUTH-CHECK
    if not authorization_check('_auth', 'updateTeam', entity_id=team_id):
        return jsonify({"success": False, "message": "Unauthorized", "status": 403}), 403

    data = request.get_json()
    if data is None:
        return jsonify({"success": False, "message": "Invalid JSON", "status": 400}), 400

    data['ip'] = request.headers.get('X-Forwarded-For', request.remote_addr)
    data['lan'] = request.headers.get('Accept-Language')
    data['user_id'] = get_current_user()
    data['portfolio_id'] = portfolio_id
    data['team_id'] = team_id
    
    type = 'team'
    response = AUC.update_entity(type, **data)
    
    if not response['success']:
        return jsonify(response), response['status']
    
    refresh_tree()
    return jsonify(response), response['status']



#TANK-FE
#UPDATES TREE
@app_auth.route('/teams/<string:portfolio_id>', methods=['POST'])
@cognito_auth_required
def create_team(portfolio_id):

    # AUTH-CHECK
    if not authorization_check('_auth', 'createTeam', entity_id=portfolio_id):
        return jsonify({"success": False, "message": "Unauthorized", "status": 403}), 403

    data = request.get_json()
    if data is None:
        return jsonify({"success": False, "message": "Invalid JSON", "status": 400}), 400

    # Validate required keys in the payload
    required_keys = ['name']  # Adjust as necessary
    if not all(key in data for key in required_keys):
        return jsonify({"success": False, "message": "Missing required attributes", "status": 400}), 400

    data['ip'] = request.headers.get('X-Forwarded-For', request.remote_addr)
    data['lan'] = request.headers.get('Accept-Language')
    data['user_id'] = get_current_user()
    data['portfolio_id'] = portfolio_id

    response = AUC.create_team_funnel(**data)
    
    if not response['success']:
        return jsonify(response), response['status']
    
    refresh_tree()
    return jsonify(response), response['status']





#-------------------------------------------------ROUTES/TOOLS
# _auth/tools/* use a composed id : <TEAM_ID>-<APP_ID>





# TOOL ENTITIES


#NOT USED
@app_auth.route('/portfolios/<string:portfolio_id>/tools/<string:tool_id>', methods=['GET'])
@cognito_auth_required
def get_tool(portfolio_id,tool_id):

    
    #AUTH-CHECK
    if not authorization_check('_auth','getTool',entity_id=tool_id):
        return False
    
    data = {}
    data['portfolio_id'] = portfolio_id
    data['tool_id'] = tool_id
    
    type = 'tool'
    response = AUC.get_entity(type,**data)
    if response['success']:
        return jsonify(response['document']), response['status']
    else:
        return jsonify(response), response['status']



#TANK-FE
# Usage : Used to change the name of the tool (Do you need that?) 
@app_auth.route('/portfolios/<string:portfolio_id>/tools/<string:tool_id>', methods=['PUT'])
@cognito_auth_required
def put_tool(portfolio_id,tool_id):

    # AUTH-CHECK
    if not authorization_check('_auth', 'updateTool', entity_id=tool_id):
        return jsonify({"success": False, "message": "Unauthorized", "status": 403}), 403

    payload = request.get_json()
    if payload is None:
        return jsonify({"success": False, "message": "Invalid JSON", "status": 400}), 400
    
    response_1 = validate_payload(payload, ['name'])
    if not response_1['success']:
        return jsonify(response_1), response_1['status']

    data = {}
    data['payload'] = response_1['document']
    data['ip'] = request.headers.get('X-Forwarded-For', request.remote_addr)
    data['user_id'] = get_current_user()
    data['portfolio_id'] = portfolio_id
    data['tool_id'] = tool_id

    response = AUC.update_entity('tool', **data)
    
    if not response['success']:
        return jsonify(response), response['status']
    
    refresh_tree()
    return jsonify(response), response['status']



#TANK-FE
# Usage: Used to remove a tool
@app_auth.route('/portfolios/<string:portfolio_id>/tools/<string:tool_id>', methods=['DELETE'])
@cognito_auth_required
def delete_tool(portfolio_id, tool_id):

    # AUTH-CHECK
    if not authorization_check('_auth', 'deleteTools', entity_id=tool_id):
        return jsonify({"success": False, "message": "Unauthorized", "status": 403}), 403

    # Get the request data
    data = request.get_json()
    if data is None:
        return jsonify({"success": False, "message": "Invalid JSON", "status": 400}), 400

    data['ip'] = request.headers.get('X-Forwarded-For', request.remote_addr)
    data['user_id'] = get_current_user()
    data['portfolio_id'] = portfolio_id
    data['tool_id'] = tool_id

    response = AUC.remove_tool_funnel(**data)
    
    if not response['success']:
        return jsonify(response), response['status']
    
    refresh_tree()
    return jsonify(response['document']), response['status']




#TANK-FE
# USAGE: Used to create new tools. This is not a common POST action. It needs to link to an existing System Tool. 
# We are not creating the tool, we are linking a system tool to this portfolio.
@app_auth.route('/portfolios/<string:portfolio_id>/tools', methods=['POST'])
#@app_auth.route('tools/<string:portfolio_id>', methods=['POST'])
@cognito_auth_required
def create_tool(portfolio_id):

    # AUTH-CHECK
    if not authorization_check('_auth', 'createTool', entity_id=portfolio_id):
        return jsonify({"success": False, "message": "Unauthorized", "status": 403}), 403

    data = request.get_json()
    if data is None:
        return jsonify({"success": False, "message": "Invalid JSON", "status": 400}), 400

    # Validate required keys in the payload
    required_keys = ['name']  # Adjust as necessary
    if not all(key in data for key in required_keys):
        return jsonify({"success": False, "message": "Missing required attributes", "status": 400}), 400

    data['ip'] = request.headers.get('X-Forwarded-For', request.remote_addr)
    data['lan'] = request.headers.get('Accept-Language')
    data['user_id'] = get_current_user()
    data['portfolio_id'] = portfolio_id
    
    valid_tools = {
                    'data':{
                        'name':'Data',
                        'handle':'data',
                        'about':'Data explorer'
                    }
                 }
    
    if data['name'] in valid_tools:  
        data['handle'] = valid_tools[data['name']]['handle']
        data['about'] = valid_tools[data['handle']]['about']
        data['name'] = valid_tools[data['name']]['name'] #What was sent was the handle, replacing with real name
    else:
        return jsonify({"success": False, "message": "Invalid Tool", "status": 403}), 403
        
        

    response = AUC.create_tool_funnel(**data)
    
    if not response['success']:
        return jsonify(response), response['status']
    
    refresh_tree()
    return jsonify(response), response['status']




#REL

# Assigns/Unassigns tool to a team
@app_auth.route('/teams/<string:team_id>/tools/<string:tool_id>', methods=['POST','DELETE'])
@cognito_auth_required
def assign_team_tools(team_id,tool_id):
    
    # AUTH-CHECK
    if not authorization_check('_auth', 'assignTeamTools', entity_id=team_id):
        return jsonify({"success": False, "message": "Unauthorized", "status": 403}), 403
    
    data = {}
    data['user_id'] = get_current_user()
    data['team_id'] = team_id
    data['tool_id'] = tool_id
    data['method'] = request.method

    response = AUC.assign_team_tools(**data)
    
    if not response['success']:
        return jsonify(response), response['status']
    
    refresh_tree()
    return jsonify(response['document']), response['status']


    

# Assigns/Unassigns tool role to a team
@app_auth.route('/teams/<string:team_id>/tools/<string:tool_id>/roles/<string:role_id>', methods=['POST','DELETE'])
@cognito_auth_required
def assign_team_tool_roles(team_id,tool_id,role_id):
    
    # AUTH-CHECK
    if not authorization_check('_auth', 'assignTeamToolRoles', entity_id=team_id):
        return jsonify({"success": False, "message": "Unauthorized", "status": 403}), 403
    
    data = {}
    data['user_id'] = get_current_user()
    data['team_id'] = team_id
    data['tool_id'] = tool_id
    data['role_id'] = role_id
    data['method'] = request.method

    response = AUC.assign_team_tool_roles(**data)
    
    if not response['success']:
        return jsonify(response), response['status']
    
    refresh_tree()
    return jsonify(response['document']), response['status']
    



# Assigns/UnAssigns tool to org for an specific team
@app_auth.route('/teams/<string:team_id>/tools/<string:tool_id>/orgs/<string:org_id>', methods=['POST','DELETE'])
@cognito_auth_required
def assign_team_tool_org(team_id,tool_id,org_id):
    
    # AUTH-CHECK
    if not authorization_check('_auth', 'assignTeamToolRoles', entity_id=team_id):
        return jsonify({"success": False, "message": "Unauthorized", "status": 403}), 403
    
    data = {}
    data['user_id'] = get_current_user()
    data['team_id'] = team_id
    data['tool_id'] = tool_id
    data['org_id'] = org_id
    data['method'] = request.method

    response = AUC.assign_team_tool_orgs(**data)
    
    if not response['success']:
        return jsonify(response), response['status']
    
    refresh_tree()
    return jsonify(response['document']), response['status']
    


