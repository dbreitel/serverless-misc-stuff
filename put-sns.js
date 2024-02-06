import json
import boto3
import random
import time
client = boto3.client('sns')
stam = random.randint(0,32)
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('fromLambda')
def lambda_handler(event, context):
   response = client.publish(TopicArn='<YOUR_TOPIC_SNS_ARN',Message="Test message from lambda"+ str(stam))
   ct=time.time()
   item = {
            'date': int(ct),
            'name': str(stam)
           }
   response = table.put_item(Item=item)
   print("Message published" + str(stam))
   return(response)
