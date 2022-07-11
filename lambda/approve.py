import boto3
import os
import json
import datetime
import logging
from datetime import timedelta
from botocore.exceptions import ClientError
from botocore.config import Config

logger = logging.getLogger()
logger.setLevel(logging.INFO)

#Task 1: Get role ARN
#Task 2: check if role is actually not used
#Task 3: mark role inactive
#Task 4: move to wait state

BOTO_CONFIG = Config(retries=dict(max_attempts=5, mode='standard'))
ROLE_TIMEOUT_SECONDS = 900


def get_assume_role_credentials(account_id,cross_account_role):

    sts_client = boto3.client('sts')
    try:
        assume_role_response = sts_client.assume_role(RoleArn="arn:aws:iam::{}:role/{}".format(account_id,cross_account_role),
                                                        RoleSessionName=cross_account_role,
                                                        DurationSeconds=ROLE_TIMEOUT_SECONDS)
        return assume_role_response['Credentials']
    except ClientError as ex:
        if 'AccessDenied' in ex.response['Error']['Code']:
            ex.response['Error']['Message'] = "Lambda function does not have permission to assume the IAM role."
        else:
            ex.response['Error']['Message'] = "InternalError"
            ex.response['Error']['Code'] = "InternalError"
        raise ex


def get_client(service, account_id,cross_account_role):
    
    temp_access = get_assume_role_credentials(account_id,cross_account_role)

    ACCESS_KEY = temp_access['AccessKeyId']
    SECRET_KEY = temp_access['SecretAccessKey']
    SESSION_TOKEN = temp_access['SessionToken']

    return boto3.client(
                service,
                aws_access_key_id=ACCESS_KEY,
                aws_secret_access_key=SECRET_KEY,
                aws_session_token=SESSION_TOKEN,
                config=BOTO_CONFIG
                )

def deactivate_role(client,role_name):

    deny_permission = False

    try:
        deactivate_role = client.put_role_policy(
            PolicyDocument='{ "Version": "2012-10-17", "Statement": [ { "Action": "*", "Effect": "Deny", "Resource": "*" } ] }',
            PolicyName='DenyAllCheckUnusedIAMRoleSolution',
            RoleName=role_name
            )
    
        add_tag = client.tag_role(
            RoleName=role_name,
            Tags=[{
                'Key': 'DeactivateReason',
                'Value': 'Role is in grace time period before deletion. Deactivated by CheckUnusedIAMRole Solution'
                },
            ]
        )
        deny_permission = True

    except ClientError as ex:
        if 'NoSuchEntityException' in ex.response['Error']['Code']:
            ex.response['Error']['Message'] = "Role doesn't exist"
        else:
            ex.response['Error']['Message'] = "InternalError"
            ex.response['Error']['Code'] = "InternalError"
        raise ex



    return deny_permission

# Determine if any roles were used to make an AWS request
def evaluate_role(client, member_account, role_name, role_last_used, max_days_for_last_used):
    role_inactive = False

    last_used_date = role_last_used.get('LastUsedDate', None)
    used_region = role_last_used.get('Region', None)

    if last_used_date is not None:
        days_unused = (datetime.datetime.now() - last_used_date.replace(tzinfo=None)).days
        if days_unused > max_days_for_last_used:
            role_inactive =  deactivate_role(client, role_name)
            logger.info("Deactivate role {} in account {} by CheckUnusedIAMRole Solution".format(role_name,member_account))

        logger.info("Role is in use. Role {} in account {} was used on {}  in {}".format(role_name,member_account, last_used_date, used_region))

    return role_inactive


def lambda_handler(event, context):

    member_account = event["finding"]["UserDefinedFields"]["TargetAccountId"]
    max_days_for_last_used = int(event["finding"]["UserDefinedFields"]["MaxDays"])
    role_name = event["finding"]["UserDefinedFields"]["RoleName"]

    cross_account_role = os.environ.get('cross_account_role')
    iam_client = get_client('iam', member_account,cross_account_role)
    get_role = iam_client.get_role(RoleName=role_name)
    role = get_role['Role']
    role_last_used = role['RoleLastUsed']
    role_status = evaluate_role(iam_client, member_account, role_name, role_last_used, max_days_for_last_used)

    # set timestamp to wait for 30 days from now 
    # update timedelta(days=x) while x is the number of days you want to wait between
    # role invalidation to deletion
    wait_time_stamp = (datetime.datetime.now() + timedelta(days=30)).strftime('%Y-%m-%dT%H:%M:%SZ')

    role_properties = {"roleName": role_name,
                        "accountId" : member_account,
                        "maxdays": max_days_for_last_used,
                        "waitUntil" : wait_time_stamp,
                        "roleStatus": role_status
                        }
    return role_properties
