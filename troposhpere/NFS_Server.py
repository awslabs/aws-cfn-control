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
    t.add_version("2010-09-09")
    t.add_description(
        "Currently supporting RHEL/CentOS 7.5.  Setup IAM role and security groups, "
        "launch instance, create/attach 10 EBS volumes, install/fix ZFS "
        "(http://download.zfsonlinux.org/epel/zfs-release.el7_5.noarch.rpm), "
        "create zfs RAID6 pool, setup NFS server, export NFS share"
    )

    InstUserData = list()
    InstUserData = [
        '#!/usr/bin/env bash\n',
        '\n',
        'set -x\n',
        '\n',
        '##exit 0\n',  # use this to disable all user-data and bring up files
        '\n',
        'zfs_pool_name="', Ref('ZfsPool'), '"\n',
        'zfs_mount_point="', Ref('ZfsMountPoint'), '"\n',
        'nfs_cidr_block="', Ref('NFSCidr'), '"\n',
        'nfs_opts="', Ref('NFSOpts'), '"\n',
        'my_wait_handle="', Ref('NFSInstanceWaitHandle'), '"\n',
        '\n',
    ]

    with open('_include/Tropo_build_zfs_export_nfs.sh', 'r',) as ud_file:
        user_data_file = ud_file.readlines()

    for l in user_data_file:
        InstUserData.append(l)

    t.add_metadata({
        'AWS::CloudFormation::Interface': {
            'ParameterGroups': [
                {
                    'Label': {'default': 'Instance Configuration'},
                    'Parameters': [
                        "OperatingSystem",
                        "VPCId",
                        "Subnet",
                        "PrivateIpAddress",
                        "UsePublicIp",
                        "CreateElasticIP",
                        "EC2KeyName",
                        "NFSInstanceType",
                        "SshAccessCidr",
                        "ExistingSecurityGroup",
                        "ExistingPlacementGroup",
                        "S3BucketName"
                    ]
                },
                {
                    'Label': {'default': 'Storage Options - Required'},
                    'Parameters': [
                        "RAIDLevel",
                        "VolumeSize",
                        "VolumeType",
                        "EBSVolumeType",
                        "VolumeIops"
                    ]
                },
                {
                    'Label': {'default': 'ZFS Pool and FS Options - Required'},
                    'Parameters': [
                        "ZfsPool",
                        "ZfsMountPoint"
                    ]
                },
                {
                    'Label': {'default': 'NFS Options - Required'},
                    'Parameters': [
                        "NFSCidr",
                        "NFSOpts"
                    ]
                }
            ],
            'ParameterLabels': {
                'OperatingSystem': {'default': 'Operating System of AMI'},
                'VPCId': {'default': 'VPC ID'},
                'Subnet': {'default': 'Subnet ID'},
                "PrivateIpAddress": {'default': 'Static Private IP'},
                'UsePublicIp': {'default': 'Assign a Public IP '},
                'CreateElasticIP': {'default': 'Create and use an EIP '},
                'EC2KeyName': {'default': 'EC2 Key Name'},
                'NFSInstanceType': {'default': 'Instance Type'},
                'SshAccessCidr': {'default': 'SSH Access CIDR Block'},
                'ExistingSecurityGroup': {'default': 'OPTIONAL:  Existing Security Group'},
                'ExistingPlacementGroup': {'default': 'OPTIONAL:  Existing Placement Group'},
                'S3BucketName': {'default': 'Optional S3 Bucket Name'},
                'RAIDLevel': {'default': 'RAID Level'},
                'VolumeSize': {'default': 'Volume size of the EBS vol'},
                'VolumeType': {'default': 'Volume type of the EBS vol'},
                'EBSVolumeType': {'default': 'Volume type of the EBS vol'},
                'VolumeIops': {'default': 'IOPS for each EBS vol (only for io1)'},
                'ZfsPool': {'default': 'ZFS pool name'},
                'ZfsMountPoint': {'default': 'Mount Point'},
                'NFSCidr': {'default': 'NFS CIDR block for mounts'},
                'NFSOpts': {'default': 'NFS options'},
            }
        }
    })

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

    NFSInstanceType = t.add_parameter(Parameter(
        'NFSInstanceType',
        Type="String",
        Description="NFS instance type",
        Default="r4.16xlarge",
        AllowedValues=[
            "m4.16xlarge",
            "m4.10xlarge",
            "r4.16xlarge",
            "c8.8xlarge"
        ],
        ConstraintDescription= "Must an EC2 instance type from the list"
    ))

    VolumeType = t.add_parameter(Parameter(
        'VolumeType',
        Type="String",
        Description="Type of EBS volume",
        Default="EBS",
        AllowedValues=[
            "EBS",
            "InstanceStore"
        ],
        ConstraintDescription="Volume type has to EBS or InstanceStore"
    ))

    EBSVolumeType = t.add_parameter(Parameter(
        'EBSVolumeType',
        Description="Type of EBS volumes to create",
        Type="String",
        Default="io1",
        ConstraintDescription="Must be a either: io1, gp2, st1",
        AllowedValues= [
            "io1",
            "gp2",
            "st1"
        ]
    ))

    VolumelSize = t.add_parameter(Parameter(
        'VolumeSize',
        Type="Number",
        Default="500",
        Description="Volume size in GB"
    ))

    VolumeIops = t.add_parameter(Parameter(
        'VolumeIops',
        Type="Number",
        Default="20000",
        Description="IOPS for the EBS volume"
    ))

    RAIDLevel = t.add_parameter(Parameter(
        'RAIDLevel',
        Description="RAID Level, currently only 6 (8+2p) is supported",
        Type="String",
        Default="0",
        AllowedValues=[ "0" ],
        ConstraintDescription="Must be 0"
    ))

    ZfsPool = t.add_parameter(Parameter(
        'ZfsPool',
        Description="ZFS pool name",
        Type="String",
        Default="v01"
    ))

    ZfsMountPoint = t.add_parameter(Parameter(
        'ZfsMountPoint',
        Description="ZFS mount point, absolute path will be /pool_name/mount_point (e.g. /v01/testzfs)",
        Type="String",
        Default="testzfs"

    ))

    VPCId = t.add_parameter(Parameter(
        'VPCId',
        Type="AWS::EC2::VPC::Id",
        Description="VPC Id for this instance"
    ))

    ExistingPlacementGroup = t.add_parameter(Parameter(
        'ExistingPlacementGroup',
        Type="String",
        Default="NO_VALUE",
        Description="OPTIONAL:  Existing placement group"
    ))

    Subnet = t.add_parameter(Parameter(
        'Subnet',
        Type="AWS::EC2::Subnet::Id",
        Description="Subnet IDs"
    ))

    StaticPrivateIpAddress = t.add_parameter(Parameter(
        'StaticPrivateIpAddress',
        Type="String",
        Default="NO_VALUE",
        Description="Static Private IP address",
    ))

    ExistingSecurityGroup = t.add_parameter(Parameter(
        'ExistingSecurityGroup',
        Type="String",
        Default="NO_VALUE",
        Description="OPTIONAL: Choose an existing Security Group ID, e.g. sg-abcd1234"
    ))

    UsePublicIp = t.add_parameter(Parameter(
        'UsePublicIp',
        Type="String",
        Description="Should a public IP address be given to the instance",
        Default="True",
        ConstraintDescription="True/False",
        AllowedValues=[
            "True",
            "False"
        ]
    ))

    CreateElasticIP = t.add_parameter(Parameter(
        'CreateElasticIP',
        Type="String",
        Description="Create an Elasic IP address, that will be assinged to an instance",
        Default="True",
        ConstraintDescription="True/False",
        AllowedValues=[
            "True",
            "False"
        ]
    ))

    S3BucketName = t.add_parameter(Parameter(
        'S3BucketName',
        Type="String",
        Default="NO_VALUE",
        Description="S3 bucket to allow this instance read access."
    ))

    SshAccessCidr = t.add_parameter(Parameter(
        'SshAccessCidr',
        Type="String",
        Description="CIDR Block for SSH access",
        Default="111.222.333.444/32",
        AllowedPattern="(\\d{1,3})\\.(\\d{1,3})\\.(\\d{1,3})\\.(\\d{1,3})/(\\d{1,2})",
        ConstraintDescription="Must be a valid CIDR x.x.x.x/x"
    ))

    NFSCidr = t.add_parameter(Parameter(
        'NFSCidr',
        Type="String",
        Description="CIDR for NFS Security Group and NFS clients, to allow all access use 0.0.0.0/0",
        Default="10.0.0.0/16",
        AllowedPattern="(\\d{1,3})\\.(\\d{1,3})\\.(\\d{1,3})\\.(\\d{1,3})/(\\d{1,2})",
        ConstraintDescription="Must be a valid CIDR x.x.x.x/x"
    ))

    NFSOpts = t.add_parameter(Parameter(
        'NFSOpts',
        Description="NFS export options",
        Type="String",
        Default="(rw,async,no_root_squash,wdelay,no_subtree_check,no_acl)"
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

    BucketPolicy= t.add_resource(PolicyType(
        "BucketPolicy",
        PolicyName="BucketPolicy",
        Roles=[Ref(RootRole)],
        PolicyDocument={
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": ["s3:GetObject"],
                    "Resource": {"Fn::Join":["", ["arn:aws:s3:::", {"Ref": "S3BucketName"},"/*"]]}
                },
                {
                    "Effect": "Allow",
                    "Action": [ "s3:ListBucket"],
                    "Resource": {"Fn::Join":["", ["arn:aws:s3:::", {"Ref": "S3BucketName"}]]}
                }
            ],
        },
        Condition="Has_Bucket"
    )),

    NFSSecurityGroup = t.add_resource(SecurityGroup(
        "NFSSecurityGroup",
        VpcId = Ref(VPCId),
        GroupDescription = "NFS Secuirty group",
        SecurityGroupIngress=[
            ec2.SecurityGroupRule(
                IpProtocol="tcp",
                FromPort="2049",
                ToPort="2049",
                CidrIp=Ref(NFSCidr),
            ),
        ]
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

    EIPAddress = t.add_resource(EIP(
        'EIPAddress',
        Domain='vpc',
        Condition="create_elastic_ip"
    ))

    tags = Tags(Name=Ref("AWS::StackName"))

    NFSInstance = t.add_resource(ec2.Instance(
        'NFSInstance',
        ImageId=FindInMap("AWSRegionAMI", Ref("AWS::Region"), Ref(OperatingSystem)),
        KeyName=Ref(EC2KeyName),
        InstanceType=(Ref(NFSInstanceType)),
        NetworkInterfaces=[
            NetworkInterfaceProperty(
                SubnetId=Ref(Subnet),
                GroupSet=If(
                    "not_existing_sg",
                    [Ref(NFSSecurityGroup), Ref(SshSecurityGroup)],
                    [Ref(NFSSecurityGroup), Ref(SshSecurityGroup), Ref(ExistingSecurityGroup)]
                ),
                AssociatePublicIpAddress=Ref(UsePublicIp),
                DeviceIndex='0',
                DeleteOnTermination='true',
                PrivateIpAddress=If(
                    "Has_Static_Private_IP",
                    Ref(StaticPrivateIpAddress),
                    Ref("AWS::NoValue"),
                )
            )
        ],
        IamInstanceProfile=(Ref(RootInstanceProfile)),
        PlacementGroupName=If(
            "no_placement_group",
            Ref("AWS::NoValue"),
            Ref(ExistingPlacementGroup)
        ),
        BlockDeviceMappings=If('vol_type_ebs',
                               [
                                   ec2.BlockDeviceMapping(
                                       DeviceName="/dev/sdh",
                                       Ebs=ec2.EBSBlockDevice(
                                           VolumeSize=(Ref(VolumelSize)),
                                           DeleteOnTermination="True",
                                           Iops=(Ref(VolumeIops)),
                                           VolumeType=(Ref(EBSVolumeType))
                                       )
                                   ),
                                   ec2.BlockDeviceMapping(
                                       DeviceName="/dev/sdi",
                                       Ebs=ec2.EBSBlockDevice(
                                           VolumeSize=(Ref(VolumelSize)),
                                           DeleteOnTermination="True",
                                           Iops=(Ref(VolumeIops)),
                                           VolumeType=(Ref(EBSVolumeType))
                                       )
                                   ),
                                   ec2.BlockDeviceMapping(
                                       DeviceName="/dev/sdj",
                                       Ebs=ec2.EBSBlockDevice(
                                           VolumeSize=(Ref(VolumelSize)),
                                           DeleteOnTermination="True",
                                           Iops=(Ref(VolumeIops)),
                                           VolumeType=(Ref(EBSVolumeType))
                                       )
                                   ),
                                   ec2.BlockDeviceMapping(
                                       DeviceName="/dev/sdk",
                                       Ebs=ec2.EBSBlockDevice(
                                           VolumeSize=(Ref(VolumelSize)),
                                           DeleteOnTermination="True",
                                           Iops=(Ref(VolumeIops)),
                                           VolumeType=(Ref(EBSVolumeType))
                                       )
                                   ),
                                   ec2.BlockDeviceMapping(
                                       DeviceName="/dev/sdl",
                                       Ebs=ec2.EBSBlockDevice(
                                           VolumeSize=(Ref(VolumelSize)),
                                           DeleteOnTermination="True",
                                           Iops=(Ref(VolumeIops)),
                                           VolumeType=(Ref(EBSVolumeType))
                                       )
                                   ),
                                   ec2.BlockDeviceMapping(
                                       DeviceName="/dev/sdm",
                                       Ebs=ec2.EBSBlockDevice(
                                           VolumeSize=(Ref(VolumelSize)),
                                           DeleteOnTermination="True",
                                           Iops=(Ref(VolumeIops)),
                                           VolumeType=(Ref(EBSVolumeType))
                                       )
                                   ),
                               ],
                               { "Ref": "AWS::NoValue" },
                               ),
        UserData=Base64(Join('', InstUserData)),
    ))
    # End of NFSInstance

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
        "no_placement_group",
        Equals(Ref(ExistingPlacementGroup), "NO_VALUE")
    )

    t.add_condition(
        "not_existing_sg",
        Equals(Ref(ExistingSecurityGroup), "NO_VALUE")
    )

    t.add_condition(
        "vol_type_ebs",
        Equals(Ref(VolumeType), "EBS")
    )

    t.add_condition(
        "Has_Public_Ip",
        Equals(Ref(UsePublicIp), "True")
    )

    t.add_condition(
        "Has_Bucket",
        Not(Equals(Ref(S3BucketName), "NO_VALUE"))
    )

    t.add_condition(
        "create_elastic_ip",
        Equals(Ref(CreateElasticIP), "True")
    )

    t.add_condition(
        "Has_Static_Private_IP",
        Not(Equals(Ref(StaticPrivateIpAddress), "NO_VALUE"))
    )

    nfswaithandle = t.add_resource(WaitConditionHandle('NFSInstanceWaitHandle'))

    nfswaitcondition = t.add_resource(WaitCondition(
        "NFSInstanceWaitCondition",
        Handle=Ref(nfswaithandle),
        Timeout="1500",
        DependsOn="NFSInstance"
    ))

    t.add_output([
        Output(
            "ElasticIP",
            Description="Elastic IP address for the instance",
            Value=Ref(EIPAddress),
            Condition="create_elastic_ip"
        ),
        Output(
            "InstanceID",
            Description="Instance ID",
            Value=Ref(NFSInstance)
        ),
        Output(
            "InstancePrivateIP",
            Value=GetAtt('NFSInstance', 'PrivateIp')
        ),
        Output(
            "InstancePublicIP",
            Value=GetAtt('NFSInstance', 'PublicIp'),
            Condition="Has_Public_Ip"
        ),
        Output(
            "ElasticPublicIP",
            Value=GetAtt('NFSInstance', 'PublicIp'),
            Condition="create_elastic_ip"
        ),
        Output(
            "PrivateMountPoint",
            Description="Mount point on private network",
            Value=Join("", [
                GetAtt('NFSInstance', 'PrivateIp'),
                ":/fs1"
            ] )
        ),
        Output(
            "ExampleClientMountCommands",
            Description="Example commands to mount NFS on the clients",
            Value=Join("", [
                "sudo mkdir /nfs1; sudo mount ",
                GetAtt('NFSInstance', 'PrivateIp'),
                ":/",
                Ref("ZfsPool"),
                "/",
                Ref("ZfsMountPoint"),
                " /nfs1"
            ])
        ),
        Output(
            "S3BucketName",
            Value=(Ref("S3BucketName")),
            Condition="Has_Bucket"
        ),
        Output(
            "StaticPrivateIpAddress",
            Value=(Ref("StaticPrivateIpAddress")),
            Condition="Has_Static_Private_IP"
        )
    ])

    print(t.to_json(indent=2))


if __name__ == "__main__":
    sys.exit(main())
