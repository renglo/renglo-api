#app_data.py
from flask import Blueprint,request,redirect,url_for, jsonify, current_app, session, render_template, make_response
from renglo.auth.login_required import login_required

from flask_cognito import cognito_auth_required, current_user, current_cognito_jwt

from renglo.schd.schd_controller import SchdController
from renglo_api.routes.schd_ingress import (
    check_ingress_secret,
    dispatch_ingress,
    normalize_detail,
    presented_ingress_secret,
    resolve_ingress_secret,
)

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


@app_schd.route('/clock')
@cognito_auth_required
def schd_clock():
    from renglo.schd.schd_machine_id import schd_machine_id as _mid
    url = (SHC.config or {}).get("EVENTBRIDGE_EMULATOR_URL") or "http://127.0.0.1:5056"
    return jsonify(
        {
            "success": True,
            "schd_machine_id": _mid(),
            "eventbridge_emulator_url": url,
        }
    )


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


def _job_write(portfolio, org, payload, job_id=None):
    payload = dict(payload or {})
    if job_id:
        payload["schd_jobs_id"] = job_id
    kind = str(payload.get("schedule_kind") or "").strip()
    if kind == "heartbeat" or payload.get("heartbeat_id"):
        return SHC.subscribe(portfolio, org, payload)
    if kind == "once" or payload.get("run_at"):
        return SHC.schedule_once(portfolio, org, payload)
    if kind == "custom" or payload.get("schedule_expression"):
        return SHC.schedule_custom(portfolio, org, payload)
    return SHC.subscribe(portfolio, org, {**payload, "schedule_kind": "heartbeat"})


@app_schd.route('/<string:portfolio>/<string:org>/heartbeats', methods=['GET'])
@cognito_auth_required
def list_heartbeats(portfolio, org):
    return jsonify(SHC.list_heartbeats(portfolio, org))


@app_schd.route('/<string:portfolio>/<string:org>/heartbeats', methods=['POST'])
@cognito_auth_required
def set_heartbeat(portfolio, org):
    payload = request.get_json() or {}
    if str(payload.get("action") or "").strip() == "ensure":
        return jsonify(SHC.ensure_heartbeats(portfolio, org))
    heartbeat_id = str(payload.get("heartbeat_id") or payload.get("handle") or "").strip()
    status = str(payload.get("status") or "enabled").strip()
    if not heartbeat_id:
        return jsonify({"success": False, "message": "heartbeat_id required"}), 400
    return jsonify(SHC.set_heartbeat_status(portfolio, org, heartbeat_id, status))


@app_schd.route('/<string:portfolio>/<string:org>/heartbeats/ensure', methods=['POST'])
@cognito_auth_required
def ensure_heartbeats(portfolio, org):
    return jsonify(SHC.ensure_heartbeats(portfolio, org))


@app_schd.route('/<string:portfolio>/<string:org>/heartbeats/<string:heartbeat_id>/jobs', methods=['GET'])
@cognito_auth_required
def list_heartbeat_jobs(portfolio, org, heartbeat_id):
    listed = SHC.list_jobs(portfolio, org, origin=request.args.get("origin") or "cloud")
    items = [
        job
        for job in listed.get("items") or []
        if str(job.get("heartbeat_id") or "") == heartbeat_id
    ]
    return jsonify({"success": True, "items": items, "count": len(items)})


@app_schd.route('/<string:portfolio>/<string:org>/jobs', methods=['GET'])
@app_schd.route('/<string:portfolio>/<string:org>/schd_jobs', methods=['GET'])
@cognito_auth_required
def list_jobs(portfolio, org):
    origin = request.args.get("origin") or "cloud"
    return jsonify(SHC.list_jobs(portfolio, org, origin=origin))


@app_schd.route('/<string:portfolio>/<string:org>/jobs/<string:idx>', methods=['GET'])
@app_schd.route('/<string:portfolio>/<string:org>/schd_jobs/<string:idx>', methods=['GET'])
@cognito_auth_required
def get_job(portfolio, org, idx):
    response = SHC.get_job(portfolio, org, idx)
    return jsonify(response), (200 if response.get("success") else 404)


@app_schd.route('/<string:portfolio>/<string:org>/jobs', methods=['POST'])
@app_schd.route('/<string:portfolio>/<string:org>/schd_jobs', methods=['POST'])
@cognito_auth_required
def create_job(portfolio, org):
    payload = request.get_json() or {}
    response = _job_write(portfolio, org, payload)
    return jsonify(response), (200 if response.get("success") else 400)


@app_schd.route('/<string:portfolio>/<string:org>/jobs/<string:idx>', methods=['PUT'])
@app_schd.route('/<string:portfolio>/<string:org>/schd_jobs/<string:idx>', methods=['PUT'])
@cognito_auth_required
def update_job(portfolio, org, idx):
    payload = request.get_json() or {}
    if "enabled" in payload and len(payload) == 1:
        enabled = str(payload.get("enabled")).lower() in {"1", "true", "yes", "enabled"}
        response = SHC.resume_job(portfolio, org, idx) if enabled else SHC.pause_job(portfolio, org, idx)
        return jsonify(response), (200 if response.get("success") else 400)
    response = _job_write(portfolio, org, payload, job_id=idx)
    return jsonify(response), (200 if response.get("success") else 400)


@app_schd.route('/<string:portfolio>/<string:org>/jobs/<string:idx>', methods=['DELETE'])
@app_schd.route('/<string:portfolio>/<string:org>/schd_jobs/<string:idx>', methods=['DELETE'])
@cognito_auth_required
def delete_job(portfolio, org, idx):
    response = SHC.unsubscribe(portfolio, org, idx)
    return jsonify(response), (200 if response.get("success") else 400)


@app_schd.route('/<string:portfolio>/<string:org>/jobs/<string:idx>/run', methods=['POST'])
@cognito_auth_required
def run_job_now(portfolio, org, idx):
    payload = request.get_json(silent=True) or {}
    response = SHC.run_now(portfolio, org, idx, payload)
    return jsonify(response), (200 if response.get("success") else 400)


@app_schd.route('/<string:portfolio>/<string:org>/activity', methods=['GET'])
@cognito_auth_required
def list_activity(portfolio, org):
    days = request.args.get("days", 7)
    limit = request.args.get("limit", 100)
    event_type = request.args.get("event_type", "")
    schd_jobs_id = request.args.get("schd_jobs_id", "")
    try:
        days_n = int(days)
    except (TypeError, ValueError):
        days_n = 7
    try:
        limit_n = int(limit)
    except (TypeError, ValueError):
        limit_n = 100
    return jsonify(
        SHC.list_activity(
            portfolio,
            org,
            days=days_n,
            limit=limit_n,
            event_type=event_type,
            schd_jobs_id=schd_jobs_id,
            origin=request.args.get("origin") or "cloud",
        )
    )


@app_schd.route('/<string:portfolio>/<string:org>/activity/<string:event_id>', methods=['GET'])
@cognito_auth_required
def get_activity(portfolio, org, event_id):
    response = SHC.get_activity(
        portfolio, org, event_id, origin=request.args.get("origin") or "cloud"
    )
    return jsonify(response), (200 if response.get("success") else 404)


@app_schd.route('/<string:portfolio>/<string:org>/schd_runs', methods=['GET'])
@cognito_auth_required
def list_runs(portfolio, org):
    return jsonify({"success": False, "message": "schd_runs is retired; use GET /activity"}), 410


@app_schd.route('/<string:portfolio>/<string:org>/schd_runs/<string:idx>', methods=['GET'])
@cognito_auth_required
def get_run(portfolio, org, idx):
    return jsonify({"success": False, "message": "schd_runs is retired; use GET /activity"}), 410


# Used to trigger a job execution
@app_schd.route('/<string:portfolio>/<string:org>/create_job_run',methods=['POST'])
@cognito_auth_required
def create_job_run(portfolio,org):  
    
    payload = request.get_json()
    response, status = SHC.create_job_run(portfolio,org,payload)
    
    return jsonify(response), status


@app_schd.route('/<string:portfolio>/<string:org>/schd_runs/<string:idx>',methods=['PUT'])
@cognito_auth_required
def update_run(portfolio,org,idx):
    return jsonify({"success": False, "message": "schd_runs is retired; use GET /activity"}), 410


@app_schd.route('/<string:portfolio>/<string:org>/schd_runs/<string:idx>',methods=['DELETE'])
@cognito_auth_required
def delete_run(portfolio,org,idx):
    return jsonify({"success": False, "message": "schd_runs is retired; use GET /activity"}), 410







def _ingress_auth_or_401():
    """Enforce shared ingress secret when configured. Returns Response or None."""
    app_cfg = getattr(current_app, 'renglo_config', None) or {}
    expected = resolve_ingress_secret(app_cfg, current_app.config)
    ok, err, status = check_ingress_secret(
        expected=expected,
        presented=presented_ingress_secret(request.headers),
    )
    if not ok:
        current_app.logger.warning('Ingress secret mismatch')
        return jsonify(err), status
    return None


def _run_ingress_dispatch(detail: dict):
    return dispatch_ingress(
        detail,
        load_and_run=SHC.SHL.load_and_run,
        create_job_run=SHC.create_job_run,
        dispatch_heartbeat=SHC.dispatch_heartbeat,
    )


# Universal EventBridge → API entry (webhooks, heartbeats, scheduled jobs).
@app_schd.route('/ingress', methods=['POST'])
@app_schd.route('/ingress/', methods=['POST'])
def process_ingress():
    denied = _ingress_auth_or_401()
    if denied is not None:
        return denied

    event_data = request.get_json(silent=True) or {}
    detail = normalize_detail(event_data)
    if detail is None:
        return jsonify({'success': False, 'message': 'Invalid or missing detail'}), 400

    current_app.logger.info('Processing ingress type=%s', detail.get('type'))
    response, status = _run_ingress_dispatch(detail)
    return jsonify(response), status


# Direct handler runs
@app_schd.route('/run/<string:extension>/<string:handler>',methods=['POST'])
@cognito_auth_required
def direct_run(extension,handler):
    
    current_app.logger.info('Running: '+extension+'/'+handler)
    handler_route = extension+'/'+handler
    
    payload = request.get_json()
    payload['handler'] = handler_route
    response, status = SHC.direct_run(handler_route,payload)
    
    return jsonify(response), status


# Direct handler runs
@app_schd.route('/<string:portfolio>/<string:org>/call/<string:extension>/<string:handler>',methods=['POST'])
@cognito_auth_required
def handler_call(portfolio,org,extension,handler):
    
    current_app.logger.info('Running: '+extension+'/'+handler)
    payload = request.get_json() 
    response = SHC.handler_call(portfolio,org,extension,handler,payload)
    
    if not response['success']:
        return jsonify(response), 400
    
    return jsonify(response), 200



# Batch start: return 202 with request_id and task_id (client polls batch/result and batch/logs)
@app_schd.route('/<string:portfolio>/<string:org>/call/<string:extension>/<string:handler>/start', methods=['POST'])
@cognito_auth_required
def handler_call_batch_start(portfolio, org, extension, handler):
    current_app.logger.info('Batch start: %s/%s', extension, handler)
    payload = request.get_json() or {}
    response = SHC.handler_call_batch_start(portfolio, org, extension, handler, payload)
    if not response.get('success'):
        return jsonify(response), 400
    return jsonify(response), 202


# Batch result: GET result from S3 (pending until task writes)
@app_schd.route('/<string:portfolio>/<string:org>/batch/result', methods=['GET'])
@cognito_auth_required
def batch_result(portfolio, org):
    extension = request.args.get('extension', '').strip()
    request_id = request.args.get('request_id', '').strip()
    if not extension or not request_id:
        return jsonify({'success': False, 'error': 'extension and request_id required'}), 400
    response = SHC.get_batch_result(portfolio, org, extension, request_id)
    if response.get('status') == 'pending':
        return jsonify(response), 200
    return jsonify(response), 200


# Batch status: GET progress from S3 (status/<request_id>.json)
@app_schd.route('/<string:portfolio>/<string:org>/batch/status', methods=['GET'])
@cognito_auth_required
def batch_status(portfolio, org):
    extension = request.args.get('extension', '').strip()
    request_id = request.args.get('request_id', '').strip()
    if not extension or not request_id:
        return jsonify({'success': False, 'error': 'extension and request_id required'}), 400
    response = SHC.get_batch_status(portfolio, org, extension, request_id)
    return jsonify(response), 200


# Direct subhandler runs
@app_schd.route('/<string:portfolio>/<string:org>/call/<string:extension>/<string:handler>/<string:subhandler>',methods=['POST'])
@cognito_auth_required
def subhandler_call(portfolio,org,extension,handler,subhandler):
    
    current_app.logger.info('Running: '+extension+'/'+handler+'/'+subhandler)
    payload = request.get_json() 
    shandler = f'{handler}/{subhandler}'
    response = SHC.handler_call(portfolio,org,extension,shandler,payload)
    
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
@app_schd.route('/<string:portfolio>/<string:org>/webhook/<string:extension>/<string:handler>',methods=['POST'])
def webhook_call(portfolio,org,extension,handler):
    
    # IMPLEMENT AUTHENTICATION HERE!!!
    #auth_result = token_authenticate(request)
    
    
    current_app.logger.info('Running: '+extension+'/'+handler)
    payload = request.get_json() 
    response = SHC.handler_call(portfolio,org,extension,handler,payload)
    
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


# Google OAuth callback for Gmail agent mailbox Connect (no Cognito).
# Redirect URI registered on each org's GCP OAuth client:
#   {BASE_URL}/_schd/gmail/oauth_callback
@app_schd.route('/gmail/oauth_callback', methods=['GET'])
@app_schd.route('/gmail/oauth_callback/', methods=['GET'])
def gmail_oauth_callback():
    payload = {
        'code': request.args.get('code') or '',
        'state': request.args.get('state') or '',
        'error': request.args.get('error') or '',
        'error_description': request.args.get('error_description') or '',
    }
    response = SHC.SHL.load_and_run('gmail/oauth_callback', payload=payload)
    redirect_url = ''
    if isinstance(response, dict):
        outer = response.get('output')
        if isinstance(outer, dict):
            redirect_url = outer.get('redirect_url') or ''
            nested = outer.get('output')
            if not redirect_url and isinstance(nested, dict):
                redirect_url = nested.get('redirect_url') or ''
        if not redirect_url:
            redirect_url = response.get('redirect_url') or ''
    if redirect_url:
        return redirect(redirect_url)
    current_app.logger.error('Gmail OAuth callback missing redirect_url: %s', response)
    return jsonify({'success': False, 'message': 'OAuth callback failed', 'output': response}), 400

