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

import os
import sys
import argparse
from awscfnctl import CfnControl

progname = 'cfnctl'

def arg_parse():

    parser = argparse.ArgumentParser(prog=progname,
                                     description='Launch and manage CloudFormation templates from the command line')

    opt_group = parser.add_argument_group('optional arguments')
    opt_group.add_argument('-a', dest='ls_all_stack_info', required=False, help='List more info on all stacks', action='store_true')
    opt_group.add_argument('-b', dest='bucket', required=False, help='Bucket to upload template to')
    opt_group.add_argument('-c', dest='create_stack', required=False, help="Create a stack", action='store_true')
    opt_group.add_argument('-d', dest='del_stack', required=False, help="Delete a stack", action='store_true')
    opt_group.add_argument('-f', dest='param_file', required=False, help="cfnctl stack parameter file (includes template)")
    opt_group.add_argument('-l', dest='ls_stacks', required=False, help='List stacks', action='store_true')
    opt_group.add_argument('-nr', dest='no_rollback', required=False, help='Do not rollback', action='store_true')
    opt_group.add_argument('-p', dest='aws_profile', required=False, help='AWS Profile')
    opt_group.add_argument('-r', dest='region', required=False, help="Region name")
    opt_group.add_argument('-s', dest='stack_name', required=False, help="Stack name")
    opt_group.add_argument('-t', dest='template', required=False, help='CFN Template from local file or URL')
    opt_group.add_argument('-y', dest='no_prompt', required=False, help='On interactive question, force yes', action='store_true')
    opt_group.add_argument('-v', dest='verbose_param_file', required=False, help='Verbose config file', action='store_true')

    if len(sys.argv[1:])==0:
        parser.print_help()
        parser.exit()

    return parser.parse_args()


def main():

    rc = 0
    args = arg_parse()
    rollback = 'ROLLBACK'

    bucket = args.bucket
    create_stack = args.create_stack
    del_stack = args.del_stack
    param_file = args.param_file
    ls_stacks = args.ls_stacks
    ls_all_stack_info = args.ls_all_stack_info
    region = args.region
    stack_name = args.stack_name
    template = args.template
    no_prompt = args.no_prompt
    verbose_param_file = args.verbose_param_file

    errmsg_cr = "Creating a stack requires create flag (-c), stack name (-s), and for new stacks " \
                "the template (-t) flag or for configured stacks, the -f flag for parameters file, " \
                "which includes the template location"

    aws_profile = 'NULL'
    if args.aws_profile:
        aws_profile = args.aws_profile
        print('Using profile {0}'.format(aws_profile))

    if args.no_rollback:
        rollback = 'DO_NOTHING'

    client = CfnControl(region=region,aws_profile=aws_profile)

    if ls_all_stack_info or ls_stacks:
        if ls_all_stack_info and ls_stacks:
            errmsg = "Specify either -l or -a, not both"
            raise ValueError(errmsg)

        if ls_all_stack_info:
            print("Gathering all info on CFN stacks...")
            stacks = client.ls_stacks(show_deleted=False)
            for stack, i in sorted(stacks.items()):
                if len(stack) > 37:
                    stack = stack[:37] + ">"
                print('{0:<42.40} {1:<21.19} {2:<30.28} {3:<.30}'.format(stack, str(i[0]), i[1], i[2]))
        elif ls_stacks:
            print("Listing stacks...")
            stacks = client.ls_stacks(show_deleted=False)
            for stack, i in sorted(stacks.items()):
                print(' {}'.format(stack))
    elif create_stack:
        if stack_name and param_file and not template:
            try:
                response = client.cr_stack(stack_name, param_file, verbose=verbose_param_file, set_rollback=rollback)
            except Exception as e:
                raise ValueError(e)

        elif template and stack_name:

            if not client.url_check(template):
                if not os.path.isfile(template):
                    errmsg = 'File "{}" does not exists'.format(template)
                    raise ValueError(errmsg)
            try:
                if param_file:
                    param_file = param_file
                    print("Parameters file specified at CLI: {}".format(param_file))
                response = client.cr_stack(stack_name, param_file, verbose=verbose_param_file, set_rollback=rollback, template=template)
                return
            except Exception as e:
                if "Member must have length less than or equal to 51200" in e[0]:
                    if bucket:
                        print("Uploading {0} to bucket {1} and creating stack".format(template, bucket))
                        try:
                            template_url = client.upload_to_bucket(template,bucket,template)
                            response = client.cr_stack(stack_name, param_file, verbose=verbose_param_file, set_rollback=rollback, template=template_url)
                        except Exception as e:
                            raise ValueError(e)
                    else:
                        errmsg = "The template has too many bytes (>51,200), use the -b flag with a bucket name, or " \
                             "upload the template to an s3 bucket and specify the bucket URL with the -t flag "
                        raise ValueError(errmsg)
                else:
                    raise ValueError(e)
        elif template and not stack_name:
            raise ValueError(errmsg_cr)
        elif not template and stack_name:
            raise ValueError(errmsg_cr)
        elif not template and not stack_name:
            raise ValueError(errmsg_cr)
    elif del_stack:
        if not stack_name:
            errmsg = "Must specify a stack to delete (-s)"
            raise ValueError(errmsg)
        client.del_stack(stack_name, no_prompt=no_prompt)
    elif param_file or stack_name:
        raise ValueError(errmsg_cr)
    else:
        print("No actions requested - shouldn't have got this far.")
        return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print '\nReceived Keyboard interrupt.'
        print 'Exiting...'
    except ValueError as e:
        print('ERROR: {0}'.format(e))



