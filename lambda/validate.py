import boto3
import json
import os 
import datetime
import logging
from botocore.exceptions import ClientError
from botocore.config import Config

logger = logging.getLogger()
logger.setLevel(logging.INFO)

#Task 1: get roleARN from previous state
#Task 2: make sure role isn't used and currently deactivated
#Task 3: delete role
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

def get_client(service, account_id, cross_account_role):
  temp_access = get_assume_role_credentials(account_id, cross_account_role)

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
def check_role_deactivate(client, role_name):
    role_deactivate = False
    try:
        check_deny_policy = client.get_role_policy(
            RoleName=role_name,
            PolicyName='DenyAllCheckUnusedIAMRoleSolution'
        )
        role_deactivate = True
        return role_deactivate 
    except ClientError as ex:
        if 'NoSuchEntityException' in ex.response['Error']['Code']:
            ex.response['Error']['Message'] = "Role doesn't exist"
        else:
            ex.response['Error']['Message'] = "InternalError"
            ex.response['Error']['Code'] = "InternalError"
    return role_deactivate
    
def remove_instance_profiles(client, role_name):
    list_instance_profiles = []
    instance_profiles = client.list_instance_profiles_for_role(RoleName=role_name)

    while True:
        list_instance_profiles += instance_profiles['InstanceProfiles']
        if 'Marker' in instance_profiles:
            instance_profiles = iam_client.list_instance_profiles_for_role(RoleName=role_name, Marker=instance_profiles['Marker'])
        else:
            break
    
    for item in list_instance_profiles:
        remove_profile = client.remove_role_from_instance_profile(
                InstanceProfileName=item['InstanceProfileName'],
                RoleName=role_name
                )
                
def detach_managed_policies(client, role_name):
    list_managed_policies = []
    managed_policies = client.list_attached_role_policies(
                RoleName=role_name )
   
    while True:
        list_managed_policies += managed_policies['AttachedPolicies']
        if 'Marker' in managed_policies:
            managed_policies = iam_client.list_attached_role_policies(RoleName=role_name, Marker=managed_policies['Marker'])
        else:
            break
    
    for item in list_managed_policies:
        remove_m_policies = client.detach_role_policy(
                RoleName=role_name,
                PolicyArn=item['PolicyArn']
                )

def delete_inline_policies(client, role_name):
    list_inline_policies = []
    inline_policies = client.list_role_policies(
        RoleName=role_name
    )
       
    while True:
        list_inline_policies += inline_policies['PolicyNames']
        if 'Marker' in inline_policies:
            inline_policies = iam_client.list_role_policies(RoleName=role_name, Marker=inline_policies['Marker'])
        else:
            break

    for item in list_inline_policies:
        remove_m_policies = client.delete_role_policy(
                RoleName=role_name,
                PolicyName = item
                )
               
def delete_role(client,role_name):

    try:
        delete_role = client.delete_role(
            RoleName = role_name)
        return "Role is deleted"
    except ClientError as ex:
        if 'NoSuchEntityException' in ex.response['Error']['Code']:
            ex.response['Error']['Message'] = "Role doesn't exist"
        else:
            ex.response['Error']['Message'] = "InternalError"
            ex.response['Error']['Code'] = "InternalError"
        return "Fail to delete IAM Role {}".format(role_name)
        
# Determine if any roles were used to make an AWS request
def validate_deletion(client, member_account, role_name, role_last_used, max_days_for_last_used):
    #add 30days wait time before deleting the role

    last_used_date = role_last_used.get('LastUsedDate', None)
    used_region = role_last_used.get('Region', None)

    role_is_deactivated = check_role_deactivate(client, role_name)

    if not last_used_date:
        return "Role {} in {} doesn't have 'RoleLastUsed' information".format(role_name,member_account)

    days_unused = (datetime.datetime.now() - last_used_date.replace(tzinfo=None)).days
    if days_unused > max_days_for_last_used:
        if role_is_deactivated:
            logger.info("Deleting role {} in account {} by CheckUnusedIAMRole Solutions".format(role_name, member_account))
            remove_instance_profiles(client,role_name) #remove instance profile from role
            detach_managed_policies(client, role_name) #detach managed policies from role
            delete_inline_policies(client, role_name)  #delete inline policies of the role
            return delete_role(client, role_name)

    return "Role is in use. Role {} in account {} was on {} in {}".format(role_name,member_account, last_used_date, used_region)


def lambda_handler(event, context):

    member_account = event['accountId']
    max_days_for_last_used = int(event['maxdays']) # + int(30) # add 30 days wait time for wait state before this validate state
    role_name = event['roleName']
    cross_account_role = os.environ.get('cross_account_role')

    iam_client = get_client('iam', member_account, cross_account_role)
    get_role = iam_client.get_role(RoleName=role_name)
    role = get_role['Role']
    role_last_used = role['RoleLastUsed']

    return validate_deletion(iam_client, member_account, role_name, role_last_used, max_days_for_last_used)
