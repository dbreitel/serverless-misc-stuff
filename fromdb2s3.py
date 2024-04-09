import json
import boto3
import uuid
import random
import string
import os
from datetime import datetime
#takes value from dynamodb and put it under random directory in s3 
dynamodb = boto3.resource('dynamodb')
s3 = boto3.client('s3')
def lambda_handler(event, context):
    table = dynamodb.Table('fromLambda')
    response = table.scan()
    data = response['Items']
  #change it to int from decimal, default response from dynamo 
    for d in data:
        d['name'] = int(d.get("name", 0))
        d['date'] = int(d.get("date"))
    #data = [1712670827,25]
    
    now = datetime.now().strftime("%Y%m%d-%H%M%S")
    file_name = f"fromLambda-{now}.json"


    # Generate random folder name
    folder = ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(10))
    
    # Create folder in bucket
#    s3.put_object(
#        Bucket="db-db2bucket",
#        Key=(folder + "/")
#    )
    json_data = json.dumps(data)
    s3.put_object(
        Bucket='db-db2bucket',
        Key=f"{folder}{file_name}",
        Body=json_data
    )

    return {
        'statusCode': 200,
        'body': f"Wrote {len(data)} items from DynamoDB table 'fromLambda' to S3 bucket 'db-db2bucket' at {folder}{file_name}"
    }
