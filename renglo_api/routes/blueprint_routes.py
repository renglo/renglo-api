from flask import Blueprint,request,redirect,url_for, jsonify, current_app, session
from renglo.auth.login_required import login_required
from flask_cognito import cognito_auth_required, current_user, current_cognito_jwt


#from app_blueprint.dispatchers_blueprint import blueprint_dispatcher
 
from datetime import datetime
from renglo.blueprint.blueprint_controller import BlueprintController


app_blueprint = Blueprint('app_blueprint', __name__, template_folder='templates',url_prefix='/_blueprint')

# Controllers - will be initialized when blueprint is registered
BPC = None

@app_blueprint.record_once
def on_load(state):
    """Initialize controllers with config when blueprint is registered."""
    global BPC
    config = state.app.renglo_config
    BPC = BlueprintController(config=config)


# Set the route and accepted methods

@app_blueprint.route('/t0')
@login_required
def index():

    current_app.logger.info(f'Handle: {session["current_user"]}')
    return jsonify(message=session["current_user"])


  

@app_blueprint.route('/t1')
def t1():

    current_app.logger.info('t1')
    return jsonify(message="t1b")


@app_blueprint.route('/t2')
@login_required
def t2():

    current_app.logger.info('t2')
    return jsonify(message="t2")


  

@app_blueprint.route('/', methods=['POST'])
def create_blueprint():

    data = request.json
    return BPC.create_blueprint(data)



@app_blueprint.route('/c:clone', methods=['GET'])
@login_required
def clone_blueprint():

    return jsonify(BPC.clone_blueprint())



@app_blueprint.route('/c:branch', methods=['GET'])
@login_required
def branch_blueprint():

    return jsonify(BPC.branch_blueprint())



  

@app_blueprint.route('/<string:handle>/<string:name>', methods=['GET'])
def get_blueprint(handle,name):
    if request.args.get("v"):
        v = request.args.get("v")
    else:
        v = 'last'
  
    return jsonify(BPC.get_blueprint(handle,name,v))

  

@app_blueprint.route('/<string:handle>/<string:name>/<string:v>', methods=['GET'])
def get_blueprint_v(handle,name,v):

    return BPC.get_blueprint(handle,name,v)

  

@app_blueprint.route('/<string:handle>/<string:name>', methods=['PUT'])
def update_blueprint(handle, name):

    return BPC.update_blueprint(handle,name)


  

@app_blueprint.route('/<string:handle>/<string:name>/<string:v>', methods=['DELETE'])
def delete_blueprint(handle, name, v):

    return BPC.delete_blueprint(handle,name,v)


