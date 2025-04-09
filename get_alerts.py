import sys
import json
import ssl
import certifi
import boto3
from botocore.exceptions import ClientError
from datetime import datetime, timezone
from secrets import choice
from string import ascii_letters, digits
from hashlib import sha256
from http.client import HTTPSConnection
import os

def create_ssl_context():
    """
    Create a secure SSL context with options for certificate verification.
    
    :return: SSL context
    """
    try:
        # Create a default SSL context using certifi's root certificates
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        
        # Optional: Add flexibility for self-signed or internal certificates
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        return ssl_context
    except Exception as e:
        print(f"Error creating SSL context: {e}")
        return None

def upload_to_s3(file_path, bucket_name):
    """
    Upload a file to S3 bucket.
    
    :param file_path: Path to the file to upload
    :param bucket_name: Name of the S3 bucket
    :return: True if upload successful, False otherwise
    """
    try:
        # Create S3 client
        s3_client = boto3.client('s3')
        
        # Generate S3 key (path) using filename
        s3_key = f'cortex-alerts/{os.path.basename(file_path)}'
        
        # Upload the file
        s3_client.upload_file(file_path, bucket_name, s3_key)
        
        print(f"Successfully uploaded {file_path} to s3://{bucket_name}/{s3_key}")
        return True
    
    except ClientError as e:
        print(f"S3 Upload Error: {e}")
        return False
    except Exception as e:
        print(f"Unexpected error uploading to S3: {e}")
        return False

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
    Make a single API request with robust SSL handling.
    
    :raises Exception: For network or parsing errors
    :return: Parsed JSON response
    """
    payload = get_payload(start, end)
    headers = get_headers(key_id, key, key_type)
    
    try:
        # Create SSL context
        ssl_context = create_ssl_context()
        
        # Establish HTTPS connection with custom SSL context
        conn = HTTPSConnection(
            fqdn, 
            context=ssl_context,
            timeout=30
        )
        
        conn.request('POST', endpoint, json.dumps(payload), headers)
        res = conn.getresponse()
        
        # Check for successful response
        if res.status != 200:
            raise Exception(f"API request failed with status {res.status}: {res.reason}")
        
        data = res.read()
        return json.loads(data.decode('utf-8'))
    except ssl.SSLError as ssl_err:
        print(f"SSL Certificate Verification Error: {ssl_err}")
        print("Possible solutions:")
        print("1. Verify the server's SSL certificate")
        print("2. Contact your network administrator")
        print("3. If this is an internal/test environment, consider manual certificate handling")
        raise
    except Exception as e:
        print(f"Error making request: {e}")
        raise
    finally:
        conn.close()

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

def save_alerts_to_file(alerts, base_filename=None):
    """
    Save retrieved alerts to a JSON file and upload to S3.
    
    :param alerts: List of alerts to save
    :param base_filename: Optional base filename (defaults to timestamp)
    :return: Filename of the saved file
    """
    if not alerts:
        print("No alerts to save.")
        return None
    
    # Use timestamp if no base filename provided
    if base_filename is None:
        base_filename = f'cortex-alerts-{datetime.now().isoformat()}'
    
    filename = f'{base_filename}.json'
    
    try:
        with open(filename, 'w') as f:
            json.dump(alerts, f, indent=2)
        print(f"Saved {len(alerts)} alerts to {filename}")
        
        # Upload to S3
        upload_to_s3(filename, 'db-pan-bucket')
        
        return filename
    except Exception as e:
        print(f"Error saving alerts: {e}")
        return None

def main():
    """
    Main execution function with improved error handling and flexibility.
    """
    # Validate command-line arguments
    if len(sys.argv) < 9:
        print("""
USAGE: python3 lobotomy.py KEYID KEY KEYTYPE FQDN ENDPOINT START COUNT MAX_PAGES
EXAMPLE: python3 lobotomy.py 007 my-key advanced api.xdr.us.paloaltonetworks.com /public_api/v1/alerts/get_alerts_multi_events 0 100 10
        """)
        sys.exit(1)
    
    try:
        # Parse arguments
        key_id = int(sys.argv[1])
        key = sys.argv[2]
        key_type = sys.argv[3]
        fqdn = sys.argv[4]
        endpoint = sys.argv[5]
        start = int(sys.argv[6])
        count_per_page = int(sys.argv[7])
        max_pages = int(sys.argv[8])
        
        # Retrieve alerts
        alerts = retrieve_all_alerts(
            key_id, key, key_type, fqdn, endpoint, 
            count_per_page, max_pages
        )
        
        # Save alerts and upload to S3
        save_alerts_to_file(alerts)
        
    except Exception as e:
        print(f"Execution error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()