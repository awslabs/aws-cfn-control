#!/usr/bin/env python

#
# Copyright 2018 Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"). You may not use this file
# except in compliance with the License. A copy of the License is located at
#
#     http://aws.amazon.com/apache2.0/
#
# or in the "license" file accompanying this file. This file is distributed on an "AS IS"
# BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.
#

import sys
from pprint import pprint

from troposphere import Base64, FindInMap, GetAtt, Join, iam, Tags
from troposphere import Parameter, Output, Ref, Template, Condition, Equals, And, Or, Not, If
from troposphere.cloudformation import WaitCondition, WaitConditionHandle
from troposphere import cloudformation, autoscaling
from troposphere.autoscaling import AutoScalingGroup, Tag, Metadata
from troposphere.autoscaling import LaunchConfiguration
from troposphere.elasticloadbalancing import LoadBalancer
from troposphere.policies import (
    AutoScalingReplacingUpdate, AutoScalingRollingUpdate, UpdatePolicy
)
import troposphere.ec2 as ec2
from troposphere.ec2 import PortRange, NetworkAcl, Route, \
    VPCGatewayAttachment, SubnetRouteTableAssociation, Subnet, RouteTable, \
    VPC, NetworkInterfaceProperty, NetworkAclEntry, \
    SubnetNetworkAclAssociation, EIP, Instance, InternetGateway, \
    SecurityGroupRule, SecurityGroup, SecurityGroupIngress, SecurityGroupEgress
import troposphere.elasticloadbalancing as elb
from troposphere.helpers import userdata
from troposphere.iam import AccessKey, Group, LoginProfile, PolicyType, Role, InstanceProfile, User
from troposphere import GetAtt, Ref, Template
from troposphere.iam import LoginProfile, Policy, User
from troposphere.efs import FileSystem, MountTarget

from troposphere.policies import CreationPolicy, ResourceSignal


def main():

    t = Template()
    t.set_description("test instance launch")
    t.set_version("2010-09-09")

    InstUserData = [
        '#!/usr/bin/env bash\n',
        '\n',
        'set -x\n',
        '\n',
        'my_wait_handle="', Ref('InstanceWaitHandle'), '"\n',
        'curl -X PUT -H \'Content-Type:\' --data-binary \'{ "Status" : "SUCCESS",  "Reason" : "Instance launched",  "UniqueId" : "launch001",  "Data" : "Instance launched."}\'  "${my_wait_handle}"', '\n',
        '\n',
    ]

    EC2KeyName = t.add_parameter(Parameter(
        'EC2KeyName',
        Type="AWS::EC2::KeyPair::KeyName",
        Description="Name of an existing EC2 KeyPair to enable SSH access to the instance.",
        ConstraintDescription="REQUIRED: Must be a valud EC2 key pair"
    ))

    OperatingSystem = t.add_parameter(Parameter(
        'OperatingSystem',
        Type="String",
        Description="Operating System",
        Default="centos7",
        AllowedValues=[
            "alinux2",
            "centos7",
            "rhel7",
        ],
        ConstraintDescription="Must be: alinux2, centos7, rhel7"
    ))

    myInstanceType = t.add_parameter(Parameter(
        'MyInstanceType',
        Type="String",
        Description="Instance type",
        Default="m5.24xlarge",
    ))

    VPCId = t.add_parameter(Parameter(
        'VPCId',
        Type="AWS::EC2::VPC::Id",
        Description="VPC Id for this instance"
    ))

    Subnet = t.add_parameter(Parameter(
        'Subnet',
        Type="AWS::EC2::Subnet::Id",
        Description="Subnet IDs"
    ))

    ExistingSecurityGroup = t.add_parameter(Parameter(
        'ExistingSecurityGroup',
        Type="AWS::EC2::SecurityGroup::Id",
        Description="OPTIONAL: Choose an existing Security Group ID, e.g. sg-abcd1234"
    ))

    UsePublicIp = t.add_parameter(Parameter(
        'UsePublicIp',
        Type="String",
        Description="Should a public IP address be given to the instance",
        Default="true",
        ConstraintDescription="true/false",
        AllowedValues=[
            "true",
            "false"
        ]
    ))

    SshAccessCidr = t.add_parameter(Parameter(
        'SshAccessCidr',
        Type="String",
        Description="CIDR Block for SSH access, default 0.0.0.0/0",
        Default="0.0.0.0/0",
        AllowedPattern="(\\d{1,3})\\.(\\d{1,3})\\.(\\d{1,3})\\.(\\d{1,3})/(\\d{1,2})",
        ConstraintDescription="Must be a valid CIDR x.x.x.x/x"
    ))

    RootRole = t.add_resource(iam.Role(
        "RootRole",
        AssumeRolePolicyDocument={"Statement": [{
            "Effect": "Allow",
            "Principal": {
                "Service": [ "ec2.amazonaws.com" ]
            },
            "Action": [ "sts:AssumeRole" ]
        }]}
    ))

    SshSecurityGroup = t.add_resource(SecurityGroup(
        "SshSecurityGroup",
        VpcId = Ref(VPCId),
        GroupDescription = "SSH Secuirty group",
        SecurityGroupIngress=[
            ec2.SecurityGroupRule(
                IpProtocol="tcp",
                FromPort="22",
                ToPort="22",
                CidrIp=Ref(SshAccessCidr),
            ),
        ]
    ))

    RootInstanceProfile = t.add_resource(InstanceProfile(
        "RootInstanceProfile",
        Roles=[Ref(RootRole)]
    ))

    tags = Tags(Name=Ref("AWS::StackName"))

    myInstance = t.add_resource(ec2.Instance(
        'MyInstance',
        ImageId=FindInMap("AWSRegionAMI", Ref("AWS::Region"), Ref(OperatingSystem)),
        KeyName=Ref(EC2KeyName),
        InstanceType=(Ref(myInstanceType)),
        NetworkInterfaces=[
            NetworkInterfaceProperty(
                GroupSet=If(
                    "not_existing_sg",
                    [Ref(SshSecurityGroup)],
                    [Ref(SshSecurityGroup), Ref(ExistingSecurityGroup)]
                ),
                AssociatePublicIpAddress=Ref(UsePublicIp),
                DeviceIndex='0',
                DeleteOnTermination='true',
                SubnetId=Ref(Subnet))],
        IamInstanceProfile=(Ref(RootInstanceProfile)),
        UserData=Base64(Join('', InstUserData)),
    ))

    t.add_mapping('AWSRegionAMI', {
        "ap-northeast-1": {
            "centos7": "ami-8e8847f1",
            "rhel7": "ami-6b0d5f0d"
        },
        "ap-northeast-2": {
            "centos7": "ami-bf9c36d1",
            "rhel7": "ami-3eee4150"
        },
        "ap-south-1": {
            "centos7": "ami-1780a878",
            "rhel7": "ami-5b673c34"
        },
        "ap-southeast-1": {
            "centos7": "ami-8e0205f2",
            "rhel7": "ami-76144b0a"
        },
        "ap-southeast-2": {
            "centos7": "ami-d8c21dba",
            "rhel7": "ami-67589505"
        },
        "ca-central-1": {
            "centos7": "ami-e802818c",
            "rhel7": "ami-49f0762d"
        },
        "eu-central-1": {
            "centos7": "ami-dd3c0f36",
            "rhel7": "ami-c86c3f23"
        },
        "eu-west-1": {
            "centos7": "ami-3548444c",
            "rhel7": "ami-7c491f05"
        },
        "eu-west-2": {
            "centos7": "ami-00846a67",
            "rhel7": "ami-7c1bfd1b"
        },
        "eu-west-3": {
            "centos7": "ami-262e9f5b",
            "rhel7": "ami-5026902d"
        },
        "sa-east-1": {
            "centos7": "ami-cb5803a7",
            "rhel7": "ami-b0b7e3dc"
        },
        "us-east-1": {
            "centos7": "ami-9887c6e7",
            "rhel7": "ami-6871a115"
        },
        "us-east-2": {
            "centos7": "ami-9c0638f9",
            "rhel7": "ami-03291866"
        },
        "us-west-1": {
            "centos7": "ami-4826c22b",
            "rhel7": "ami-18726478"
        },
        "us-west-2": {
            "centos7": "ami-3ecc8f46",
            "rhel7": "ami-28e07e50"
        }
    })

    t.add_condition(
        "not_existing_sg",
        Equals(Ref(ExistingSecurityGroup), "")
    )

    t.add_condition(
        "Has_Public_Ip",
        Equals(Ref(UsePublicIp), "true")
    )

    mywaithandle = t.add_resource(WaitConditionHandle('InstanceWaitHandle'))

    mywaitcondition = t.add_resource(WaitCondition(
        "InstanceWaitCondition",
        Handle=Ref(mywaithandle),
        Timeout="1500",
        DependsOn="MyInstance"
    ))

    t.add_output([
        Output(
            "InstanceID",
            Description="Instance ID",
            Value=Ref(myInstance)
        )
    ])

    t.add_output([
        Output(
            "InstancePrivateIP",
            Value=GetAtt('MyInstance', 'PrivateIp')
        )
    ])

    t.add_output([
        Output(
            "InstancePublicIP",
            Value=GetAtt('MyInstance', 'PublicIp'),
            Condition="Has_Public_Ip"
        )
    ])

    #print(t.to_yaml())
    print(t.to_json(indent=2))


if __name__ == "__main__":
    sys.exit(main())
