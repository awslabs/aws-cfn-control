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
import json
import boto3
import argparse

#aws ec2 describe-images --owners 309956199498  --region us-west-2 --filters Name=name,Values=RHEL-7.3_HVM_GA-20161026-x86_64-1-Hourly2-GP2

def arg_parse():
    parser = argparse.ArgumentParser(prog='get_ami_id')
    parser.add_argument('--amzn',
                        dest='alinux',
                        type=str,
                        help='Base Amazon Linux AMI ID (xx-xxxxxxxxx) *specifically* in us-east-1, '
                             'use this site for Amazon Linux: '
                             ' https://aws.amazon.com/amazon-linux-ami/',
                        required=False
                        )
    parser.add_argument('--amzn2',
                        dest='alinux2',
                        type=str,
                        help='Base Amazon Linux 2 AMI ID (xx-xxxxxxxxx) *specifically* in us-east-1, '
                             'use this site for Amazon Linux 2: '
                             ' https://aws.amazon.com/amazon-linux-ami/',
                        required=False
                        )
    parser.add_argument('--centos6',
                        dest='centos6',
                        type=str,
                        help='Base CentOS6 Linux AMI ID (xx-xxxxxxxxx) *specifically* in us-east-1, '
                             'use this site for CentOS AMI info: '
                             ' https://wiki.centos.org/Cloud/AWS',
                        required=False
                        )
    parser.add_argument('--centos7',
                        dest='centos7',
                        type=str,
                        help='Base Centos7 Linux AMI ID (xx-xxxxxxxxx) *specifically* in us-east-1, '
                             'use this site for CentOS AMI info: '
                             ' https://wiki.centos.org/Cloud/AWS',
                        required=False
                        )
    parser.add_argument('--rhel7',
                        dest='rhel7',
                        type=str,
                        help='Base RHEL7 Linux AMI ID (xx-xxxxxxxxx) *specifically* in us-east-1, '
                             'use this site for RHEL 7 AMI info'
                             ' AWS Console',
                        required=False
                        )
    parser.add_argument('--suse11',
                        dest='suse11',
                        type=str,
                        help='Base SUSE 11 Linux AMI ID (xx-xxxxxxxxx) *specifically* in us-east-1, '
                             'use this site for SuSE 11 info: '
                             ' AWS Console',
                        required=False
                        )
    parser.add_argument('--suse12',
                        dest='suse12',
                        type=str,
                        help='Base SUSE 12 Linux AMI ID (xx-xxxxxxxxx) *specifically* in us-east-1, '
                             'use this site for SuSE 12 info: '
                             ' AWS Console',
                        required=False
                        )
    parser.add_argument('--ubuntu14',
                        dest='ubuntu14',
                        type=str,
                        help='Base Ubuntu 14 Linux AMI ID (xx-xxxxxxxxx) *specifically* in us-east-1, '
                             'use this site for Ubuntu14: '
                             ' AWS Console',
                        required=False
                        )
    parser.add_argument('--ubuntu16',
                        dest='ubuntu16',
                        type=str,
                        help='Base Ubuntu 16 Linux AMI ID (xx-xxxxxxxxx) *specifically* in us-east-1, '
                             'use this site for Ubuntu16: '
                             ' AWS Console',
                        required=False
                        )

    return parser.parse_args()


def image_info(client, owners, ami_name, region):

    response = client.describe_images(
        DryRun=False,
        Owners=[
            owners,
        ],
        Filters=[
            {
                'Name': 'name',
                'Values': [
                    ami_name,
                ]
            },
        ]
    )

    try:
        if response["Images"][0]["ImageId"]:
            return response
    except:
        print "Does the AMI requested exist in {0}? Not adding region {0} to list. Continuing...".format(region)
        return "NONE"


def get_image_info(client, ami_id):

    try:
        response = client.describe_images(
            DryRun=False,
            ImageIds=[
                ami_id,
            ],
        )
    except Exception as e:
        print e
        print "Does {0} exist in us-east-1?  Checking next region ...".format(ami_id)
        sys.exit(1)

    ami_name     = response["Images"][0]["Name"]
    owners       = 'NONE'
    description  = 'NONE'
    ena          = 'NONE'
    sriov        = 'NONE'

    try:
        owners       = response["Images"][0]["OwnerId"]
        description  = response["Images"][0]["Description"]
        ena          = response["Images"][0]["EnaSupport"]
        sriov        = response["Images"][0]["SriovNetSupport"]
    except KeyError, e:
        pass

    return ami_name, owners, description, ena, sriov


def print_image_info(args, client):

    for arg_n, ami_id in vars(args).items():
        if ami_id:
            (ami_name, owners, description, ena, sriov) = get_image_info(client, ami_id)
            print('Building mappings for:\n'
                  ' Argument Name: {0}\n'
                  ' AMI Name:      {1}\n'
                  ' AMI ID:        {2}\n'
                  ' Owners ID:     {3}\n'
                  ' AMI Desc:      {4}\n'
                  ' ENA Support:   {5}\n'
                  ' SRIOV Support: {6}\n'
                  .format(arg_n, ami_name, ami_id, owners, description, ena, sriov))

def main():

    rc = 0

    ami_map = dict()

    args = arg_parse()

    client_iad = boto3.client('ec2', region_name='us-east-1')
    r_response_iad = client_iad.describe_regions()

    print_image_info(args, client_iad)
    print("Getting AMI IDs from regions: ")

    for r in r_response_iad["Regions"]:
        region=r["RegionName"]
        print(" " + region)

        client = boto3.client('ec2', region_name=region)

        response = dict()
        ami_map[region] = dict()

        for arg_n, ami_id_iad in vars(args).items():
            if ami_id_iad:
                (ami_name, owners, description, ena, sriov) = get_image_info(client_iad, ami_id_iad)
                response[arg_n] = image_info(client, owners, ami_name, region)
                if response[arg_n] is not "NONE":
                    ami_map[region].update({arg_n: response[arg_n]["Images"][0]["ImageId"]})

    ami_map = { "AWSRegionAMI": ami_map }
    ami_map = { "Mappings": ami_map }

    print json.dumps(ami_map, indent=2, sort_keys=True)

    ##print(ami_map)

    return rc


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print '\nReceived Keyboard interrupt.'
        print 'Exiting...'
    except ValueError as e:
        print('ERROR: {0}'.format(e))



