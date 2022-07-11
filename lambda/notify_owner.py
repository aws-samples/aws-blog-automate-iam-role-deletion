
import boto3
import urllib.parse
import json
from botocore.exceptions import ClientError
from botocore.config import Config
import os
import logging

logger = logging.getLogger()
logger.setLevel(os.getenv('log_level', logging.INFO))

# Configure boto retries
BOTO_CONFIG = Config(retries=dict(max_attempts=5, mode='standard'))

st_client = boto3.client('stepfunctions', config = BOTO_CONFIG)
ses_client = boto3.client('ses', config = BOTO_CONFIG)

def lambda_handler(event, context):

    # This ITSecTeamEmail address must be verified with Amazon SES.
    sender = os.environ.get('ITSecTeamEmail')
    taskToken = event['taskToken']
    role_arn = event['finding']['Id']
    target_account = event['finding']['UserDefinedFields']['TargetAccountId']

    # If your account is still in the sandbox, this recipient/owner_email address must be verified with SES
    owner_email = event['finding']['UserDefinedFields']['OwnerEmail']
    max_days = event['finding']['UserDefinedFields']['MaxDays']
    privateAPIGWEndpoint = os.environ.get('privateAPIGWEndpoint')
    
    approve_apigw = privateAPIGWEndpoint + '/approve?taskToken=' + urllib.parse.quote(taskToken)
    deny_apigw = privateAPIGWEndpoint + '/deny?taskToken=' + urllib.parse.quote(taskToken)

    html_message = """
    <html>
    <p>Hello!</p>
    <p> This IAM Role {rolearn} is not used for more than {maxdays} days.</p>
    <p> Can you please delete the role by following this link: 
    <a href={approveapigw}>Approve link</a></p>
    <p> Or keep this role by following this link:                  
    <a href={denyapigw}>Deny link</a>  </p> 
        
    </html>
    """.format(rolearn=role_arn, maxdays=max_days, approveapigw=approve_apigw, denyapigw=deny_apigw)
    send_email = ses_client.send_email(
        Source=sender,
        Destination={
            'ToAddresses': [
                owner_email, 
            ],
            'CcAddresses': [
                
            ],
            'BccAddresses': [
                ]
        },
        Message={
            'Subject': {
                'Data': 'Please take action on this unused IAM Role',
                'Charset': 'UTF-8'
            },
            'Body': {
                'Html': {
                    'Data': html_message,
                    'Charset': 'UTF-8'
                }

            }
        },
        ReplyToAddresses=[
            sender,
        ]
    )
    
    return

  