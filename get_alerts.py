import json
import boto3
import os
import ssl
import certifi
from botocore.exceptions import ClientError
from datetime import datetime, timezone
from secrets import choice
from string import ascii_letters, digits
from hashlib import sha256
import urllib3
# env variables
# COUNT_PER_PAGE
# MAX_PAGES
# S3_BUCKET - bucket name
# there is a need to set ssm see line 227
# Disable SSL warnings for self-signed certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def get_ssm_parameter(parameter_name):
    """
    Retrieve sensitive parameters from AWS Systems Manager Parameter Store.
    
    :param parameter_name: Name of the SSM parameter
    :return: Parameter value
    """
    ssm_client = boto3.client('ssm')
    try:
        response = ssm_client.get_parameter(
            Name=parameter_name,
            WithDecryption=True
        )
        return response['Parameter']['Value']
    except Exception as e:
        print(f"Error retrieving SSM parameter {parameter_name}: {e}")
        raise

def get_headers(key_id, key, key_type):
    """Generate authentication headers for Cortex API."""
    headers = {}
    if key_type == 'advanced':
        nonce = ''.join([choice(ascii_letters + digits) for _ in range(64)])
        timestamp = int(datetime.now(timezone.utc).timestamp()) * 1000
        auth_key = f'{key}{nonce}{timestamp}'
        headers = {
            'x-xdr-timestamp': str(timestamp),
            'x-xdr-nonce': nonce,
            'x-xdr-auth-id': str(key_id),
            'Authorization': sha256(auth_key.encode('utf-8')).hexdigest()
        }
    else:
        headers = {
            'Authorization': key,
            'x-xdr-auth-id': str(key_id)
        }
    return headers

def get_payload(start, end, additional_filters=None):
    """
    Create a flexible payload for API request.
    
    :param start: Starting index for pagination
    :param end: Ending index for pagination
    :param additional_filters: Optional list of additional filters
    :return: Payload dictionary
    """
    # Default severity filters
    default_filters = [
        {
            'field': 'severity',
            'operator': 'in',
            'value': ['low', 'medium', 'high']
        }
    ]
    
    # Merge default and additional filters if provided
    filters = default_filters + (additional_filters or [])
    
    payload = {
        'request_data': {
            'filters': filters,
            'search_from': start,
            'search_to': end,
            'sort': {
                'field': 'creation_time',
                'keyword': 'desc'
            }
        }
    }
    return payload

def make_request(key_id, key, key_type, fqdn, endpoint, start, end):
    """
    Make a single API request with robust handling.
    
    :raises Exception: For network or parsing errors
    :return: Parsed JSON response
    """
    import urllib3
    
    payload = get_payload(start, end)
    headers = get_headers(key_id, key, key_type)
    
    try:
        # Create a PoolManager to handle HTTPS requests
        http = urllib3.PoolManager(
            cert_reqs='CERT_NONE',  # Disable certificate verification
            assert_hostname=False   # Disable hostname verification
        )
        
        # Prepare the request
        encoded_payload = json.dumps(payload).encode('utf-8')
        
        # Send POST request
        response = http.request(
            'POST', 
            f'https://{fqdn}{endpoint}',
            body=encoded_payload,
            headers={
                'Content-Type': 'application/json',
                **headers
            }
        )
        
        # Check response status
        if response.status != 200:
            raise Exception(f"API request failed with status {response.status}: {response.data}")
        
        # Parse and return response
        return json.loads(response.data.decode('utf-8'))
    
    except Exception as e:
        print(f"Error making request: {e}")
        raise

def retrieve_all_alerts(key_id, key, key_type, fqdn, endpoint, count_per_page=100, max_pages=None):
    """
    Retrieve all available alerts with robust pagination.
    
    :param key_id: API Key ID
    :param key: API Key
    :param key_type: 'advanced' or 'standard'
    :param fqdn: API endpoint domain
    :param endpoint: API endpoint path
    :param count_per_page: Number of alerts to retrieve per page
    :param max_pages: Maximum number of pages to retrieve (None for all)
    :return: List of all retrieved alerts
    """
    all_alerts = []
    start = 0
    page = 1
    
    while True:
        try:
            # Calculate end index
            end = start + count_per_page
            
            # Make API request
            response = make_request(key_id, key, key_type, fqdn, endpoint, start, end)
            
            # Extract alerts from response
            alerts = response.get('reply', {}).get('alerts', [])
            
            # Break if no more alerts
            if not alerts:
                break
            
            # Extend all_alerts list
            all_alerts.extend(alerts)
            
            # Print progress
            print(f"[Page {page}] Retrieved {len(alerts)} alerts. Total so far: {len(all_alerts)}")
            
            # Check for pagination limit
            if max_pages and page >= max_pages:
                print(f"Reached maximum specified pages: {max_pages}")
                break
            
            # Prepare for next page
            start += count_per_page
            page += 1
            
        except Exception as e:
            print(f"Error retrieving alerts: {e}")
            break
    
    return all_alerts

def upload_to_s3(alerts, bucket_name):
    """
    Upload alerts to S3 bucket.
    
    :param alerts: List of alerts to upload
    :param bucket_name: Name of the S3 bucket
    :return: S3 object key
    """
    s3_client = boto3.client('s3')
    
    try:
        # Generate unique filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        s3_key = f'cortex-alerts/{timestamp}_alerts.json'
        
        # Convert alerts to JSON string
        alerts_json = json.dumps(alerts, indent=2)
        
        # Upload to S3
        s3_client.put_object(
            Bucket=bucket_name, 
            Key=s3_key, 
            Body=alerts_json.encode('utf-8'),
            ContentType='application/json'
        )
        
        print(f"Successfully uploaded {len(alerts)} alerts to s3://{bucket_name}/{s3_key}")
        return s3_key
    
    except ClientError as e:
        print(f"S3 Upload Error: {e}")
        raise

def lambda_handler(event, context):
    """
    AWS Lambda handler function.
    
    :param event: Lambda event data
    :param context: Lambda context object
    :return: Dictionary with operation results
    """
    try:
        # Retrieve configuration from SSM Parameters
        key_id = int(get_ssm_parameter('/cortex/key_id'))
        key = get_ssm_parameter('/cortex/api_key')
        key_type = get_ssm_parameter('/cortex/key_type')
        fqdn = get_ssm_parameter('/cortex/fqdn')
        endpoint = get_ssm_parameter('/cortex/endpoint')
        
        # Default pagination parameters
        count_per_page = int(os.environ.get('COUNT_PER_PAGE', 100))
        max_pages = int(os.environ.get('MAX_PAGES', 10))
        bucket_name = os.environ.get('S3_BUCKET', 'db-pan-bucket')
        
        # Retrieve alerts
        alerts = retrieve_all_alerts(
            key_id, key, key_type, fqdn, endpoint, 
            count_per_page, max_pages
        )
        
        # Upload to S3
        s3_key = upload_to_s3(alerts, bucket_name)
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Alerts retrieved and uploaded successfully',
                'total_alerts': len(alerts),
                's3_key': s3_key
            })
        }
    
    except Exception as e:
        print(f"Lambda execution error: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e)
            })
        }
