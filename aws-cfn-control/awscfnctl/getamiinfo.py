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


_PROPS = [
    'Name',
    'ImageId',
    'ImageType',
    'ImageLocation',
    'State',
    'OwnerId',
    'Description',
    'EnaSupport',
    'SriovNetSupport',
    'VirtualizationType',
    'Hypervisor',
    'Architecture',
    'RootDeviceType',
    'CreationDate',
    'Public',
    'ProductCodeId',
    'ImageOwnerAlias',
    'BlockDeviceMappings',
    'Architecture',
    'RootDeviceType',
    'RootDeviceName',
    'Public',
]

_BlockDevice_INFO = [
    'DeviceName',
    'SnapshotId',
    'DeleteOnTermination',
    'VolumeType',
    'VolumeSize',
    'Encrypted',
]


def arg_parse():
    parser = argparse.ArgumentParser(prog='get_ami_id')

    req_group = parser.add_argument_group('required arguments')
    req_group.add_argument('-i', dest='ami_id', help='AMI ID (default region is us-east-1)', required=True )

    opt_group = parser.add_argument_group('optional arguments')
    opt_group.add_argument('-r', dest='region', required=False, help="Region name (default is us-east-1)")

    return parser.parse_args()


def image_info(client, owners, ami_name):

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

    return response

def get_image_info(client, ami_id):

    response = client.describe_images(
        DryRun=False,
        ImageIds=[
            ami_id,
        ],
    )

    resp = dict()

    for p in _PROPS:
        try:
            resp[p] = response["Images"][0][p]
            if resp[p] == 1:
                resp[p] = "True"
            elif resp[p] == 0:
                resp[p] = "False"
        except KeyError:
            resp[p] = "NO VALUE FOUND"

    return resp


def print_image_info(ami, client):

    resp = dict()
    resp = get_image_info(client, ami)

    for k in _PROPS:
        if k == "BlockDeviceMappings":
            if type(resp[k]) is list:
                for blk_devs in resp[k]:
                    block_dev = dict(blk_devs)
                    for dev in block_dev.keys():
                        if type(block_dev[dev]) is str:
                            print(" {0:<20}:  {1:<30}    {2:<30}".format(k, dev, block_dev[dev]))
                        elif type(block_dev[dev]) is dict:
                            if dev == "Ebs":
                                print(" {0:<20}:    {1:<30}  {2:<30}".format(k, 'Block Device Type', dev))
                            for dev_info in block_dev[dev].keys():
                                print(" {0:<20}:    {1:<30}  {2:<30}".format(k, dev_info, block_dev[dev][dev_info]))
        else:
            print(" {0:<20}:  {1:<30}".format(k, resp[k]))


def main():

    rc = 0

    args = arg_parse()
    region = args.region
    ami = args.ami_id

    if region == "":
        region = 'us-east-1'

    client = boto3.client('ec2', region_name=region)
    print("Checking region {0} for AMI info...".format(region))
    print_image_info(ami, client)

    return rc


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print('\nReceived Keyboard interrupt.')
        print('Exiting...')
    except ValueError as e:
        print('ERROR: {0}'.format(e))




