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
from awscfnctl import CfnControl

progname = 'asgctl'

def arg_parse():

    parser = argparse.ArgumentParser(prog=progname,
                                     description='Control the instances in an ASG',
                                     epilog='Example:  {} <action> -a <asg_name> -r <region>'.format(progname)
                                     )

    opt_group = parser.add_argument_group('optional arguments')
    opt_group.add_argument('-r', dest='region', required=False, help="Region name")

    req_group = parser.add_argument_group('required arguments')
    req_group.add_argument('action', help='Action to take: '
                                          'status, enter-stby, exit-stby, stop, start (stop will enter standby first, '
                                          'and start will exit standby after start is complete')
    req_group.add_argument('-a', dest='asg', required=True)

    return parser.parse_args()


def main():

    args = arg_parse()

    region = args.region
    asg = args.asg
    action = args.action

    i = CfnControl(region=region, asg=asg)

    if action == 'enter-stby':
        i.asg_enter_standby()
    elif action == 'stop':
        i.asg_enter_standby()
        i.stop_instances()
    elif action == 'start':
        i.start_instances()
        i.asg_exit_standby()
    elif action == 'exit-stby':
        i.asg_exit_standby()
    elif action == 'status':
        i.ck_asg_status()
        i.ck_inst_status()

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print '\nReceived Keyboard interrupt.'
        print 'Exiting...'
    except ValueError as e:
        print('ERROR: {0}'.format(e))

