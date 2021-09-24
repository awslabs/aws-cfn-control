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
from argparse import RawTextHelpFormatter

progname = 'cfnctl'


def arg_parse():

    parser = argparse.ArgumentParser(prog=progname,
                                     description='Launch and manage CloudFormation templates from the command line',
                                     formatter_class=RawTextHelpFormatter
                                     )
    parser._optionals.title = "arguments"

    parser.add_argument('cfn_action', type=str,
                        help="REQUIRED: Action: build|create|list|delete\n"
                             "  build    Builds the CFN parameter file (-t required)\n"
                             "  create   Creates a new stack (-n and [-t|-f] required)\n"
                             "  list     List all stacks (-d provides extra detail)\n"
                             "  delete   Deletes a stack (-n is required)"
                        )
    parser.add_argument('-r', dest='region', required=False, help="Region name")
    parser.add_argument('-n', dest='stack_name', required=False, help="Stack name")
    parser.add_argument('-t', dest='template', required=False, help='CFN Template from local file or S3 URL')
    parser.add_argument('-f', dest='param_file', required=False,
                        help="Template parameter file")
    parser.add_argument('-d', dest='ls_all_stack_info', required=False, help='List details on all stacks',
                        action='store_true')
    parser.add_argument('-b', dest='bucket', required=False, help='Bucket to upload template to')
    parser.add_argument('-nr', dest='no_rollback', required=False, help='Do not rollback', action='store_true')
    parser.add_argument('-p', dest='aws_profile', required=False, help='AWS Profile')
    parser.add_argument('-y', dest='no_prompt', required=False, help='On interactive question, force yes',
                        action='store_true')
    parser.add_argument('-v', dest='verbose_param_file', required=False, help='Verbose config file',
                        action='store_true')

    if len(sys.argv[1:]) == 0:
        parser.print_help()
        parser.exit()

    return parser.parse_args()


def main():

    rc = 0
    args = arg_parse()
    rollback = 'ROLLBACK'

    create_stack = False
    del_stack = False
    ls_stacks = False
    build_param_file = False

    if args.cfn_action == "create":
        create_stack = True
    elif args.cfn_action == "delete":
        del_stack = True
    elif args.cfn_action == "list":
        ls_stacks = True
    elif args.cfn_action == "build":
        build_param_file = True
    else:
        print('Action has to be "build|create|list|delete"')
        sys.exit(1)

    bucket = args.bucket
    param_file = args.param_file
    ls_all_stack_info = args.ls_all_stack_info
    region = args.region
    stack_name = args.stack_name
    template = args.template
    no_prompt = args.no_prompt
    verbose_param_file = args.verbose_param_file

    errmsg_cr = "Creating a stack requires 'create' action, stack name (-n), and for new stacks " \
                "the template (-t) flag or for configured stacks, the -f flag for parameters file, " \
                "which includes the template location"

    aws_profile = 'NULL'
    if args.aws_profile:
        aws_profile = args.aws_profile
        print('Using profile {0}'.format(aws_profile))

    if args.no_rollback:
        rollback = 'DO_NOTHING'

    client = CfnControl(region=region, aws_profile=aws_profile)

    if ls_all_stack_info or ls_stacks:
        if ls_all_stack_info and ls_stacks:
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
            response = ""
            try:
                response = client.cr_stack(stack_name, param_file, verbose=verbose_param_file, set_rollback=rollback)
            except Exception as cr_stack_err:
                print("Got response: {0}".format(response))
                raise ValueError(cr_stack_err)

        elif template and stack_name:

            if not client.url_check(template):
                if not os.path.isfile(template):
                    errmsg = 'File "{}" does not exists'.format(template)
                    raise ValueError(errmsg)
            try:
                if param_file:
                    param_file = param_file
                    print("Parameters file specified at CLI: {}".format(param_file))

                response = client.cr_stack(stack_name, param_file, verbose=verbose_param_file, set_rollback=rollback,
                                           template=template)
                #return response
                return

            except Exception as cr_stack_err:
                if "Member must have length less than or equal to 51200" in str(cr_stack_err):
                    if bucket:
                        print("Uploading {0} to bucket {1} and creating stack".format(template, bucket))
                        response = ""
                        try:
                            template_url = client.upload_to_bucket(template, bucket, template)
                            response = client.cr_stack(stack_name, param_file, verbose=verbose_param_file,
                                                       set_rollback=rollback, template=template_url)
                        except Exception as upload_to_bucket_err:
                            print("Got response: {0}".format(response))
                            raise ValueError(upload_to_bucket_err)
                    else:
                        errmsg = "The template has too many bytes (>51,200), use the -b flag with a bucket name, or " \
                             "upload the template to an s3 bucket and specify the bucket URL with the -t flag "
                        raise ValueError(errmsg)
                else:
                    raise ValueError(cr_stack_err)
        elif template and not stack_name:
            raise ValueError(errmsg_cr)
        elif not template and stack_name:
            raise ValueError(errmsg_cr)
        elif not template and not stack_name:
            raise ValueError(errmsg_cr)
    elif del_stack:
        if not stack_name:
            errmsg = "Must specify a stack to delete (-n)"
            raise ValueError(errmsg)
        client.del_stack(stack_name, no_prompt=no_prompt)
    elif build_param_file:
        client.build_cfn_param('default', template, cli_template=template)
    elif param_file or stack_name:
        raise ValueError(errmsg_cr)
    else:
        print("No actions requested - shouldn't have got this far.")
        return 0

    return rc


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print('\nReceived Keyboard interrupt.')
        print('Exiting...')
    except ValueError as e:
        print('ERROR: {0}'.format(e))
    except Exception as e:
        print('ERROR: {0}'.format(e))
