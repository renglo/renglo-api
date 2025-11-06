from flask import Blueprint,request,redirect,url_for, jsonify, current_app, session
from renglo.auth.login_required import login_required
from flask_cognito import cognito_auth_required, current_user, current_cognito_jwt



from datetime import datetime
from renglo.state.state_controller import StateController


app_state = Blueprint('app_state', __name__, template_folder='templates',url_prefix='/_state')

# Controllers - will be initialized when blueprint is registered
STC = None

@app_state.record_once
def on_load(state):
    """Initialize controllers with config when blueprint is registered."""
    global STC
    config = state.app.renglo_config
    STC = StateController(config=config)



@app_state.route('/<string:name>', methods=['GET'])
def get_state(name):
    if request.args.get("v"):
        v = request.args.get("v")
    else:
        v = 'last'
  
    return jsonify(STC.get_state(name,v))

  
@app_state.route('/<string:name>/<string:v>', methods=['GET'])
def get_state_v(handle,name,v):

    return STC.get_state(name,v)
