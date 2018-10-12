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

progname = 'get_inst_from_asg'

def arg_parse():

    parser = argparse.ArgumentParser(prog=progname, description='List instances in an ASG')

    opt_group = parser.add_argument_group()
    opt_group.add_argument('-r', dest='region', required=False, help="Region name")

    req_group = parser.add_argument_group('required arguments')
    req_group.add_argument('-a', dest='asg_name', required=True)

    return parser.parse_args()


def main():

    rc = 0

    args = arg_parse()

    region = args.region
    asg = args.asg_name

    cfn_client = CfnControl(region=region)

    instances = cfn_client.get_inst_from_asg(asg)

    for i in instances:
        print(' {}'.format(i))

    asg_status = cfn_client.ck_asg_inst_status(asg)

    return rc

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print '\nReceived Keyboard interrupt.'
        print 'Exiting...'

