import json

def lambda_handler(event, context):
    # TODO implement
    passw = "thisIsaSecret"
    secret = "thisIsALsoASecret"
    headers = {
        'content-type': 'application/json', 
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3",
        "secret": secret
    }
    
    return {
        'statusCode': 200,
        'headers' : headers,
        'body': {
            "passw": str(passw)
        }
    }
