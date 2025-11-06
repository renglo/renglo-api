#docs_routes.py

from flask import Blueprint,request,redirect,url_for, jsonify, current_app, session, render_template, make_response
from flask_cognito import cognito_auth_required, current_user, current_cognito_jwt
from renglo.docs.docs_controller import DocsController

import time,json,csv
import io
import urllib.parse
import boto3
import mimetypes
import uuid



app_docs = Blueprint('app_docs', __name__, template_folder='templates',url_prefix='/_docs')

# Controllers - will be initialized when blueprint is registered
DCC = None

@app_docs.record_once
def on_load(state):
    """Initialize controllers with config when blueprint is registered."""
    global DCC
    config = state.app.renglo_config
    DCC = DocsController(config=config)

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
def upload_doc_to_s3(portfolio, org, ring, raw_doc, type):
    
    raw_id = str(uuid.uuid4())
    
    s3_client = boto3.client('s3')
    bucket_name = current_app.config['S3_BUCKET_NAME']  
    filename = f'{raw_id}.{valid_types[type]}'
    file_path = f'_docs/{portfolio}/{org}/{ring}/{filename}'
    
    # Determine the content type based on the file type
    content_type = {
        'image/jpeg': 'image/jpeg',
        'image/png': 'image/png',
        'image/svg+xml': 'image/svg+xml',
        'application/pdf': 'application/pdf',
        'text/plain': 'text/plain',
        'text/csv': 'text/csv'
    }.get(type, 'application/octet-stream')  # Default to application/octet-stream if not found

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


@app_docs.route('/')
@cognito_auth_required
def index():
   #Nothing to show here
    return jsonify(message='')



# POST A DOCUMENT TO UPLOAD TO S3
@app_docs.route('/<string:portfolio>/<string:org>/<string:ring>', methods=['POST'])
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
           
        response = DCC.a_b_post(portfolio,org,ring,raw_content,up_file_type,up_file_override)
        
        
        if not response['success']:      
            return jsonify(response), 400
        return jsonify(response), 200
               
    return jsonify(success=False, message='Invalid file'), 400


# GET A DOCUMENT FROM S3
@app_docs.route('/<string:portfolio>/<string:org>/<string:ring>/<string:filename>', methods=['GET'])
def route_a_b_c_get(portfolio,org,ring,filename):
    
    #return get_doc_from_s3(portfolio,org,ring,filename)
    response = DCC.a_b_c_get(portfolio,org,ring,filename)
    
    if not response['success']:
        current_app.logger.error(f"File not found {filename}, returning default image instead")
        
        # Serve the default image instead of returning an error
        default_image_path = '_static/yellow.png'  # Path to your default image
        with open(default_image_path, 'rb') as default_image:
            content = default_image.read()
            response_2 = make_response(content)
            response_2.headers.set('Content-Type', 'image/png')  # Set the correct content type for the image
            return response_2, 200  # Return the default image with a 200 status code
    
    return response['content'], 200
    
    


    


 
# DELETE A DOCUMENT IN S3 (NOT IMPLEMENTED)
@app_docs.route('/<string:portfolio>/<string:org>/<string:ring>/<string:filename>', methods=['DELETE'])
@cognito_auth_required
def route_a_b_c_delete(portfolio,org,ring,idx):

    return False

    
