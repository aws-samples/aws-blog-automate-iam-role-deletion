# How to centralize findings and automate deletion for unused IAM role

Proactively detecting and responding to unused IAM roles will help you prevent unauthorized entities to leverage it to get access to your AWS resources. You can build automation to enforce this process and periodically check IAM resources then take actions to delete unused IAM roles in an AWS Account. This blog post gives an example solution of how you can leverage Tags and AWS Serverless technologies to create such an automation. Follow blog post “How to centralize findings and automate deletion for unused IAM role” for more details.


## **Solution architecture**

[Image: checkUnusedIAMRoleSolution(2).png]The architecture diagram above demonstrate the automation workflow. There are two option to run this solution: in a single AWS Account belongs to an organization/OU, or in every member accounts belong to an organization or an organization unit.

## Walkthrough: Deploy the solution

### Prerequisites

* You will need to have an AWS Organization organization or a Security account .
* The solution should be deployed only in a central Security account, in which has appropriate admin permission to audit other accounts, and manage security automation.
* Since this solution will create CloudFormation StackSet in member accounts of organization/OU that you specify, the Security account will need to have a [Cloudformation delegated admin permission](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/stacksets-orgs-delegated-admin.html) to create AWS resources in this solution. If you run this solution for a single account, you need to [establish trust relationship](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/stacksets-prereqs-self-managed.html)between the Security account and target account by creating  AWSCloudFormationStackSetAdministrationRole IAM Role in Security account and  AWSCloudFormationStackSetExecutionRole in target account.
* This solution uses AWS Security Hub as a central dashboard in Security account that aggregates findings. Security Hub needs to be enable in Security Account. AWS Security Hub provides [predefined response and remediation actions](https://aws.amazon.com/solutions/implementations/aws-security-hub-automated-response-and-remediation/) based on industry compliance standards and best practices for security threats. It currently doesn’t have automation to check for unused IAM Roles. However, this solution can show you how to create custom findings and import to Security Hub.  The solution needs to be deploy in the home region that you use Security Hub dashboard.
* There should be an existing tagging enforcement already applied to IAM Roles. This solution use tag to identify owner email address. 
* This solution use Amazon SES to send email to IAM Role’s Owner. The sender address will need to be [verified with Amazon SES](https://docs.aws.amazon.com/ses/latest/DeveloperGuide/verify-email-addresses.html). If your account is still in the Amazon SES sandbox, you also need to verify any email addresses that you send emails to.

### Deploy the solution for a target AWS Account using AWS Console

From the home region of your Security Hub in Security account, , deploy this CloudFormation template (link to template solution_scope_account.yml on github)
[Image: image.png]

1. On **Specify stack details**,  provide a unique **Stack name**
2. For **AccountId**, provide the AWS Account Id of target account 
3. For **Frequency**, specify how often the automation will be triggered (number of days). For example, if you specify 2 days, the automation will be triggered 2 days after this solution is provisioned. To test this solution without waiting for this schedule, scroll down to **“Test this solution”**
4. For **ITSecurityEmail,** provide default email from IT Security team. If the role doesn’t have Owner tag to find owner, the email notification will be sent to IT security team.
5. For **MaxDaysForLastUsed**, provide number of days you would like to use as benchmark for checking if IAM roles are used within the period of time
6. For **RolePatternAllowedList**, provide a specific pattern of role name that you would like to skip for this automation. If you need to specify multiple patterns, you can use the `|` (pipe) character as a delimiter between each pattern

[Image: Screen Shot 2021-12-23 at 10.07.41 AM.png]


1. Click Next
2. Click Next
3. Under **Review**, make sure all Parameteres in **Step 2: Specify stack details** are correct. Scroll down to **Capabilities**. Check 2 boxes for “**I acknowledge that AWS CloudFormation might create IAM resources with custom names”** and **“I acknowledge that AWS CloudFormation might require the following capability:  CAPABILITY_AUTO_EXPAND”**
4. Click **Create Stack**

### Deploy the solution for an Organization or Organizational Unit

From the home region of your Security Hub in Security account, , deploy this CloudFormation template (link to template solution_scope_organization.yml on github)
[Image: image.png]

1. On **Specify stack details**,  provide a unique **Stack name**
2. For **AccountId**, provide the AWS Account Id of target account 
3. For **Frequency**, specify how often the automation will be triggered (number of days). For example, if you specify 2 days, the automation will be triggered 2 days after this solution is provisioned. To test this solution without waiting for this schedule, scroll down to **“Test this solution”**
4. For **ITSecurityEmail,** provide default email from IT Security team. If the role doesn’t have Owner tag to find owner, the email notification will be sent to IT security team.
5. For **MaxDaysForLastUsed**, provide number of days you would like to use as benchmark for checking if IAM roles are used within the period of time
6. Provide appropriate parameters for Organization/OU:
    1. To run this solution for entire Organization: 
        1. Provide organization root id for **OrgRootId**. The solution need this root id to create [CFN Stackset](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-properties-cloudformation-stackset-deploymenttargets.html) for all accounts in organization
        2. Leave **OrganizationalUnitId** blank
        3. Provide organization ID for **OrganizationId**. This parameter is for scoping permission for cross account role created in this solution.
        4. Choose **Scope** as Organization
    2. To run this solution for an Organization Unit:
        1. Leave **OrgRootId** blank
        2. Provide Organization Unit Id for **OrganizationUnitId**. The solution need this OU id to create [CFN Stackset](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-properties-cloudformation-stackset-deploymenttargets.html) for all accounts in organization.
        3. Provide organization ID for **OrganizationId**. This parameter is for scoping permission for cross account role created in this solution.
        4. Choose **Scope** as OrganizationalUnit
7. For **RolePatternAllowedList**, provide a specific pattern of role name that you would like to skip for this automation. If you need to specify multiple patterns, you can use the `|` (pipe) character as a delimiter between each pattern
8. Choose appropriate **Scope** : Organization for running this solution against entire Organization, or OrganizationalUnit for running this solution against an OU. Child OU is not supported in this solution.
9. Click Next
10. Click Next
11. Under **Review**, scroll down to **Capabilities**. Check 2 boxes for “**I acknowledge that AWS CloudFormation might create IAM resources with custom names”** and **“I acknowledge that AWS CloudFormation might require the following capability: CAPABILITY_AUTO_EXPAND”**
12. Click **Create Stack**

[Image: Screen Shot 2021-12-23 at 10.22.01 AM.png]

### Deploy the solution using AWS CLI

Alternatively, you can run these AWS CLI command to deploy the solution. Start with cloning the git repo. 

```
git clone [git repo to be created] .
cd /solution
```

Run [Cloudformation package](https://docs.aws.amazon.com/cli/latest/reference/cloudformation/package.html)to upload templates and Lambda code to your S3 bucket. The S3 bucket needs to be in the same region that you will deploy this solution
adfaf


```
#Deploy solution for a single target AWS Account
aws cloudformation package \
--template-file solution_scope_account.yml \
--s3-bucket YOUR_BUCKET_NAME \
--s3-prefix PATH_TO_UPLOAD_CODE \
--output-template-file solution_scope_account.template
```

```
#Deploy solution for an Organization/OU
aws cloudformation package \
--template-file solution_scope_organization.yml \
--s3-bucket YOUR_BUCKET_NAME \
--s3-prefix PATH_TO_UPLOAD_CODE \
--output-template-file solution_scope_organization.template
```


Validate if the template generated by Cloudformation package is valid

```
#Deploy solution for a single target AWS Account
aws cloudformation validate-template —template-body file://solution_scope_account.template
```

```
#Deploy solution for an Organization/OU
aws cloudformation validate-template —template-body file://solution_scope_organization.template
```

Deploy the solution in the same region with Security Hub home region. The stack takes 30 minutes to complete deployment

```
#Deploy solution for a single target AWS Account
aws cloudformation deploy \
--template-file solution_scope_account.template \
--stack-name UNIQUE_STACK_NAME \
--region REGION \
--capabilities CAPABILITY_NAMED_IAM CAPABILITY_AUTO_EXPAND \
--parameter-overrides AccountId='TARGET ACCOUNT ID' \
Frequency=[days] MaxDaysForLastUsed=[days] \
ITSecurityEmail='YOUR IT TEAM EMAIL' \
RolePatternAllowedlist='ALLOWED PATTERN'
```

```
#Deploy solution for an Organization
aws cloudformation deploy \
--template-file solution_scope_organization.template \
--stack-name UNIQUE_STACK_NAME \
--region REGION \
--capabilities CAPABILITY_NAMED_IAM CAPABILITY_AUTO_EXPAND \
--parameter-overrides Scope=Organization \
OrganizationId='o-12345abcde' \
OrgRootId='r-1234'  \
Frequency=[days] MaxDaysForLastUsed=[days] \
ITSecurityEmail='security-team@example.com' \
RolePatternAllowedlist='ALLOWED PATTERN'
```

```
#Deploy solution for an OU
aws cloudformation deploy \
--template-file solution_scope_organization.template \
--stack-name UNIQUE_STACK_NAME \
--region REGION \
--capabilities CAPABILITY_NAMED_IAM CAPABILITY_AUTO_EXPAND \
--parameter-overrides Scope=OrganizationalUnit \
OrganizationId='o-12345abcde' \
OrganizationalUnitId='ou-1234-1234abcd'  \
Frequency=[days] MaxDaysForLastUsed=[days] \
ITSecurityEmail='security-team@example.com' \
RolePatternAllowedlist='ALLOWED PATTERN'
```



## Test the solution

Because the solution is triggered by an Event Bridge schedule rule, it does not perform the checks immediately. To test the solution right away after the Cloudformation stacks are successfully created, you can follow these steps below.


###  Manually trigger the automation

After CFN stacks are created, go to AWS Lambda to manually trigger a function 

1. If the scope is Account, click on function [Cloudformation stackname]-LambdaCheckIAMRole. Click **Test**, click **New event**, name the event, and copy the json code below. Please make sure to replace the time by current time in UTC Date Time format  “YYYY-MM-DDTHH:MM:SSZ”. Once you’re done, click **Test** button. 

```
{
  "time": "2021-12-22T04:36:52Z"
}
```

[Image: Screen Shot 2021-12-23 at 11.32.50 AM.png]
1. If the Scope is Organization/OU, click on function [Cloudformation stackname]-LambdaGetAccounts.  Click **Test**, click **New event**, name the event. Leave everything as default. Once you’re done, click **Test** button.

### Respond to unused IAM Roles

Once you have trigger the Lambda function, the automation will run necessary checks. For each unused IAM role, it will create a Step Functions state machine execution. Go to AWS Step Functions, click on  state machine [Cloudformation stackname]OnwerApprovalStateMachine. Under **Executions** tab, you will see the list of executions in running state following this naming convention: [target-account-id]-[unused IAM role name]-[time the execution created in Unix format]
[Image: Screen Shot 2021-12-23 at 12.01.21 PM.png][Image: Screen Shot 2021-12-23 at 12.01.21 PM.png]Each execution will send out an email notification to the IAM role owner (if available via tag) or to the email you provided in CFN stack parameter ‘ITSecurityEmail’. The email will look like this:
[Image: Screen Shot 2021-12-23 at 11.52.33 AM.png]

The **Approve link** and **Deny link** is the link to a private API Endpoint with a parameter taskToken. If you access these link publicly, it don’t work. To test the approval action, you can utilize API Gateway Test feature by following these step:

1. Retrieve taskToken from state machine:
    1. Click on the execution that has the IAM role name that you want to delete
    2. Scroll down to **Execution event history**
    3. Find the item **taskToken** and copy its value to a notepad

[Image: Screen Shot 2021-12-23 at 12.25.31 PM.png]

1. Test approval workflow using API Gateway Test
    1. Go to API Gateway 
    2. Click on API that has the name similar to [Cloudformation stackname]-PrivateAPIGW-[unique string]-ApprovalEndpoint
    3. To test deny action, click **GET** method under **/deny** resource
    4. To test approve action, click **GET** method under **/approve** resource
    5. Click on Test
    6. Under **QuerryString**, type in **taskToken=**, and paste the taskToken you copy from state machine execution.
    7. Click **Test**

[Image: Screen Shot 2021-12-23 at 12.37.04 PM.png]
1. Go to the state machine execution. 
    1. If you deny the role deletion, the execution will immediately stop as ‘Fail’
    2. If you choose to approve role deletion, the execution will wait at “Wait” task until specified wait time, triggers “Validate” task to do a final validation on the role before deleting it. 



## Next step

We recommend testing this solution extensively to make sure it performs all the necessary checks following guidance from your IT/Security team. Here are a few suggestions that you can take to improve this solution:

* Encrypt SNS message to protect AWS account ID
* Create connectivity between your internal network and Private API Gateway
* Adding a mechanism to control access to API Gateway
* Utilize Step Function state machine for other automation that needs human approval

