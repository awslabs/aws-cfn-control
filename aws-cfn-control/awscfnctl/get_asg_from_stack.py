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
import boto3
import argparse
from awscfnctl import CfnControl

progname = 'get_asg_from_stack'

def arg_parse():

    parser = argparse.ArgumentParser(prog=progname, description='Launch a stack, with a config file')

    opt_group = parser.add_argument_group()
    opt_group.add_argument('-r', dest='region', required=False, help="Region name")

    req_group = parser.add_argument_group('required arguments')
    req_group.add_argument('-s', dest='stack_name', required=True)

    return parser.parse_args()


def get_asg_from_stack(stack_name, client):

    asg = list()

    stk_response = client.describe_stack_resources(StackName=stack_name)

    for resp in stk_response['StackResources']:
        for resrc_type in resp:
            if resrc_type == "ResourceType":
                if resp[resrc_type] == "AWS::AutoScaling::AutoScalingGroup":
                    asg.append(resp['PhysicalResourceId'])

    return asg


def main():

    rc = 0

    args = arg_parse()

    region = args.region
    stack = args.stack_name

    cfn_client = boto3.client('cloudformation', region_name=region)

    asg = get_asg_from_stack(stack, cfn_client)

    for a in asg:
        print(' {}'.format(a))

    return rc

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print '\nReceived Keyboard interrupt.'
        print 'Exiting...'
