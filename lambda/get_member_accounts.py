import boto3
import os
import logging
from botocore.config import Config

logger = logging.getLogger()
logger.setLevel(os.getenv('log_level', logging.INFO))

# Configure boto retries
BOTO_CONFIG = Config(retries=dict(max_attempts=5, mode='standard'))

sns_topic = os.environ['SNS_topic']
scope = os.environ.get('Scope')

org_client = boto3.client('organizations')
sns_client = boto3.client('sns')

def lambda_handler(event, context):

    logger.info('Triggered by Event Bridge scheduled event')

    if scope == 'Organization':
        logger.info('Getting list of accounts in organization')
        aws_accounts = org_client.list_accounts()
        list_aws_accounts = aws_accounts['Accounts']

        while 'NextToken' in aws_accounts:
            aws_accounts = org_client.list_accounts(NextToken=aws_accounts['NextToken'])
            list_aws_accounts.extend(aws_accounts['Accounts'])
            
        for account in list_aws_accounts:
            if account['Status'] == 'ACTIVE':
                send_sns_message = sns_client.publish(
                TopicArn=sns_topic,
                Message=account['Id']
                )

    if scope == 'OrganizationalUnit':
        ou_id = os.environ.get('OrganizationalUnitId')
        if not ou_id:
            logger.info('OU ID is not provided')
            raise ValueError('A very specific bad thing happened.')
            return
        
        logger.info('Getting list of accounts in Organizational Unit {}'.format(ou_id))
        aws_accounts = org_client.list_accounts_for_parent(ParentId = ou_id)
        list_aws_accounts = aws_accounts['Accounts']

        while 'NextToken' in aws_accounts:
            aws_accounts = org_client.list_accounts_for_parent(NextToken=aws_accounts['NextToken'])
            list_aws_accounts.extend(aws_accounts['Accounts'])

        for account in list_aws_accounts:
            if account['Status'] == 'ACTIVE':
                send_sns_message = sns_client.publish(
                TopicArn=sns_topic,
                Message=account['Id']
                )
    logger.info('Send all account numbers to SNS topic ')