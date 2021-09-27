# AWS CFN Control [![Build Status](https://api.travis-ci.org/awslabs/aws-cfn-control.png?branch=master)](https://travis-ci.org/awslabs/aws-cfn-control) [![PyPi Status](https://badge.fury.io/py/aws-cfn-control.png)](https://badge.fury.io/py/aws-cfn-control)


AWS-CFN-Control provides a command line interface to quickly deploy and redeploy [AWS CloudFormation stacks](https://aws.amazon.com/cloudformation/). The `cfnctl` command provides the core functionality, with several other commands that will find AMI info, get stack status, build CloudFormation mappings, and other features. AWS-CFN-Control is very useful for CloudFormation templates that have parameters, and you want to create stacks with the same parameters in multiple regions, or you want to change just a few parameters values for a new stack.


## License

This library is licensed under the Apache 2.0 License. 

## Prerequisites

It is assumed that you have an AWS account (preferably with admin privileges) and experience with CloudFormation. You will also need to be familiar with either [AWS Cloud Development Kit](https://aws.amazon.com/cdk/) (CDK) or writing your own CloudFormation templates. Although JSON or YAML formatted templates can be used, JSON is recommended. 

## Installation

```
pip install aws-cfn-control
```

## TL;DR

1. Build cfnctl parameters file
1. Launch the stack
1. Check stack status and outputs

## Usage overview 

#### Build the parameters file for a CloudFormation template:
This command builds a default parameters file:

```cfnctl build -t <template_file>```

#### Create a stack using the template or a parameters file: 

This first create command (using -t) first checks if there is an existing parameters file, and prompts if it should be used. Otherwise, a parameters file is created using the stack name (-n) appended to the template file name. You are then prompted for the stack parameters (similar to build action), and then the stack is created.

```cfnctl create -n stack001 -t <template_file>```

This second command (using -f) uses an existing parameters file, which has the template location, to create a stack. You will not be prompted for any parameters:

```cfnctl create -n stack001 -f <parameters_file>```

#### List all existing stacks 

```cfnctl list```


#### Delete a stack

```cfnctl delete -n <stack_name>```

## More detailed information

### Command help

```text
usage: cfnctl [-h] [-r REGION] [-n STACK_NAME] [-t TEMPLATE] [-f PARAM_FILE] [-d] [-b BUCKET] [-nr] [-p AWS_PROFILE] [-y] [-v] cfn_action

Launch and manage CloudFormation templates from the command line

positional arguments:
  cfn_action      REQUIRED: Action: build|create|list|delete
                    build    Builds the CFN parameter file (-t required)
                    create   Creates a new stack (-n and [-t|-f] required)
                    list     List all stacks (-d provides extra detail)
                    delete   Deletes a stack (-n is required)

arguments:
  -h, --help      show this help message and exit
  -r REGION       Region name
  -n STACK_NAME   Stack name
  -t TEMPLATE     CFN Template from local file or S3 URL
  -f PARAM_FILE   Template parameter file
  -d              List details on all stacks
  -b BUCKET       Bucket to upload template to
  -nr             Do not rollback
  -p AWS_PROFILE  AWS Profile
  -y              On interactive question, force yes
  -v              Verbose config file
```

### Using the defaults from CloudFormation templates and seeing existing resources

When using the ```build``` or ```create``` actions, as you are prompted for each parameter you will be given the choice of choosing the default value specified in the template. For example, if your template has this:
```text
    "MyInstanceType": {
      "Default": "m5.24xlarge",
      "Description": "Instance type",
      "Type": "String"
    },
```

Your prompt will have the default value included, and you just hit entire to accept the default:
```text
MyInstanceType [m5.24xlarge]:
```

#### Existing resources

For some resources, a list of existing values will be shown. For example, here is what the list of subnets look like, with the default set to ```subnet-abbbcccbbbbcd1235```:

```text
Getting subnets for vpc-0000aaaa1111bbbb2 ...
  subnet-aaaabbbcccbcd1234 | us-east-1b
  subnet-abbbcccbbbbcd12gg | us-east-1-bos-1a | Local Zone Subnet
  subnet-abbbcccbbbbcd1235 | us-east-1a
  subnet-addddbbbccbcd1232 | us-east-1f
  subnet-addddbbbccbcd1236 | us-east-1c
  subnet-addddbbbccbcd1238 | us-east-1e
  subnet-aaabbbbcccbcd1237 | us-east-1d
Select subnet: [subnet-abbbcccbbbbcd1235]: 
```

#### Required parameters

If a parameter is defined as required (```ConstraintDescription``` is used in the template), and you have not provided a value, you will see one of two messages.

1. If you ran ```cfnctl build``` you will see a message similar to this:

```text
WARNING ONLY: Parameter "MyS3Bucket" is required but can be updated in parameters file and left empty for now
```

2. If you ran ```cfnctl create``` you will see a message similar this:
```text
MyS3Bucket []: 
 REQUIREMENT: Parameter "MyS3Bucket" is required to create the stack, please enter a value, optionally exit create and rerun with build action
MyS3Bucket: 
Required parameter MyS3Bucket not entered. The stack create will fail, but the parameters file will still be built.
```

After the build completes you will see this message, reminding you to update the value in the parameters file:

```text
Some values are still needed, replace "<VALUE_NEEDED>" in /Users/joeuser/.cfnparam/My_Instance.json.default
```

In the parameters file you will see this, for ```MyS3Bucket```:

```text
MyS3Bucket                          = <VALUE_NEEDED>
```

You will need to change ```<VALUE_NEEDED>``` to a valid parameter to create the stack successfully.



### Optional (but recommended): Build cfnctl parameters file  (stored in ~/.cfnparam/)

When you run ```cfnctl build``` you will be prompted for each of the parameter values. The ```build``` process accounts for default values, and you will be double prompted on any parameter that is using ```ConstraintDescription``` and does not have a value. A file with parameters and the template location will be saved in the ```~/.cfnparam/``` directory with ```.default``` appended to the template name. For example, the default parameter file for the template named ```stack1.json```, is ```~/.cfnparam/stack1.json.default```.

Here is an example of running the ```cfnctl build``` command:

```text
$ cfnctl build -t My_Instance.json                   
Using AWS credentials profile "default"
Looks like we're in us-east-1
Creating parameters file /Users/joeuser/.cfnparam/My_Instance.json.default
EC2 keys found in us-east-1:
  Testing1 
  Joeuser_IAD 
Select EC2 Key [Joeuser_IAD]: 
Getting VPC info...
  vpc-0000aaaa1111bbbb2 | 10.0.0.0/16 | False | test1-VPC
  vpc-aaaabbbbeebce1234 | 172.31.0.0/16 | True | default-vpc
Select VPC [vpc-aaaabbbbeebce1234]: vpc-0000aaaa1111bbbb2 
Getting security groups for vpc-0000aaaa1111bbbb2 ...
  sg-1111aaaa3333bbbbcc | launch-wizard-1
  sg-2222bbbbcccc333334 | Ent-network
  sg-bbbccaa1234124efgh | default
Select secuirty group [sg-bbbccaa1234124efgh]: 
MyInstanceType [m5.2xlarge]:  t3.small 
OperatingSystem [centos7]:  alinux2
SshAccessCidr [111.222.333.444/32]:  333.333.444.444/32 
MyS3Bucket []: 
 WARNING ONLY: Parameter "MyS3Bucket" is required but can be updated in parameters file and left empty for now
MyS3Bucket: 
Getting subnets for vpc-0000aaaa1111bbbb2 ...
  subnet-aaaabbbcccbcd1234 | us-east-1b
  subnet-abbbcccbbbbcd12gg | us-east-1-bos-1a | Local Zone Subnet
  subnet-abbbcccbbbbcd1235 | us-east-1a
  subnet-addddbbbccbcd1232 | us-east-1f
  subnet-addddbbbccbcd1236 | us-east-1c
  subnet-addddbbbccbcd1238 | us-east-1e
  subnet-aaabbbbcccbcd1237 | us-east-1d
Select subnet: [subnet-abbbcccbbbbcd1235]: 
UsePublicIp [true]: 
Some values are still needed, replace "<VALUE_NEEDED>" in /Users/joeuser/.cfnparam/My_Instance.json.default
Done building cfnctl parameters file /Users/joeuser/.cfnparam/My_Instance.json.default, includes template location
```

#### Edit the parameters file, and fill in values as needed 

After running the ```cfnctl build```, in your home directory under ```~/.cfnparam/```, you will find a parameters file. Edit the parameters file as needed, if you see ```<VALUE_NEEDED>```, those values can not be null for a successful stack luanch.

Example parameters file:

```text
[AWS-Config]
TemplateBody = /Users/joeuser/templates/My_Instance.json 

[Paramters]
EC2KeyName                          = Joeuser_IAD 
ExistingSecurityGroup               = sg-bbbccaa1234124efgh 
MyInstanceType                      = t3.small
OperatingSystem                     = alinux2 
SshAccessCidr                       = 333.333.444.444/32 
SshBucket                           = <VALUE_NEEDED>
Subnet                              = subnet-abbbcccbbbbcd1235 
UsePublicIp                         = true
VpcId                               = vpc-aaaabbbbeebce1234 
```


### Create the stack 

The stack can be created in two ways, either with the ```-t``` flag or the ```-f``` flag

#### 1. Create with the ```-t``` flag

If you already created the parameters file (steps above), when you run the create command you will be prompted to choose from either the existing (default) parameters file, or continue the create while answering the parameters questions again.

For example, if the default parameters file exists you will see this:

```
$ cfnctl create -n teststack1 -t My_Instance.json
Using AWS credentials profile "default"
Looks like we're in us-east-1
Default parameters file /Users/joeuser/.cfnparam/My_Instance.json.default exists, use this file [Y/n]:  
```
Answering "y" will create the stack using the values from the previously created default parameters file. 

If you answer "n", you will be prompted for each parameter, and the parameters will be saved in the ```~/.cfnparam/``` directory with the values used to create the stack. The parameters file name is the stack name appended to the template file name. For example, the parameters file for the template named ```My_Instance.json``` when specifying the stack name ```teststack1```, will be ```~/.cfnparam/My_Instance.json.teststack1```:

```text
$ cfnctl create -n teststack1 -t My_Instance.json
Using AWS credentials profile "default"
Looks like we're in us-east-1
Default parameters file /Users/joeuser/.cfnparam/My_Instance.json.default exists, use this file [Y/n]: n
Stack parameters file does not exists, continuing...
Creating parameters file /Users/joeuser/.cfnparam/My_Instance.json.teststack1
...
```

#### 2. Create with the ```-f``` flag

You can use any parameters file (using ```-f```) to create a stack, as the parameters file has the template location and the paramters.

For example, to create a new stack (teststack2) using all the parameters from the previously created stack named ```teststack1```, you run this: 

```
$ cfnctl create -n teststack2 -f ~/.cfnparam/My_Instance.json.teststack1
```

#### Example ```cfnctl create``` using the default parameters file (from ```cfnctl build```):

Here is example output from a ```cfnctl create```, using the previously created default parameters file. The status of the stack, the parameters used, and the output(s) are also displayed:

```
$ cfnctl create -n teststack1 -t My_Instance.json
Using AWS credentials profile "default"
Looks like we're in us-east-1
Default parameters file /Users/joeuser/.cfnparam/My_Instance.json.default exists, use this file [Y/n]:  
Using parameters file: /Users/joeuser/.cfnparam/My_Instance.json.default 
Using template file: /Users/joeuser/templates/My_Instance.json 
Attempting to launch teststack1 
teststack1                             :  CREATE_IN_PROGRESS        :  User Initiated
SshSecurityGroup                       :  CREATE_IN_PROGRESS       
InstanceWaitHandle                     :  CREATE_IN_PROGRESS       
RootRole                               :  CREATE_IN_PROGRESS       
InstanceWaitHandle                     :  CREATE_IN_PROGRESS        :  Resource creation Initiated
InstanceWaitHandle                     :  CREATE_COMPLETE          
RootRole                               :  CREATE_IN_PROGRESS        :  Resource creation Initiated
SshSecurityGroup                       :  CREATE_IN_PROGRESS        :  Resource creation Initiated
SshSecurityGroup                       :  CREATE_COMPLETE          
RootRole                               :  CREATE_COMPLETE          
RootInstanceProfile                    :  CREATE_IN_PROGRESS       
RootInstanceProfile                    :  CREATE_IN_PROGRESS        :  Resource creation Initiated
RootInstanceProfile                    :  CREATE_COMPLETE          
MyInstance                             :  CREATE_IN_PROGRESS       
MyInstance                             :  CREATE_IN_PROGRESS        :  Resource creation Initiated
MyInstance                             :  CREATE_COMPLETE          
InstanceWaitCondition                  :  CREATE_IN_PROGRESS       
InstanceWaitCondition                  :  CREATE_IN_PROGRESS        :  Resource creation Initiated
InstanceWaitCondition                  :  CREATE_COMPLETE          
teststack1                             :  CREATE_COMPLETE          

Status:
teststack1                               2021-09-16 14:35:11   CREATE_COMPLETE                test instance launch

[Parameters]
ExistingSecurityGroup                  = sg-bbbccaa1234124efgh 
OperatingSystem                        = alinux2 
VpcId                                  = vpc-aaaabbbbeebce1234 
UsePublicIp                            = true                          
SshAccessCidr                          = 333.333.444.444/32 
EC2KeyName                             = Joeuser_IAD 
MyInstanceType                         = t3.small 
Subnet                                 = subnet-abbbcccbbbbcd1235 

[Outputs]
InstanceID                             = i-00011100022200333
InstancePublicIP                       = 54.12.11.13 
InstancePrivateIP                      = 172.25.5.5
```



