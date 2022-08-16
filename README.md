Sample code and CloudFormation template for blog post “How to centralize findings and automate deletion for unused IAM role”. This solution gives an example of how you can leverage Tags and AWS Serverless technology to create automation to detect and remove unused IAM roles in AWS account.

## **Solution architecture**

![Architecture Diagram](/images/checkUnusedIAMRoleSolution.png)

The architecture diagram above demonstrate the automation workflow. There are two option to run this solution: in a single AWS Account belongs to an organization/OU, or in every member accounts belong to an organization or an organization unit.

## Option 1: Deploy this solution for a standalone account
Choose this option if you would like to check for unused IAM roles in a single AWS account. This AWS account might or might not belong to an organization or OU. In this blog post, I refer to this account as the standalone account.
### Prerequisites
1.	You need an AWS account specifically for security automation. For this blog post, I refer to this account as the standalone Security account. 
2.	You should deploy the solution to the standalone Security account, which has appropriate admin permission to audit other accounts and manage security automation.
3.	Because this solution uses AWS CloudFormation StackSets, you need to grant self-managed permissions to create stack sets in standalone accounts. Specifically, you need to establish a trust relationship between the standalone Security account and the standalone account by creating the AWSCloudFormationStackSetAdministrationRole IAM role in the standalone Security account, and the AWSCloudFormationStackSetExecutionRole IAM role in the standalone account.
4.	You need to have AWS Security Hub enabled in your standalone Security account, and you need to deploy the solution in the same AWS Region as your Security Hub dashboard.
5.	You need a tagging enforcement in place for IAM roles. This solution uses an IAM tag key Owner to identify the email address of the owner. The value of this tag key should be the email address associated with the owner of the IAM role. If the Owner tag isn’t available, the notification email is sent to the email address that you provided in the parameter ITSecurityEmail when you provisioned the CloudFormation stack.
6.	This solution uses Amazon Simple Email Service (Amazon SES) to send emails to the owner of the IAM roles. The destination address needs to be verified with Amazon SES.  With Amazon SES, you can verify identity at the individual email address or at the domain level.

An EventBridge rule triggers the AWS Lambda function LambdaCheckIAMRole in the standalone Security account. The LambdaCheckIAMRole function assumes a role in the standalone account. This role is named after the Cloudformation stack name that you specify when you provision the solution. Then LambdaCheckIAMRole calls the IAM API action GetAccountAuthorizationDetails to get the list of IAM roles in the standalone account, and parses the data type RoleLastUsed to retrieve the date, time, and the Region in which the roles were last used. If the last time value is not available, the IAM role is skipped. Based on the CloudFormation parameter MaxDaysForLastUsed that you provide, LambdaCheckIAMRole determines if the last time used is greater than the MaxDaysForLastUsed value. LambdaCheckIAMRole also extracts tags associated with the IAM roles, and retrieves the email address of the IAM role owner from the value of the tag key Owner. If there is no Owner tag, then LambdaCheckIAMRole sends an email to a default email address provided by you from the CloudFormation parameter ITSecurityEmail.

## Option 2: Deploy this solution for all member accounts that belong to an organization or an OU
Choose this option if you want to check for unused IAM roles in every member account that belongs to an AWS Organizations organization or OU.
### Prerequisites

1.	You need to have an AWS Organizations organization with a dedicated Security account that belongs to a Security OU. For this blog post, I refer to this account as the Security account.
2.	You should deploy the solution to the Security account that has appropriate admin permission to audit other accounts and to manage security automation.
3.	Because this solution uses CloudFormation StackSets to create stack sets in member accounts of the organization or OU that you specify, the Security account in the Security OU needs to be granted CloudFormation delegated admin permission to create AWS resources in this solution. 
4.	You need Security Hub enabled in your Security account, and you need to deploy the solution in the same Region as your Security Hub dashboard.
5.	You need tagging enforcement in place for IAM roles. This solution uses the IAM tag key Owner to identify the owner email address. The value of this tag key should be the email address associated with the owner of the IAM role. If the Owner tag isn’t available, the notification email will be sent to the email address that you provided in the parameter ITSecurityEmail when you provisioned the CloudFormation stack.
6.	This solution uses Amazon SES to send emails to the owner of the IAM roles. The destination address needs to be verified with Amazon SES. With Amazon SES, you can verify identity at the individual email address or at the domain level.	


An EventBridge rule triggers the Lambda function LambdaGetAccounts in the Security account to collect the account IDs of member accounts that belong to the organization or OU. LambdaGetAccounts sends those account IDs to an SNS topic. Each account ID invokes the Lambda function LambdaCheckIAMRole once.

Similar to the process for Option 1, LambdaCheckIAMRole in the Security account assumes a role in the member account(s) of the organization or OU, and checks the last time that IAM roles in the account were used. 

In both options, if an IAM role is not currently used, the function LambdaCheckIAMRole generates a Security Hub finding, and performs BatchImportFindings for all findings to Security Hub in the Security account. At the same time, the Lambda function starts an AWS Step Functions state machine execution. Each execution is for an unused IAM role following this naming convention: [target-account-id]-[unused IAM role name]-[time the execution created in Unix format]

You should avoid running this solution against special IAM roles, such as a break-glass role or a disaster recovery role. In the CloudFormation parameter RolePatternAllowedlist, you can provide a list of role name patterns to skip the check.

## **Use a Step Functions state machine to process approval**
 
![Owner approval state machine workflow](/images/statemachine.png)

After the solution identifies an unused IAM role, it creates a Step Functions state machine execution. Figure 2 demonstrates the workflow of the execution. After the execution starts, the first Lambda task NotifyOwner (powered by the Lambda function NotifyOwnerFunction) sends an email to notify the IAM role owner. This is a callback task that pauses the execution until a taskToken is returned. The maximum pause for a callback task is 1 year. The execution waits until the owner responds with a decision to delete or keep the role, which is captured by a private API endpoint in Amazon API Gateway. You can configure a timeout to avoid waiting for callback task execution.

With a private API endpoint, you can build a REST API that is only accessible within your Amazon Virtual Private Cloud (Amazon VPC), or within your internal network connected to your VPC. Using a private API endpoint will prevent anyone from outside of your internal network from selecting this link and deleting the role. You can implement authentication and authorization with API Gateway to make sure that only the appropriate owner can delete a role.

If the owner denies role deletion, then the role remains intact until the next automation cycle runs, and the state machine execution stops immediately with a Fail status. If the owner approves role deletion, the next Lambda task Approve (powered by the function ApproveFunction) checks again if the role is not currently used. If the role isn’t in use, the Lambda task Approve attaches an IAM policy DenyAllCheckUnusedIAMRoleSolution to deny the role to perform any actions, and waits for 30 days. During this wait time, you can restore the IAM role by removing the IAM policy DenyAllCheckUnusedIAMRoleSolution from the role. The Step Functions state machine execution for this role is still in progress until the wait time expires.

After the wait time expires, the state machine execution invokes the Validate task. The Lambda function ValidateFunction checks again if the role is not in use after the amount of time calculated by adding MaxDaysForLastUsed and the preceding wait time. It also checks if the IAM policy DenyAllCheckUnusedIAMRoleSolution is attached to the role. If both of these conditions are true, the Lambda function follows a process to detach the IAM policies and delete the role permanently. The role can’t be recovered after deletion.

## To deploy the solution using AWS CLI

Alternatively, you can run these AWS CLI command to deploy the solution. Start with cloning the git repo. 

```
git clone https://github.com/aws-samples/aws-blog-automate-iam-role-deletion 
cd /aws-blog-automate-iam-role-deletion
```

Run [Cloudformation package](https://docs.aws.amazon.com/cli/latest/reference/cloudformation/package.html)to upload templates and Lambda code to your S3 bucket. The S3 bucket needs to be in the same region that you will deploy this solution

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

## Next step
Here are a few suggestions that you can take to extend this solution.

*	This solution uses a private API Gateway to handle the approval response from the IAM role owner. You need to establish private connectivity between your internal network and AWS to invoke a private API Gateway. For instructions, see How to invoke a private API.
*	Add a mechanism to control access to API Gateway by using endpoint policies for interface VPC endpoints.
*	Archive the Security Hub finding after the IAM role is deleted using the AWS CLI or AWS Console.
*	Use a Step Functions state machine for other automation that needs human approval.
*	Add the capability to report on IAM roles that were skipped due to the absence of RoleLastUsed information.

