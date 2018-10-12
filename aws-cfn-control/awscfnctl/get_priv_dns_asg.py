#!/usr/bin/env python

# Copyright 2013-2016 Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"). You may not use this file except in compliance with the
# License. A copy of the License is located at
#
# http://aws.amazon.com/apache2.0/
#
# or in the "LICENSE.txt" file accompanying this file. This file is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES
# OR CONDITIONS OF ANY KIND, express or implied. See the License for the specific language governing permissions and
# limitations under the License.


import sys
import boto3
import argparse

progname = 'get_priv_dns_asg'

def arg_parse():


    parser = argparse.ArgumentParser(prog=progname,
                                     description='Print instance info from an ASG',
                                     epilog='Example:  {} -s <stack_name> -r <region>'.format(progname)
                                     )

    parser.add_argument('-i', dest='print_inst_id', action='store_true',
                        help='Print the instance IDs with the private DNS names'
                        )

    req_group = parser.add_argument_group('required arguments')

    # required arguments
    req_group.add_argument('-a', dest='asg', required="True")
    req_group.add_argument('-r', dest='region', required="True")

    return parser.parse_args()


def main():

    args = arg_parse()

    region = args.region
    asg = args.asg

    asg_client = boto3.client('autoscaling', region_name=region)
    asg_response = asg_client.describe_auto_scaling_groups(AutoScalingGroupNames=[asg])
    ec2 = boto3.resource('ec2', region_name=region)

    # Build instance list
    for r in asg_response['AutoScalingGroups']:
        for i in r['Instances']:
            if args.print_inst_id:
                print('{0} {1}'.format(
                    ec2.Instance(i['InstanceId']).instance_id,
                    ec2.Instance(i['InstanceId']).private_dns_name.replace('.ec2.internal', ''))
                )
            else:
                print(ec2.Instance(i['InstanceId']).private_dns_name.replace('.ec2.internal', ''))


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print '\nReceived Keyboard interrupt.'
        print 'Exiting...'
    except ValueError as e:
        print('ERROR: {0}'.format(e))

