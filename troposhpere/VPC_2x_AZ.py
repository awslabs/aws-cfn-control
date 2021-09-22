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

from troposphere import Base64, Select, FindInMap, GetAtt, GetAZs, Join, Output, If, And, Not, Or, Equals, Condition
from troposphere import Parameter, Ref, Tags, Template
from troposphere.cloudformation import Init
from troposphere.cloudfront import Distribution, DistributionConfig
from troposphere.cloudfront import Origin, DefaultCacheBehavior
from troposphere.ec2 import PortRange
from troposphere.ec2 import SubnetRouteTableAssociation
from troposphere.ec2 import InternetGateway
from troposphere.ec2 import Route
from troposphere.ec2 import RouteTable
from troposphere.ec2 import NatGateway
from troposphere.ec2 import VPC
from troposphere.ec2 import Subnet
from troposphere.ec2 import EIP
from troposphere.ec2 import VPCGatewayAttachment
from troposphere.ec2 import SecurityGroup


t = Template()

t.set_description("""\
This template deploys a VPC, with a pair of public and private subnets spread across two Availability Zones. It deploys an Internet Gateway, with a default route on the public subnets. It deploys a pair of NAT Gateways (one in each AZ), and default routes for them in the private subnets.""")


EnvironmentName = t.add_parameter(Parameter(
    "EnvironmentName",
    Type="String",
    Default="vpc-stack",
    Description="An environment name that will be prefixed to resource names",
))

PrivateSubnet1CIDR = t.add_parameter(Parameter(
    "PrivateSubnet1CIDR",
    Default="10.192.20.0/24",
    Type="String",
    Description="Please enter the IP range (CIDR notation) for the private subnet in the first Availability Zone",
))

PrivateSubnet2CIDR = t.add_parameter(Parameter(
    "PrivateSubnet2CIDR",
    Default="10.192.21.0/24",
    Type="String",
    Description="Please enter the IP range (CIDR notation) for the private subnet in the second Availability Zone",
))

PublicSubnet1CIDR = t.add_parameter(Parameter(
    "PublicSubnet1CIDR",
    Default="10.192.10.0/24",
    Type="String",
    Description="Please enter the IP range (CIDR notation) for the public subnet in the first Availability Zone",
))

PublicSubnet2CIDR = t.add_parameter(Parameter(
    "PublicSubnet2CIDR",
    Default="10.192.11.0/24",
    Type="String",
    Description="Please enter the IP range (CIDR notation) for the public subnet in the second Availability Zone",
))

VpcCIDR = t.add_parameter(Parameter(
    "VpcCIDR",
    Default="10.192.0.0/16",
    Type="String",
    Description="Please enter the IP range (CIDR notation) for this VPC",
))

AZ1 = t.add_parameter(Parameter(
    "AZ1",
    Type="AWS::EC2::AvailabilityZone::Name",
    Description="Please choose AZ1"
))

AZ2 = t.add_parameter(Parameter(
    "AZ2",
    Type="AWS::EC2::AvailabilityZone::Name",
    Description="Please choose AZ2"
))

PublicSubnet2RouteTableAssociation = t.add_resource(SubnetRouteTableAssociation(
    "PublicSubnet2RouteTableAssociation",
    SubnetId=Ref("PublicSubnet2"),
    RouteTableId=Ref("PublicRouteTable"),
))

InternetGateway = t.add_resource(InternetGateway(
    "InternetGateway",
    Tags=Tags(
        Name=Ref(EnvironmentName),
    ),
))

DefaultPublicRoute = t.add_resource(Route(
    "DefaultPublicRoute",
    GatewayId=Ref(InternetGateway),
    DestinationCidrBlock="0.0.0.0/0",
    RouteTableId=Ref("PublicRouteTable"),
    DependsOn="InternetGatewayAttachment",
))

DefaultPrivateRoute1 = t.add_resource(Route(
    "DefaultPrivateRoute1",
    DestinationCidrBlock="0.0.0.0/0",
    RouteTableId=Ref("PrivateRouteTable1"),
    NatGatewayId=Ref("NatGateway1"),
))

DefaultPrivateRoute2 = t.add_resource(Route(
    "DefaultPrivateRoute2",
    DestinationCidrBlock="0.0.0.0/0",
    RouteTableId=Ref("PrivateRouteTable2"),
    NatGatewayId=Ref("NatGateway2"),
))

PrivateSubnet2RouteTableAssociation = t.add_resource(SubnetRouteTableAssociation(
    "PrivateSubnet2RouteTableAssociation",
    SubnetId=Ref("PrivateSubnet2"),
    RouteTableId=Ref("PrivateRouteTable2"),
))

PrivateRouteTable2 = t.add_resource(RouteTable(
    "PrivateRouteTable2",
    VpcId=Ref("VPCId"),
    Tags=Tags(
        Name={ "Fn::Sub": "${EnvironmentName} Private Routes (AZ2)" },
    ),
))

NatGateway1 = t.add_resource(NatGateway(
    "NatGateway1",
    SubnetId=Ref("PublicSubnet1"),
    AllocationId=GetAtt("NatGateway1EIP", "AllocationId"),
))

NatGateway2 = t.add_resource(NatGateway(
    "NatGateway2",
    SubnetId=Ref("PublicSubnet2"),
    AllocationId=GetAtt("NatGateway2EIP", "AllocationId"),
))

PrivateRouteTable1 = t.add_resource(RouteTable(
    "PrivateRouteTable1",
    VpcId=Ref("VPCId"),
    Tags=Tags(
        Name={ "Fn::Sub": "${EnvironmentName} Private Routes (AZ1)" },
    ),
))

VPCId = t.add_resource(VPC(
    "VPCId",
    CidrBlock=Ref(VpcCIDR),
    EnableDnsSupport="true",
    EnableDnsHostnames="true",
    Tags=Tags(
        Name=Ref(EnvironmentName),
    ),
))

PrivateSubnet1 = t.add_resource(Subnet(
    "PrivateSubnet1",
    Tags=Tags(
        Name={ "Fn::Sub": "${EnvironmentName} Private Subnet (AZ1)" },
    ),
    VpcId=Ref(VPCId),
    CidrBlock=Ref(PrivateSubnet1CIDR),
    MapPublicIpOnLaunch=False,
    AvailabilityZone=Ref(AZ1)
))

PrivateSubnet2 = t.add_resource(Subnet(
    "PrivateSubnet2",
    Tags=Tags(
        Name={ "Fn::Sub": "${EnvironmentName} Private Subnet (AZ2)" },
    ),
    VpcId=Ref(VPCId),
    CidrBlock=Ref(PrivateSubnet2CIDR),
    MapPublicIpOnLaunch=False,
    AvailabilityZone=Ref(AZ2)
))

PublicSubnet1RouteTableAssociation = t.add_resource(SubnetRouteTableAssociation(
    "PublicSubnet1RouteTableAssociation",
    SubnetId=Ref("PublicSubnet1"),
    RouteTableId=Ref("PublicRouteTable"),
))

NatGateway1EIP = t.add_resource(EIP(
    "NatGateway1EIP",
    Domain="vpc",
    DependsOn="InternetGatewayAttachment",
))

PrivateSubnet1RouteTableAssociation = t.add_resource(SubnetRouteTableAssociation(
    "PrivateSubnet1RouteTableAssociation",
    SubnetId=Ref(PrivateSubnet1),
    RouteTableId=Ref(PrivateRouteTable1),
))

PublicRouteTable = t.add_resource(RouteTable(
    "PublicRouteTable",
    VpcId=Ref(VPCId),
    Tags=Tags(
        Name={ "Fn::Sub": "${EnvironmentName} Public Routes" },
    ),
))

NatGateway2EIP = t.add_resource(EIP(
    "NatGateway2EIP",
    Domain="vpc",
    DependsOn="InternetGatewayAttachment",
))

PublicSubnet1 = t.add_resource(Subnet(
    "PublicSubnet1",
    Tags=Tags(
        Name={ "Fn::Sub": "${EnvironmentName} Public Subnet (AZ1)" },
    ),
    VpcId=Ref(VPCId),
    CidrBlock=Ref(PublicSubnet1CIDR),
    MapPublicIpOnLaunch=True,
    AvailabilityZone=Ref(AZ1)
))

PublicSubnet2 = t.add_resource(Subnet(
    "PublicSubnet2",
    Tags=Tags(
        Name={ "Fn::Sub": "${EnvironmentName} Public Subnet (AZ2)" },
    ),
    VpcId=Ref(VPCId),
    CidrBlock=Ref(PublicSubnet2CIDR),
    MapPublicIpOnLaunch=True,
    AvailabilityZone=Ref(AZ2)
))

InternetGatewayAttachment = t.add_resource(VPCGatewayAttachment(
    "InternetGatewayAttachment",
    VpcId=Ref(VPCId),
    InternetGatewayId=Ref(InternetGateway),
))

NoIngressSecurityGroup = t.add_resource(SecurityGroup(
    "NoIngressSecurityGroup",
    GroupName="no-ingress-sg",
    VpcId=Ref(VPCId),
    GroupDescription="Security group with no ingress rule",
))

t.add_output([
    Output(
        "PublicSubnet1",
        Description="A reference to the public subnet in the 1st Availability Zone",
        Value=Ref(PublicSubnet1),
    ),
    Output(
        "PublicSubnets",
        Description="A list of the public subnets",
        Value=Join(",", [Ref(PublicSubnet1), Ref(PublicSubnet2)]),
    ),
    Output(
        "PublicSubnet2",
        Description="A reference to the public subnet in the 2nd Availability Zone",
        Value=Ref(PublicSubnet2),
    ),
    Output(
        "PrivateSubnet1",
        Description="A reference to the private subnet in the 1st Availability Zone",
        Value=Ref(PrivateSubnet1),
    ),
    Output(
        "PrivateSubnet2",
        Description="A reference to the private subnet in the 2nd Availability Zone",
        Value=Ref(PrivateSubnet2),
    ),
    Output(
        "PrivateSubnets",
        Description="A list of the private subnets",
        Value=Join(",", [Ref(PrivateSubnet1), Ref(PrivateSubnet2)]),
    ),
    Output(
        "VPCId",
        Description="A reference to the created VPC",
        Value=Ref(VPCId),
    ),
    Output(
        "NoIngressSecurityGroup",
        Description="Security group with no ingress rule",
        Value=Ref(NoIngressSecurityGroup),
    )
])

print(t.to_json(indent=2))




