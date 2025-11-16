#app_data.py
from flask import Blueprint,request,redirect,url_for, jsonify, current_app, session, render_template, make_response
from renglo.auth.login_required import login_required

from flask_cognito import cognito_auth_required, current_user, current_cognito_jwt

from renglo.schd.schd_controller import SchdController

import time
import random

app_schd = Blueprint('app_scheduler', __name__, template_folder='templates',url_prefix='/_schd')

# Controllers - will be initialized when blueprint is registered
SHC = None
BASE_URL = None

@app_schd.record_once
def on_load(state):
    """Initialize controllers with config when blueprint is registered."""
    global SHC, BASE_URL
    config = state.app.renglo_config
    SHC = SchdController(config=config)
    BASE_URL = config.get('BASE_URL', '')



# Set the route and accepted methods

@app_schd.route('/')
@cognito_auth_required
def index():
   #Nothing to show here
    return jsonify(message='')


@app_schd.route('/time')
def timex():
    session['current_user'] = '7e5fb15bb'
    return {
        'time': time.time(),  # This should work correctly now
    }
   

# Cron Rules

#NOT IMPLEMENTED
# Used to get a list of cron rules in an organization
@app_schd.route('/<string:portfolio>/<string:org>/schd_rules',methods=['GET'])
@cognito_auth_required
def list_rules(portfolio,org):   
    return {'success':False}



# Used to get information about an existing rule (it should reflect eventBridge)
@app_schd.route('/<string:portfolio>/<string:org>/rules/<string:name>',methods=['GET'])
@cognito_auth_required
def get_rule(portfolio,org,name): 

    response = SHC.find_rule(portfolio,org,name)

    return response


# Used to create a new cron rule
@app_schd.route('/<string:portfolio>/<string:org>/rules',methods=['POST'])
@cognito_auth_required
def create_rule(portfolio,org):   
    action = "create_rule"
    current_app.logger.info('Creating new Rule')
    
    payload = request.get_json() 
    
    event_payload = {
      'portfolio':portfolio,
      'org':org,  
      'schd_jobs_id': payload['schd_jobs_id'], 
      'trigger': payload['trigger'], 
      'author': payload['author'], 
    }
      
    response = SHC.create_rule(portfolio,org,payload['timer'],payload['schedule_expression'],event_payload)
    status = 200 if response['success'] else 400
      
    return {'success':response['success'],'action':action,'input':payload,'output':response}, status


# Used if you don't want a recurring run to be executed anymore. 
@app_schd.route('/<string:portfolio>/<string:org>/rules/<string:name>',methods=['DELETE'])
@cognito_auth_required
def delete_rule(portfolio,org,name):   
    action = "delete_rule"
    current_app.logger.info('Deleting a Rule')  
    response = SHC.remove_rule(portfolio,org,name)
      
    return {'success':response['success'],'action':action,'input':name,'output':response}


# Job Types

#NOT IMPLEMENTED
# Used to get a list of available jobs for an organization
@app_schd.route('/<string:portfolio>/<string:org>/schd_jobs',methods=['GET'])
@cognito_auth_required
def list_jobs(portfolio,org):   
    return {'success':False}

#NOT IMPLEMENTED
# Used to get information about a job type
@app_schd.route('/<string:portfolio>/<string:org>/schd_jobs/<string:idx>',methods=['GET'])
@cognito_auth_required
def get_job(portfolio,org,idx):   
    return {'success':False}

#NOT IMPLEMENTED
# Used to create a new job type
@app_schd.route('/<string:portfolio>/<string:org>/schd_jobs',methods=['POST'])
@cognito_auth_required
def create_job(portfolio,org):   
    return {'success':False}

#NOT IMPLEMENTED
# Used to modify the parameters of an existing job
@app_schd.route('/<string:portfolio>/<string:org>/schd_jobs/<string:idx>',methods=['PUT'])
@cognito_auth_required
def update_job(portfolio,org,idx):   
    return {'success':False}

#NOT IMPLEMENTED
# Used to delete a Job type that is no longer needed
@app_schd.route('/<string:portfolio>/<string:org>/schd_jobs/<string:idx>',methods=['DELETE'])
@cognito_auth_required
def delete_job(portfolio,org,idx):   
    return {'success':False}



# Job Runs

#NOT IMPLEMENTED
# Used to get a list of runs in the organization (for troubleshooting purposes)
@app_schd.route('/<string:portfolio>/<string:org>/schd_runs',methods=['GET'])
@cognito_auth_required
def list_runs(portfolio,org):   
    return {'success':False}

#NOT IMPLEMENTED
# Used to check the results of a run (for troubleshooting purposes)
@app_schd.route('/<string:portfolio>/<string:org>/schd_runs/<string:idx>',methods=['GET'])
@cognito_auth_required
def get_run(portfolio,org,idx):   
    return {'success':False}


# Used to trigger a job execution
@app_schd.route('/<string:portfolio>/<string:org>/create_job_run',methods=['POST'])
@cognito_auth_required
def create_job_run(portfolio,org):  
    
    payload = request.get_json()
    response, status = SHC.create_job_run(portfolio,org,payload)
    
    return jsonify(response), status


#NOT IMPLEMENTED
# Used to update the run document with the results of the run
@app_schd.route('/<string:portfolio>/<string:org>/schd_runs/<string:idx>',methods=['PUT'])
@cognito_auth_required
def update_run(portfolio,org,idx):   
    return {'success':False}

#NOT IMPLEMENTED
# Used to delete a job run (not usual)
@app_schd.route('/<string:portfolio>/<string:org>/schd_runs/<string:idx>',methods=['DELETE'])
@cognito_auth_required
def delete_run(portfolio,org,idx):   
    return {'success':False}







# Used as a dummy endpoint
@app_schd.route('/ping/',methods=['POST'])
def ping():

    timex = time.time()
    current_app.logger.info(f'Executing Run @::{timex}') 
    #return {'success':False,'action':'execute_run','output':timex}

    payload = request.get_json()
    current_app.logger.info(payload)
    response, status = SHC.create_job_run(payload['portfolio'],payload['org'],payload)
    
    return jsonify(response), status



# Direct handler runs
@app_schd.route('/run/<string:tool>/<string:handler>',methods=['POST'])
@cognito_auth_required
def direct_run(tool,handler):
    
    current_app.logger.info('Running: '+tool+'/'+handler)
    handler_route = tool+'/'+handler
    
    payload = request.get_json()
    payload['handler'] = handler_route
    response, status = SHC.direct_run(handler_route,payload)
    
    return jsonify(response), status


# Direct handler runs
@app_schd.route('/<string:portfolio>/<string:org>/call/<string:tool>/<string:handler>',methods=['POST'])
@cognito_auth_required
def handler_call(portfolio,org,tool,handler):
    
    current_app.logger.info('Running: '+tool+'/'+handler)
    payload = request.get_json() 
    response = SHC.handler_call(portfolio,org,tool,handler,payload)
    
    if not response['success']:
        return jsonify(response), 400
    
    return jsonify(response), 200



def token_authenticate(request):
    
    # Verify that the request originates from the application.
    if request.args.get("token", "") != current_app.config["PUBSUB_VERIFICATION_TOKEN"]:
        return "Invalid request", 400

    # Verify that the push request originates from Cloud Pub/Sub.
    try:
        # Get the Cloud Pub/Sub-generated JWT in the "Authorization" header.
        bearer_token = request.headers.get("Authorization")
        token = bearer_token.split(" ")[1]
        TOKENS.append(token)

        # Verify and decode the JWT. `verify_oauth2_token` verifies
        # the JWT signature, the `aud` claim, and the `exp` claim.
        # Note: For high volume push requests, it would save some network
        # overhead if you verify the tokens offline by downloading Google's
        # Public Cert and decode them using the `google.auth.jwt` module;
        # caching already seen tokens works best when a large volume of
        # messages have prompted a single push server to handle them, in which
        # case they would all share the same token for a limited time window.
        claim = id_token.verify_oauth2_token(
            token, requests.Request(), audience="example.com"
        )

        # IMPORTANT: you should validate claim details not covered by signature
        # and audience verification above, including:
        #   - Ensure that `claim["email"]` is equal to the expected service
        #     account set up in the push subscription settings.
        #   - Ensure that `claim["email_verified"]` is set to true.

        CLAIMS.append(claim)
    except Exception as e:
        return f"Invalid token: {e}\n", 400

    envelope = json.loads(request.data.decode("utf-8"))
    payload = base64.b64decode(envelope["message"]["data"])
    MESSAGES.append(payload)
    # Returning any 2xx status indicates successful receipt of the message.
    return "OK", 200



# Direct handler runs
# /_schd/28b8f19add5b/872756a25793/webhook/gmail/message_in
@app_schd.route('/<string:portfolio>/<string:org>/webhook/<string:tool>/<string:handler>',methods=['POST'])
def webhook_call(portfolio,org,tool,handler):
    
    # IMPLEMENT AUTHENTICATION HERE!!!
    #auth_result = token_authenticate(request)
    
    
    current_app.logger.info('Running: '+tool+'/'+handler)
    payload = request.get_json() 
    response = SHC.handler_call(portfolio,org,tool,handler,payload)
    
    if not response['success']:
        if 'status' in response:
            print(f'WEBHOOK TRACE ({response['status']}):',response)
        else:
            print('WEBHOOK TRACE (400):', response)
    else:
        if 'status' in response:
            print(f'WEBHOOK TRACE ({response['status']}):',response)
        else:
            print('WEBHOOK TRACE (200):',response)


    return '', 200  # Empty response with 200 status for Pub/Sub ACK



