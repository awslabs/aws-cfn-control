#!/usr/bin/env python

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
import argparse
import datetime
from awscfnctl import CfnControl

def prRed(prt): return("\033[91m{}\033[00m".format(prt))
def prGreen(prt): return("\033[92m{}\033[00m".format(prt))
def prYellow(prt): return("\033[93m{}\033[00m".format(prt))
def prLightPurple(prt): return("\033[94m{}\033[00m".format(prt))
def prPurple(prt): return("\033[95m{}\033[00m".format(prt))
def prCyan(prt): return("\033[96m{}\033[00m".format(prt))
def prLightGray(prt): return("\033[97m{}\033[00m".format(prt))
def prBlack(prt): return("\033[98m{}\033[00m".format(prt))


progname = 'getinstinfo'


def Sort(sub_li):

    # reverse = None (Sorts in Ascending order)
    # key is set to sort using second element of
    # sublist lambda has been used
    sub_li.sort(key = lambda x: x[1])
    return sub_li


def print_header():

    print('{:<20} {:<20} {:<20.20} {:<30}  {:<15}  {:<7}  {:<15}  {:<20}'.format(
        'Instance ID',
        'Launch Date',
        'Name',
        'Internal DNS',
        'Internal IP',
        'State',
        'Public IP',
        'Instance type'
    ))


def arg_parse():

    parser = argparse.ArgumentParser(prog=progname, description='Get instance info')

    opt_group = parser.add_argument_group()
    opt_group.add_argument('-s', dest='instance_state', required=False,
                           help='Instance State (pending | running | shutting-down | terminated | stopping | stopped)'
                           )

    req_group = parser.add_argument_group('required arguments')
    req_group.add_argument('-r', dest='region', required=True)

    return parser.parse_args()

def main():

    rc = 0

    args = arg_parse()
    region = args.region
    instance_state = args.instance_state

    inst_info_all = list()

    client = CfnControl(region=region)
    for inst, info in client.get_instance_info(instance_state=instance_state).items():
        inst_info = list()
        inst_info.append(inst)
        for k, v in info.items():
            if isinstance(v, datetime.datetime):
                v = str(v)[:-6]
            inst_info.append(v)
        inst_info_all.append(inst_info)

    print
    print_header()
    print(155 * '-')
    print('\n'.join('{:<20} {:<20} {:<20.20}  {:<30}  {:<15}  {:<7}  {:<15}  {:<20}'.format(*i) for i in Sort(inst_info_all)))
    print

    return rc

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print '\nReceived Keyboard interrupt.'
        print 'Exiting...'
    except ValueError as e:
        print('ERROR: {0}'.format(e))



