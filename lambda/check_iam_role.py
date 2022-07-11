import boto3
import json
import fnmatch
import os
import re
import datetime
import calendar
import logging
from botocore.exceptions import ClientError
from botocore.config import Config

logger = logging.getLogger()
logger.setLevel(os.getenv('log_level', logging.INFO))

# Configure boto retries
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
            

# Validates role pathname allowlist as passed via AWS CloudFormation parameters and returns a list of comma separated patterns.
def validate_allow_list(unvalidated_role_pattern_allowlist):
    # Names of users, groups, roles must be alphanumeric, including the following common
    # characters: plus (+), equal (=), comma (,), period (.), at (@), underscore (_), and hyphen (-).
    valid_character_regex = '^[-a-zA-Z0-9+=,.@_/|*]+'

    if not unvalidated_role_pattern_allowlist:
        return None

    regex = re.compile(valid_character_regex)
    if not regex.search(unvalidated_role_pattern_allowlist):
        raise ValueError("[Error] Provided allowlist has invalid characters")

    return unvalidated_role_pattern_allowlist.split('|')


# This uses Unix filename pattern matching (as opposed to regular expressions), as documented here:
# https://docs.python.org/3.7/library/fnmatch.html.  Please note that if using a wildcard, e.g. "*", you should use
# it sparingly/appropriately.
# If the rolename matches the pattern, then it is allowed
def is_allowed_role(role_pathname, pattern_list):

    if not pattern_list:
        return False
    # If role_pathname matches pattern, then return True, else False
    # eg. /service-role/aws-codestar-service-role matches pattern /service-role/*
    # https://docs.python.org/3.7/library/fnmatch.html
    for pattern in pattern_list:
        if fnmatch.fnmatch(role_pathname, pattern):
            return True

    return False

# Form an evaluation as a dictionary. Suited to report on scheduled rules.  More info here:
#   https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/config.html#ConfigService.Client.put_evaluations
def build_finding(sec_account_id, member_account, role_name, role_arn, role_owner, notification_creation_time, reason,max_days_for_last_used):
    finding = {}
    finding['SchemaVersion'] = "2018-10-08"
    finding['Title'] = "Unused IAM Role {} in account {}".format(role_name, member_account)
    finding['Description'] = reason
    finding['ProductArn'] = "arn:aws:securityhub:us-west-2:{}:product/{}/default".format(sec_account_id,sec_account_id)
    finding['AwsAccountId'] = sec_account_id
    finding['Id'] = role_arn
    finding['GeneratorId'] = "CUSTOM:checkUnusedRoleLambdaFunction"
    finding['CreatedAt'] = notification_creation_time
    finding['UserDefinedFields'] = {'OwnerEmail': role_owner, 'RoleName': role_name, 'TargetAccountId':member_account, 'MaxDays': str(max_days_for_last_used)}
    finding['Severity'] = {"Label": "MEDIUM"}
    finding['Resources'] = [{"Type": "AwsIamRoleDetails", "Id": role_arn}]
    finding['Types'] = ['Software and Configuration Checks/TPPs/Initial Access']
    finding['UpdatedAt'] = notification_creation_time
    finding['RecordState'] = 'ACTIVE'
    
    return finding

def check_finding_exists(sechub_client, sec_account_id, role_arn):
    product_arn = "arn:aws:securityhub:us-west-2:{}:product/{}/default".format(sec_account_id,sec_account_id)
    filters = {
        "ProductArn": [{
            "Value": product_arn,
            "Comparison": "EQUALS"
        }],
        "Id": [{
            "Value": role_arn,
            "Comparison": "EQUALS"
        }],
        "RecordState": [{
            "Value": "NEW",
            "Comparison": "EQUALS"
        }]
    }
    get_findings_response = sechub_client.get_findings(
        Filters=filters
    )
    #verify that there is a finding returned back.
    findings = get_findings_response["Findings"]
    if findings:
        return True
    else:
        return False

# Determine if any roles were used to make an AWS request
def determine_last_used(sechub_client, sec_account_id, role_name, role_last_used, max_days_for_last_used, notification_creation_time, member_account, role_arn, role_owner):
    last_used_date = role_last_used.get('LastUsedDate', None)
    used_region = role_last_used.get('Region', None)

    #check if there are findings related to this IAM role
    existing_findings = check_finding_exists(sechub_client, sec_account_id, role_arn)

    if last_used_date is None:
        return None

    days_unused = (datetime.datetime.now() - last_used_date.replace(tzinfo=None)).days
    if days_unused > max_days_for_last_used:
        if not existing_findings:
            reason = "NON_COMPLIANT: Role was used {} days ago in {}".format(days_unused, used_region)
            return build_finding(sec_account_id,member_account, role_name, role_arn, role_owner, notification_creation_time, reason, max_days_for_last_used)
        else:
            return None

# Returns a list of docts, each of which has authorization details of each role.  More info here:
#   https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/iam.html#IAM.Client.get_account_authorization_details
def get_role_authorization_details(iam_client):

    roles_authorization_details = []
    roles_list = iam_client.get_account_authorization_details(Filter=['Role'])

    while True:
        roles_authorization_details += roles_list['RoleDetailList']
        if 'Marker' in roles_list:
            roles_list = iam_client.get_account_authorization_details(Filter=['Role'], Marker=roles_list['Marker'])
        else:
            break

    return roles_authorization_details


# Check the compliance of each role by determining if role last used is > than max_days_for_last_used
def lambda_handler(event, context):
    sec_account_id = context.invoked_function_arn.split(":")[4]
    member_account = ""
    notification_creation_time = ""
    role_owner = ""
    #retrieve State Machine Arn
    state_machine_arn = os.environ.get('state_machine_arn','')

    # if the scope is aws account, retrieve the account number from env variables
    if os.environ.get('member_account'):
        member_account = os.environ.get('member_account')
        notification_creation_time = str(event['time'])
    else:
    #if the scope is organization or OU, retrieve the account number from SNS message
        member_account = event['Records'][0]['Sns']['Message']
        notification_creation_time = str(event['Records'][0]['Sns']['Timestamp'])

    #retrieve the cross account role name from env variable cross_account_role
    cross_account_role = os.environ.get('cross_account_role')

    # Initialize  AWS clients 
    iam_client = get_client('iam', member_account,cross_account_role)
    sechub_client = boto3.client('securityhub')
    stepfunc_client = boto3.client('stepfunctions')

    # List of findings generated from resource evaluations to return back to AWS Security Hub
    non_compliance_findings = []

    # List of dicts of each role's authorization details as returned by boto3
    all_roles = get_role_authorization_details(iam_client)
    
    # Maximum allowed days that a role can be unused, or has been last used for an AWS request
    max_days_for_last_used = int(os.environ.get('max_days_for_last_used', '60'))

    allowed_role_pattern_list = validate_allow_list(os.environ.get('role_allowed_list', ''))


    # Iterate over all our roles.  If the creation date of a role is <= max_days_for_last_used, it is compliant
    for role in all_roles:
        role_name = role['RoleName']
        role_path = role['Path']
        role_arn = role['Arn']
        role_creation_date = role['CreateDate']
        role_last_used = role['RoleLastUsed']
        
        #retrieve Role Owner address from Tags. 
        #Otherwise retrieve default email provided by IT Sec Team

        for tag in role['Tags']:
            if tag['Key'] == 'Owner':
                role_owner = tag['Value']
            role_owner = os.environ.get('default_email')

        role_age_in_days = (datetime.datetime.now() - role_creation_date.replace(tzinfo=None)).days

        if is_allowed_role(role_path + role_name, allowed_role_pattern_list):
            continue

        if role_age_in_days <= max_days_for_last_used:
            continue

        new_finding = determine_last_used(sechub_client,sec_account_id, role_name, role_last_used, max_days_for_last_used, notification_creation_time, member_account, role_arn, role_owner)
        
        if new_finding is not None:
            non_compliance_findings.append(new_finding)
            #need to reduce role name length to fit with state machine start_execution syntax 
            #require 'name' to be less than 80 char long
            if len(role_name) > 56:
                role_name = role_name[0:55]
            stepfunc_client.start_execution(
                stateMachineArn=state_machine_arn,
                name=member_account+"-"+role_name+"-"+str(calendar.timegm(datetime.datetime.now().utctimetuple())),
                input=json.dumps(new_finding)
                )

    # Iterate over our findings 100 at a time, as batch_import_findings only accepts a max of 100 evals.
    non_compliance_findings_copy = non_compliance_findings[:]
    
    while non_compliance_findings_copy:
        sechub_client.batch_import_findings(Findings=non_compliance_findings_copy[:100])
        del non_compliance_findings_copy[:100]

