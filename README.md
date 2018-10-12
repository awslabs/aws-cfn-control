# AWS CFN Control [![Build Status](https://api.travis-ci.org/awslabs/aws-cfn-control.png?branch=master)](https://travis-ci.org/awslabs/aws-cfn-control) [![PyPi Status](https://badge.fury.io/py/aws-cfn-control.png)](https://badge.fury.io/py/aws-cfn-control)


AWS-CFN-Control provides an interface to quickly deploy and redeploy CloudFormation stacks. The `cfnctl` command provides the core functionality, with several other commands that will find AMI info, get stack status, build CloudFormation mappings, and many other features.


## License

This library is licensed under the Apache 2.0 License. 


## Installation

```
pip install aws-cfn-control
```

## Launch stack using a cfnctl configuration file

TL;DR

1. Upload CloudFormation template to an s3 bucket
2. Build cfnctl configuration file
3. Fill in parameter values by editing the cfnctl configuration file
4. Launch the stack
5. Check stack status and outputs

### Upload CloudFormation template to an s3 bucket

```
$ aws s3 cp stack1.json s3://user-stacks/
```

### Build cfnctl configuration file using template in s3 bucket

The configuration process accounts for default values, built-in lists, and will prompted on any Parameter that is using "ConstraintDescription" and does not have a value.

```
$ cfnctl -r us-east-1 -b https://s3-us-west-1.amazonaws.com/user-stacks/stack1.json
Creating config file /Users/joeuser/.cfnctlconfig/stack1.json.cf
Using config file /Users/joeuser/.cfnctlconfig/stack1.json.cf
EC2 keys found in us-east-1:
  Jouser_IAD
Select EC2 Key: Jouser_IAD
Parameter "SSHBucketName" is required, but can be changed in config file
Enter SSHBucketName: jouser-keys
Getting security groups...
  sg-1234asdf | default
  sg-2345aslf | My-IPs
  sg-12823fas | aws-cloud9-Dev1-IAD-
Enter valid security group: sg-1234asdf
Getting VPC info...
  vpc-5u5u235u | 10.0.0.0/16 | False | Private VPC 1
  vpc-214u4u33 | 172.31.0.0/16 | True | Default VPC
Select VPC: vpc-5u5u235u
Getting subnets from vpc-5u5u235u...
  subnet-123ljias | us-east-1a | Default 1a
  subnet-a2939jis | us-east-1d | Default 1d
  subnet-er395948 | us-east-1f | Default 1f
  subnet-1243jjsa | us-east-1b | Default 1b
  subnet-jasdfj23 | us-east-1e | Default 1e
  subnet-asdfeirj | us-east-1c | Default 1c
Select subnet: subnet-123ljias
Done building cfnctl config file.
```

### Fill in parameter values by editing the cfnctl configuration file

Edit the configuration file as needed, if you see "<VALUE_NEEDED>", those values can not be null for successful stack luanch.

```
[AWS-Config]
TemplateUrl = https://s3-us-west-1.amazonaws.com/user-stacks/stack1.json

[Paramters]
ASG01ClusterSize                    = 2
ASG01InstanceType                   = c4.8xlarge
ASG01MaxClusterSize                 = 2
ASG01MinClusterSize                 = 0
AdditionalBucketName                =
CreateElasticIP                     = True
EC2KeyName                          = Joeuser_IAD
EfsId                               =
OperatingSystem                     = alinux
SSHBucketName                       = jouser-keys
SSHClusterKeyPriv                   = id_rsa
SSHClusterKeyPub                    = id_rsa.pub
SecurityGroups                      = sg-1234asdf
Subnet                              = subnet-123ljias
UsePublicIp                         = True
VPCId                               = vpc-5u5u235u
```


### Launch the stack

```
$ cfnctl -s st1 -r us-east-1 -c stack1.json.cf
Using config file: /Users/jouser/.cfnctlconfig/stack1.json.cf
cluster-test2                  :  CREATE_IN_PROGRESS
RootRole                       :  CREATE_IN_PROGRESS
PlacementGroup                 :  CREATE_IN_PROGRESS
EIPAddress                     :  CREATE_COMPLETE
RootRole                       :  CREATE_COMPLETE
RootInstanceProfile            :  CREATE_IN_PROGRESS
RootInstanceProfile            :  CREATE_COMPLETE
ASG01LaunchConfiguration       :  CREATE_IN_PROGRESS
ASG01LaunchConfiguration       :  CREATE_COMPLETE
AutoScalingGroup01             :  CREATE_IN_PROGRESS
AutoScalingGroup01             :  CREATE_IN_PROGRESS
AutoScalingGroup01             :  CREATE_COMPLETE
st1                            :  CREATE_COMPLETE
```

### Check stack status and outputs

After the creation is finished, the parameters and outputs are printed out:

```
[Parameters]
OperatingSystem                     = alinux
SSHClusterKeyPriv                   = id_rsa
ASG01InstanceType                   = c4.8xlarge
SSHClusterKeyPub                    = id_rsa.pub
SecurityGroups                      = sg-1234asdf
ASG01ClusterSize                    = 2
VPCId                               = vpc-5u5u235u
CreateElasticIP                     = True
ASG01MaxClusterSize                 = 2
AdditionalBucketName                =
EfsId                               =
SSHBucketName                       = jouser-keys
ASG01MinClusterSize                 = 0
UsePublicIp                         = True
EC2KeyName                          = Jouser_IAD
Subnet                              = subnet-123ljias

[Outputs]
ElasticIP                           = 109.234.22.45

```


## AWS Key setup


## Listing active stacks


