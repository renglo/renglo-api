#files_routes.py

from flask import Blueprint,request,redirect,url_for, jsonify, current_app, session, render_template, make_response
from flask_cognito import cognito_auth_required, current_user, current_cognito_jwt
from renglo.files.files_controller import FilesController
from renglo.common import create_md5_hash

import time,json,csv
import io
import urllib.parse
import boto3
import mimetypes
import uuid



app_files = Blueprint('app_files', __name__, template_folder='templates',url_prefix='/_files')

# Controllers - will be initialized when blueprint is registered
FCC = None

@app_files.record_once
def on_load(state):
    """Initialize controllers with config when blueprint is registered."""
    global FCC
    config = state.app.renglo_config
    FCC = FilesController(config=config)

valid_types = {
    'image/jpeg':'jpg', 
    'image/png':'png', 
    'image/svg+xml':'svg', 
    'application/pdf':'pdf', 
    'text/plain':'txt', 
    'text/csv':'csv'
}

#AUC = AuthController()
#DAC = DataController()

# Set the route and accepted methods

#DEPRECATED
def upload_file_to_s3(portfolio, org, ring, raw_doc, type):
    
    raw_id = str(uuid.uuid4())
    
    s3_client = boto3.client('s3')
    bucket_name = current_app.config['S3_BUCKET_NAME']  
    filename = f'{raw_id}.{valid_types[type]}'
    file_path = f'_files/{portfolio}/{org}/{ring}/{filename}'
    
    # Determine the content type based on the file type
    content_type = {
        'image/jpeg': 'image/jpeg',
        'image/png': 'image/png',
        'image/svg+xml': 'image/svg+xml',
        'application/pdf': 'application/pdf',
        'text/plain': 'text/plain',
        'text/csv': 'text/csv'
    }.get(type, 'application/octet-stream')  # Default to 'application/octet-stream' if not found

    # Upload to S3 with the specified content type
    response = s3_client.put_object(
        Bucket=bucket_name,
        Key=file_path,
        Body=raw_doc,
        ContentType=content_type  # Set the content type here
    )
    
    if response['ResponseMetadata']['HTTPStatusCode'] == 200:
        
        result = {}
        result['success'] = True
        result['path'] = file_path 
        result['id'] = raw_id 
        
        return result
    
    return jsonify({'success': False})




#--- ROUTES


@app_files.route('/')
@cognito_auth_required
def index():
   #Nothing to show here
    return jsonify(message='')


def _redirect_to_s3(response):
    """Send the browser to S3. Lambda never reads or returns file bytes."""
    if not response or not response.get('success') or not response.get('url'):
        status = int(response.get('status') or 404) if response else 404
        if status not in (400, 401, 403, 404, 500):
            status = 404
        return (
            jsonify(
                success=False,
                error=(response or {}).get('error')
                or (response or {}).get('message')
                or 'File not found',
            ),
            status,
        )
    out = redirect(response['url'], code=302)
    # Do not cache the signed Location — it expires. The browser refetches /_files.
    out.headers.set('Cache-Control', 'private, no-store')
    return out


def _cognito_user_handle():
    if 'cognito:username' in current_cognito_jwt:
        username = current_cognito_jwt['cognito:username']
    else:
        username = current_cognito_jwt['username']
    return create_md5_hash(username, 9)


# POST user profile thumbnail (auth/thumbnails/{handle}.png in S3)
@app_files.route('/auth/thumbnails', methods=['POST'])
@cognito_auth_required
def route_user_thumbnail_post():
    up_file = request.files.get('up_file')
    up_file_type = request.form.get('up_file_type')

    if not up_file:
        return jsonify(success=False, message='Invalid file'), 400

    handle = _cognito_user_handle()
    raw_content = up_file.read()
    response = FCC.user_thumbnail_post(handle, raw_content, up_file_type)

    if not response.get('success'):
        return jsonify(response), 400
    return jsonify(response), 200


# GET user profile thumbnail — 302 to S3 (no bytes through Lambda)
@app_files.route('/auth/thumbnails/<string:handle>.png', methods=['GET'])
def route_user_thumbnail_get(handle):
    return _redirect_to_s3(FCC.user_thumbnail_presign(handle))



# POST A FILE TO UPLOAD TO S3
@app_files.route('/<string:portfolio>/<string:org>/<string:ring>', methods=['POST'])
@cognito_auth_required
def route_a_b_post(portfolio,org,ring):
    
    up_file = request.files.get('up_file')  # Get uploaded file binary
    up_file_type = request.form.get('up_file_type')  # Get uploaded file binary
    up_file_override = request.form.get('up_file_override')  # Optional. Use this name instead of randomly generated UUID
    if up_file_override is None:
        up_file_override = str(uuid.uuid4())  # Use a randomly generated UUID if not provided
    
    current_app.logger.debug('up_file:')
    current_app.logger.debug(up_file)
    
    if up_file:
        raw_content = up_file.read()  # Read the file content without decoding yet
              
        # Basic verification based on file type
           
        response = FCC.a_b_post(portfolio,org,ring,raw_content,up_file_type,up_file_override)
        
        
        if not response['success']:      
            return jsonify(response), response.get('status', 400)
        return jsonify(response), 200
               
    return jsonify(success=False, message='Invalid file'), 400


# GET a transient JSON document (S3 tmp: portfolio / org / entity / YYYY-MM-DD / object_id).
# Keep proxying JSON: it is UTF-8 (safe on API Gateway) and the console fetch()es it
# with a bearer token. Images/files below redirect to S3 instead.
@app_files.route(
    '/<string:portfolio>/<string:org>/<string:entity>/<string:date>/<string:object_id>',
    methods=['GET'],
)
def route_tmp_artifact_get(portfolio, org, entity, date, object_id):
    response = FCC.tmp_get(portfolio, org, entity, date, object_id)
    if not response['success']:
        return (
            jsonify(
                success=False,
                error=response.get('error', 'File not found'),
            ),
            404,
        )
    content = response.get('content', b'')
    content_type = response.get('content_type', 'application/json')
    out = make_response(content)
    out.headers.set('Content-Type', content_type)
    return out, 200


# GET A FILE FROM S3 (4-tuple: portfolio / org / ring / filename) — 302 to S3
@app_files.route('/<string:portfolio>/<string:org>/<string:ring>/<string:filename>', methods=['GET'])
def route_a_b_c_get(portfolio,org,ring,filename):
    # Thumbnails are embedded in <img> tags and cannot send JWT headers.
    if ring == '_thumbnails':
        response = FCC.a_b_c_presign_public(portfolio, org, ring, filename)
    else:
        response = FCC.a_b_c_presign(portfolio, org, ring, filename)
    return _redirect_to_s3(response)


# DELETE A FILE IN S3 (NOT IMPLEMENTED)
@app_files.route('/<string:portfolio>/<string:org>/<string:ring>/<string:filename>', methods=['DELETE'])
@cognito_auth_required
def route_a_b_c_delete(portfolio,org,ring,idx):

    return False

    
