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
import time
import json
import yaml
import errno
import boto3
import operator
import textwrap
import subprocess
import configparser
from urllib.parse import urlparse
from botocore.exceptions import ClientError
from botocore.exceptions import EndpointConnectionError


class CfnControl:

    def __init__(self, **kwords):

        """
        Main class init

        :param kwords: aws_profile, region, asg, param_file, instances

            aws_profile:   If this is not given, then search
                             the session, otherwise use "default"

            region:        If this is not given, then search the session,
                             if it's not in the session the raise error.

            asg:           If an ASG name is given, append the instances
                             from the ASG to the instance list

            param_file:    Location of the the parameter files for
                             cfnctl command (~/.cfnparam)

            instances:     list() of instances


        """

        self.aws_profile = kwords.get('aws_profile')
        if not self.aws_profile:
            self.aws_profile = 'default'
        elif self.aws_profile == 'NULL':
            self.aws_profile = 'default'

        print('Using AWS credentials profile "{0}"'.format(self.aws_profile))

        self.session = boto3.session.Session(profile_name=self.aws_profile)
        self.region = kwords.get('region')

        if not self.region and not self.session.region_name:
            errmsg = "Must specify a region, either at the command (-r) or in your AWS CLI config"
            raise ValueError(errmsg)

        if not self.region:
            self.region = self.session.region_name

        print("Looks like we're in {0}".format(self.region))

        # boto resources
        self.s3 = self.session.resource('s3')
        self.ec2 = self.session.resource('ec2', region_name=self.region)

        # boto clients
        self.client_ec2 = self.session.client('ec2', region_name=self.region)
        self.client_asg = self.session.client('autoscaling', region_name=self.region)
        self.client_cfn = self.session.client('cloudformation', region_name=self.region)
        self.client_s3  = self.session.client('s3', region_name=self.region)

        # grab passed arguments
        self.asg = kwords.get('asg')
        self.cfn_param_file = kwords.get('param_file')

        # get instances passed as an argument
        self.instances = list()
        try:
            if kwords.get('instances'):
                self.instances = kwords.get('instances')
        except Exception as e:
            raise ValueError(e)

        # Stack variables
        #
        self.stack_name = None
        self.template = None
        self.TemplateURL = None
        self.TemplateBody = None
        self.vpc_variable_name = None

        # Set user directory and current directory
        #
        self.my_cwd = os.path.curdir
        self.homedir = os.path.expanduser("~")

        # Use user directory to build the cfnparam file location
        #  current default is   ~/.cfnparm
        #
        self.param_file_list = None
        self.cfn_param_file_values = dict()
        self.cfn_param_file_basename = None
        self.cfn_param_base_dir = ".cfnparam"
        self.cfn_param_file_dir = os.path.join(self.homedir, self.cfn_param_base_dir)

        # Check for global defaults file
        #
        global_default_file = os.path.join(os.path.join(self.cfn_param_file_dir, self.region + ".default"))
        if os.path.isfile(global_default_file):
            self.global_default_file = global_default_file
            print("Found global default file {0}".format(self.global_default_file))

        # Define other variables
        #
        self.vpc_id = None
        self.template_url = None
        self.template_body = None
        self.key_pairs = list()

        # First API call - grab key pairs, this will determine if we can talk to the API
        #
        try:
            key_pairs_response = self.client_ec2.describe_key_pairs()
        except EndpointConnectionError as e:
            errmsg = "Please make sure that the region specified ({0}) is valid\n".format(self.region)
            raise ValueError(errmsg + str(e))
        except Exception as e:
            raise ValueError(e)

        for pair in (key_pairs_response['KeyPairs']):
            self.key_pairs.append(pair['KeyName'])

        # For some lists, we only want to print out certain keys:
        #
        self.vpc_keys_to_print = ['Tag_Name',
                                  'IsDefault',
                                  'CidrBlock',
                                  ]

        self.subnet_keys_to_print = ['Tag_Name',
                                     'AvailabilityZone',
                                     ]

        self.sec_groups_keys_to_print = ['Description',
                                         'GroupName',
                                         ]

        # If the `asg` keyword was passed, then build an instance list from the ASG
        #
        if self.asg:
            response = self.client_asg.describe_auto_scaling_groups(AutoScalingGroupNames=[self.asg])

            print('Gathering instances from ASG {0}'.format(self.asg))

            # Build instance IDs list
            for r in response['AutoScalingGroups']:
                for i in r['Instances']:
                    self.instances.append(self.ec2.Instance(i['InstanceId']).instance_id)

            if not self.instances:
                print("Instance list is null, continuing...")

    @staticmethod
    def runcmd(cmdlist):
        """
        runs a command

        :param cmdlist:  command to run
        :return:  If there is an error, returns stdout and stderr, otherwise just stdout
        """

        proc = subprocess.Popen(cmdlist, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = proc.communicate()
        if proc.returncode != 0:
            log = out + err
        else:
            log = out

        return log, proc.returncode

    def instanace_list(self):
        """
        returns list() of instance IDs
        """
        return self.instances

    @staticmethod
    def inst_list_from_file(file_name):
        """
        reads a list from a named file

        :param file_name: a file name
        :return:  a list spearated but "\n"
        """
        try:
            f = open(file_name, "r")
        except:
            raise

        s = f.read()
        f.close()
        # if last char == '\n', delete it
        if s[-1] == "\n":
            s = s[:-1]
        l = s.split("\n")
        return l

    def get_asg_from_stack(self, stack_name=None):

        # returns a list of ASG names for a given stack

        self.asg = list()

        if stack_name is None:
            stack_name = self.stack_name

        # Debug
        # print('Getting ASG name(s) from stack {0} (returns a list)'.format(stack_name))

        try:
            stk_response = self.client_cfn.describe_stack_resources(StackName=stack_name)
        except ClientError as e:
            raise ValueError(e)

        for resp in stk_response['StackResources']:
            for resrc_type in resp:
                if resrc_type == "ResourceType":
                    if resp[resrc_type] == "AWS::AutoScaling::AutoScalingGroup":
                        self.asg.append(resp['PhysicalResourceId'])

        return self.asg

    def get_inst_from_asg(self, asg=None):

        if asg is None:
            asg = self.asg

        # Debug
        # print('Getting ASG instances from {0}'.format(asg))

        if type(asg) is list:
            response = self.client_asg.describe_auto_scaling_groups(AutoScalingGroupNames=asg)
        else:
            response = self.client_asg.describe_auto_scaling_groups(AutoScalingGroupNames=[asg])

        self.instances = list()
        # Build instance IDs list
        for r in response['AutoScalingGroups']:
            for i in r['Instances']:
                self.instances.append(self.ec2.Instance(i['InstanceId']).instance_id)

        return self.instances

    def asg_enter_standby(self, instances=None):

        sleep_time = 10
        print("Setting instances to ASG standby")

        if instances is None:
            instances = self.instances

        response = self.client_asg.enter_standby(InstanceIds=instances, AutoScalingGroupName=self.asg,
                                                 ShouldDecrementDesiredCapacity=True
                                                 )

        print("Sleeping for {0} seconds to allow for instances to enter standby".format(sleep_time))
        time.sleep(sleep_time)

        return response

    def asg_exit_standby(self, instances=None):

        sleep_time = 30
        print("Instances are exiting from ASG standby")

        if instances is None:
            instances = self.instances

        response = self.client_asg.exit_standby(InstanceIds=instances, AutoScalingGroupName=self.asg, )

        print("Sleeping for {0} seconds to allow for instances to exit standby".format(sleep_time))
        time.sleep(sleep_time)

        return response

    def stop_instances(self, instances=None):

        sleep_time = 300
        print("Stopping instances")

        if instances is None:
            instances = self.instances

        response = self.client_ec2.stop_instances(InstanceIds=instances, DryRun=False)
        print("Sleeping for {0} seconds to allow for instances to stop".format(sleep_time))
        time.sleep(sleep_time)

        return response

    def start_instances(self, instances=None):

        sleep_time = 120
        print("Starting instances")

        if instances is None:
            instances = self.instances

        response = self.client_ec2.start_instances(InstanceIds=instances, DryRun=False)
        print("Sleeping for {0} seconds to allow for instances to start".format(sleep_time))
        time.sleep(sleep_time)

        return response

    def terminate_instances(self, instances=None):

        sleep_time = 120
        print("Terminating instances")

        if instances is None:
            instances = self.instances

        response = self.client_ec2.terminate_instances(InstanceIds=instances, DryRun=False)
        print("Sleeping for {0} seconds to allow for instances to terminate".format(sleep_time))
        time.sleep(sleep_time)

        return response

    def ck_inst_status(self):

        response = self.client_ec2.describe_instance_status(InstanceIds=self.instances, IncludeAllInstances=True)

        running = list()
        not_running = list()

        for r in response['InstanceStatuses']:
            if (r['InstanceState']['Name']) == 'running':
                running.append(r['InstanceId'])
            else:
                not_running.append(r['InstanceId'])

        print("Instance Info:")
        print(" {0:3d}   instances are running".format(len(running)))
        print(" {0:3d}   instances are not running".format(len(not_running)))

    def ck_asg_inst_status(self, asg=None):

        if asg is None:
            asg = self.asg

        response = self.client_asg.describe_auto_scaling_groups(AutoScalingGroupNames=[asg])
        in_service = list()
        not_in_service = list()

        # Build instance IDs list
        for r in response['AutoScalingGroups']:
            for i in r['Instances']:
                if self.ec2.Instance(i['LifecycleState']).instance_id == 'InService':
                    in_service.append(self.ec2.Instance(i['InstanceId']).instance_id)
                else:
                    not_in_service.append(self.ec2.Instance(i['InstanceId']).instance_id)

        print("ASG instances status:")
        print(" {0:3d}   InService".format(len(in_service)))
        print(" {0:3d}   Not InService".format(len(not_in_service)))

        return in_service, not_in_service

    def enable_ena_vfi(self, instances=None):

        if instances is None:
            all_instances = self.instances
        else:
            all_instances = instances

        inst_add_ena_vfi = list()

        print("Checking if instances are ENA/VFI enabled")

        for inst_id in all_instances:

            response_vfi = self.client_ec2.describe_instance_attribute(
                Attribute='sriovNetSupport',
                InstanceId=inst_id
            )

            try:
                if (response_vfi['SriovNetSupport']['Value']) == 'simple':
                    pass
            except KeyError:
                if inst_id not in inst_add_ena_vfi:
                    inst_add_ena_vfi.append(inst_id)

                    # Attribute='enaSupport' is not currently supported

        if not inst_add_ena_vfi:
            print("All instances are VFI enabled (Can't check for ENA)")
            return

        print("Enabling ENA and VFI on instances")

        self.instances = inst_add_ena_vfi

        (inst_in_service, inst_in_standby) = self.ck_asg_inst_status()

        if inst_in_service:
            self.asg_enter_standby(inst_in_service)

        self.stop_instances()

        response_ec2_vfi = None
        response_ec2_ena = None

        for inst_id in self.instances:
            print('Enabling ENA/VFI on ' + inst_id)
            response_ec2_vfi = self.client_ec2.modify_instance_attribute(InstanceId=inst_id,
                                                                         SriovNetSupport={'Value': 'simple'}
                                                                         )
            response_ec2_ena = self.client_ec2.modify_instance_attribute(InstanceId=inst_id,
                                                                         EnaSupport={'Value': True},
                                                                         )

        self.start_instances()
        self.asg_exit_standby()
        if instances is None:
            self.instances = all_instances

        return response_ec2_vfi, response_ec2_ena

    def get_param_files(self, os_dir):

        if os_dir is None:
            os_dir = self.cfn_param_file_dir

        try:
            self.param_file_list = os.listdir(os_dir)
            return self.param_file_list
        except Exception as e:
            raise ValueError(e)

    def read_cfn_param_file(self, cfn_param_file=None):

        parser = configparser.SafeConfigParser()
        parser.optionxform = str

        if not cfn_param_file:
            cfn_param_file = self.cfn_param_file

        if os.path.isfile(cfn_param_file):
            print("Using parameters file: {0}".format(cfn_param_file))
            parser.read(cfn_param_file)
        elif os.path.isfile(os.path.join(self.cfn_param_file_dir, cfn_param_file + ".json.cf")):
            print("Using parameters file: {0}".format(
                os.path.join(self.cfn_param_file_dir, cfn_param_file + ".json.cf"))
            )
            parser.read(os.path.join(self.cfn_param_file_dir, cfn_param_file + ".json.cf"))
        elif os.path.isfile(os.path.join(self.cfn_param_file_dir, cfn_param_file)):
            print("Using parameters file: {0}".format(
                os.path.join(self.cfn_param_file_dir, cfn_param_file))
            )
            parser.read(os.path.join(self.cfn_param_file_dir, cfn_param_file))
        else:
            errmsg = "Config file {0} not found".format(cfn_param_file)
            raise ValueError(errmsg)

        params = list()

        boolean_keys = ['EnableEnaVfi',
                        'AddNetInterfaces',
                        'CreateElasticIP'
                        ]

        not_cfn_param_keys = ['EnableEnaVfi',
                              'AddNetInterfaces',
                              'TotalNetInterfaces',
                              'TemplateURL',
                              'TemplateBody'
                              ]

        for section_name in parser.sections():
            for key, value in parser.items(section_name):
                #print('key: {0}'.format(key))
                if key in boolean_keys:
                    value = parser.getboolean(section_name, key)

                if key in not_cfn_param_keys:
                    self.cfn_param_file_values[key] = value
                else:
                    self.cfn_param_file_values[key] = value
                    params.append(
                        {
                            'ParameterKey': key,
                            'ParameterValue': str(value),
                            'UsePreviousValue': False
                        }
                    )

        return params

    @staticmethod
    def url_check(url):
        try:
            result = urlparse.urlparse(url)
            return result.scheme and result.netloc and result.path
        except:
            return False

    def cr_stack(self, stack_name, cfn_param_file, verbose=False, set_rollback='ROLLBACK', template=None):
        """
        Three steps:

        1. Validate template
        2. Build parameters file
        3. Launch Stack

        :param stack_name:
        :param cfn_param_file:
        :param verbose:
        :param set_rollback:
        :param template:
        :return:
        """


        response = None

        try:
            stk_response = self.client_cfn.describe_stacks(StackName=stack_name)
            print('The stack "{0}" exists.  Exiting...'.format(stack_name))
            sys.exit()
        except ValueError as e:
            raise ValueError
        except ClientError as e:
            pass

        if template is not None:
            # check if the template is a URL, or a local file
            if self.url_check(template):
                self.template_url = template
                self.validate_cfn_template(template_url=self.template_url)
                if not cfn_param_file:
                    cfn_param_file = self.build_cfn_param(stack_name, self.template_url, cli_template=template, verbose=verbose)
            else:
                template_path = os.path.abspath(template)
                self.validate_cfn_template(template_body=template_path)
                if not cfn_param_file:
                    cfn_param_file = self.build_cfn_param(stack_name, template_path, cli_template=template, verbose=verbose)
                self.template_body = self.parse_cfn_template(template_path)

        cfn_params = self.read_cfn_param_file(cfn_param_file)
        self.cfn_param_file = cfn_param_file

        try:
            if self.cfn_param_file_values['TemplateURL']:
                self.template_url = self.cfn_param_file_values['TemplateURL']
                print("Using template from URL {}".format(self.template_url))
        except Exception as e:
            if "TemplateURL" in str(e):
                try:
                    if self.cfn_param_file_values['TemplateBody']:
                        self.template_body = self.cfn_param_file_values['TemplateBody']
                        print("Using template file {}".format(self.template_body))
                        self.template_body = self.parse_cfn_template(self.template_body)
                except Exception as e:
                    raise ValueError(e)
            else:
                raise ValueError(e)

        print("Attempting to launch {}".format(stack_name))

        try:

            if self.template_url:

                response = self.client_cfn.create_stack(
                    StackName=stack_name,
                    TemplateURL=self.template_url,
                    Parameters=cfn_params,
                    TimeoutInMinutes=600,
                    Capabilities=['CAPABILITY_IAM'],
                    OnFailure=set_rollback,
                    Tags=[
                           {
                               'Key': 'Name',
                               'Value': stack_name
                           },
                           {
                               'Key': 'cfnctl_param_file',
                               'Value': os.path.basename(self.cfn_param_file)
                           },
                    ]
                )

            elif self.template_body:

                response = self.client_cfn.create_stack(
                    StackName=stack_name,
                    TemplateBody=self.template_body,
                    Parameters=cfn_params,
                    TimeoutInMinutes=600,
                    Capabilities=['CAPABILITY_IAM'],
                    OnFailure=set_rollback,
                    Tags=[
                           {
                               'Key': 'Name',
                               'Value': stack_name
                           },
                           {
                               'Key': 'cfnctl_param_file',
                               'Value': os.path.basename(self.cfn_param_file)
                           },
                    ]
                )

        except ClientError as e:
            print(e.response['Error']['Message'])
            return

        stack_rc = self.stack_status(stack_name=stack_name)

        if stack_rc != 'CREATE_COMPLETE':
            print('Stack creation failed with {0}'.format(stack_rc))
            return

        self.asg = self.get_asg_from_stack(stack_name=stack_name)
        self.instances = self.get_inst_from_asg(self.asg)

        try:
            if self.cfn_param_file_values['EnableEnaVfi']:
                print("Instances finishing booting")
                time.sleep(60)
                self.enable_ena_vfi(self.instances)
        except KeyError:
            pass

        try:
            if self.cfn_param_file_values['AddNetInterfaces']:
                self.add_net_dev()
        except KeyError:
            pass

        stk_output = self.get_stack_output(stack_name)

        try:
            eip = stk_output['ElasticIP']
            self.set_elastic_ip(stack_eip=eip)
        except KeyError:
            pass

        self.stack_name = stack_name
        self.get_stack_info(stack_name=stack_name)

        return response

    def del_stack(self,stack_name, no_prompt=None):

        try:
            stk_response = self.client_cfn.describe_stacks(StackName=stack_name)

            if stk_response['Stacks'][0]['StackStatus'] == "DELETE_IN_PROGRESS":
                print('{0} already being deleted'.format(stack_name))
                return

            for t in (stk_response['Stacks'][0]['Tags']):
                if t['Key'] == "cfnctl_param_file":
                    f_path = os.path.join(self.cfn_param_file_dir, t['Value'])
                    if os.path.isfile(f_path):

                        if no_prompt:
                            try:
                                os.remove(f_path)
                                print('Removed parameters file {0}'.format(f_path))
                            except Exception as e:
                                raise ValueError(e)
                        else:
                            cli_val = input('Parameters file "{0}" exists, delete also? [y/N] '.format(f_path))

                            if not cli_val:
                                cli_val = 'n'

                            if cli_val.lower().startswith("y"):
                                try:
                                    os.remove(f_path)
                                    print('Removed parameters file {0}'.format(f_path))
                                except Exception as e:
                                    raise ValueError(e)
                            else:
                                pass
        except ClientError as e:
            raise ValueError(e)

        print('Deleting {}'.format(stack_name))
        try:
            response = self.client_cfn.delete_stack(StackName=stack_name)
        except Exception as e:
            raise ValueError(e)

        sc = response['ResponseMetadata']['HTTPStatusCode']

        if sc != 200:
            errmsg = 'Problem deleting stack, status code {}'.format(sc)
            raise ValueError(errmsg)

        return

    def ls_stacks(self, stack_name=None, show_deleted=False):
        """
        Using paginator for getting stack info, as the client.list_stack() will not get older stacks (>6 months)
        :param stack_name:  stack_name
        :param show_deleted:  Should we show deleted stacks also, StackStatus == DELETE_COMPLETE
        :return: dictionary of stacks, formatting needs to happen after the return

        """

        all_stacks = list()

        paginator = self.client_cfn.get_paginator('list_stacks')
        response_iterator = paginator.paginate()

        stacks = dict()
        show_stack = False

        for page in response_iterator:
            all_stacks = page['StackSummaries']
            for r in all_stacks:

                if [r['StackName']] == stack_name:
                    show_stack = True
                elif show_deleted and r['StackStatus'] == "DELETE_COMPLETE":
                    show_stack = True
                elif r['StackStatus'] == "DELETE_COMPLETE":
                    show_stack = False
                else:
                    show_stack = True

                if show_stack:
                    try:
                        stacks[r['StackName']] = [str(r['CreationTime']), r['StackStatus'], r['TemplateDescription']]
                    except Exception as e:
                        stacks[r['StackName']] = [str(r['CreationTime']), r['StackStatus'], "No Description"]

        return stacks

    def create_net_dev(self, subnet_id_n, desc, sg):
        """
        Creates a network device, returns the id
        :return: network device id
        """

        response = self.client_ec2.create_network_interface(SubnetId=subnet_id_n, Description=desc, Groups=[sg])

        return response['NetworkInterface']['NetworkInterfaceId']

    def attach_new_dev(self, i_id, dev_num, subnet_id, desc, sg):

        net_dev_to_attach = (self.create_net_dev(subnet_id, desc, sg))

        response = self.client_ec2.attach_network_interface(
            DeviceIndex=dev_num,
            InstanceId=i_id,
            NetworkInterfaceId=net_dev_to_attach
        )

        return response['AttachmentId']

    def add_net_dev(self):

        print("Adding network interfaces")
        attach_resp = None

        for i in self.instances:

            instance = self.ec2.Instance(i)

            num_interfaces_b = (len(instance.network_interfaces))
            num_interfaces = num_interfaces_b

            num_int_count = 0

            while num_interfaces < int(self.cfn_param_file_values['TotalNetInterfaces']):
                attach_resp = self.attach_new_dev(i,
                                                  num_interfaces_b + num_int_count,
                                                  self.cfn_param_file_values['Subnet'],
                                                  self.stack_name + "-net_dev",
                                                  self.cfn_param_file_values['SecurityGroups']
                                                  )

                instance = self.ec2.Instance(i)

                num_interfaces = (len(instance.network_interfaces))
                num_int_count += 1

            print(" {0} {1} {2}".format(instance.id, num_interfaces_b, num_interfaces))
            time.sleep(10)

        return attach_resp

    def get_stack_events(self, stack_name):

        try:
            paginator = self.client_cfn.get_paginator('describe_stack_events')
            pages = paginator.paginate(StackName=stack_name, PaginationConfig={'MaxItems': 100})
            return next(iter(pages))["StackEvents"]
        except Exception as e:
            raise ValueError(e)

    def stack_status(self, stack_name=None):

        if stack_name is None:
            stack_name = self.stack_name

        all_events = list()
        events = True

        stack_return_list = [
            'CREATE_COMPLETE',
            'ROLLBACK_COMPLETE',
            'CREATE_FAILED'
        ]

        while events:
            stk_status = self.get_stack_events(stack_name)

            for s in reversed(stk_status):
                event_id = s['EventId']
                if event_id not in all_events:
                    all_events.append(event_id)
                    try:
                        print('{0:<38} :  {1:<25} :  {2}'.format(s['LogicalResourceId'], s['ResourceStatus'], s['ResourceStatusReason']))
                    except KeyError:
                        print('{0:<38} :  {1:<25}'.format(s['LogicalResourceId'], s['ResourceStatus']))
                    except Exception as e:
                        raise ValueError(e)

                if s['LogicalResourceId'] == stack_name and s['ResourceStatus'] in stack_return_list:
                    events = False
                    return s['ResourceStatus']
            time.sleep(1)

    def has_elastic_ip(self, inst_arg=None):

        if not self.instances and inst_arg is None:
            print("Instance list is null, exiting")
            return

        if inst_arg is not None:
            self.instances = inst_arg

        for i in self.instances:
            response = self.client_ec2.describe_instances(InstanceIds=[i], DryRun=False)
            for r in response['Reservations']:
                for s in (r['Instances']):
                    for interface in s['NetworkInterfaces']:
                        response = self.client_ec2.describe_network_interfaces(
                            NetworkInterfaceIds=[interface['NetworkInterfaceId']],
                            DryRun=False)

                        for r_net in response['NetworkInterfaces']:
                            try:
                                if r_net['Association'].get('AllocationId'):
                                    return r_net['Association'].get('PublicIp')
                            except KeyError:
                                pass

    def get_netdev0_id(self, instance=None):

        if instance is None:
            print("Must specify one instance")
            return

        response = self.client_ec2.describe_instances(InstanceIds=[instance], DryRun=False)
        for r in response['Reservations']:
            for s in (r['Instances']):
                for interface in s['NetworkInterfaces']:
                    if interface['Attachment']['DeviceIndex'] == 0:
                        return interface['NetworkInterfaceId']

    def set_elastic_ip(self, instances=None, stack_eip=None):

        launch_time = dict()

        if instances is None:
            instances = self.instances

        has_eip = self.has_elastic_ip(instances)
        if has_eip:
            print('Elastic IP already allocated: ' + has_eip)
            return has_eip
        else:
            response = self.client_ec2.describe_instances(InstanceIds=instances, DryRun=False)
            for r in response['Reservations']:
                for resp_i in (r['Instances']):
                    i = resp_i['InstanceId']
                    time_tuple = (resp_i['LaunchTime'].timetuple())
                    launch_time_secs = time.mktime(time_tuple)
                    launch_time[i] = launch_time_secs

        launch_time_list = sorted(launch_time.items(), key=operator.itemgetter(1))
        inst_to_alloc_eip = launch_time_list[1][0]

        netdev0 = self.get_netdev0_id(inst_to_alloc_eip)

        if not netdev0:
            print("Couldn't get first device")
            return

        try:
            if stack_eip is not None:
                allocation_id = self.get_net_alloc_id(stack_eip)
                ip_addr = stack_eip
            else:
                allocation = self.client_ec2.allocate_address(Domain='vpc')
                allocation_id = allocation['AllocationId']
                ip_addr = allocation['PublicIp']

            response = self.client_ec2.associate_address(
                AllocationId=allocation_id,
                NetworkInterfaceId=netdev0
            )

            print('{0} now has Elastic IP address {1}'.format(inst_to_alloc_eip, ip_addr))
            return ip_addr

        except ClientError as e:
            print(e)

        return response

    def get_stack_output(self, stack_name=None):

        if stack_name is None:
            stack_name = self.stack_name

        stk_response = None

        try:
            stk_response = self.client_cfn.describe_stacks(StackName=stack_name)
        except ClientError as e:
            print(e)

        stk_output = dict()

        #for i in stk_response['Stacks']:
        #    try:
        #        for r in i['Outputs']:
        #            stk_output[r['OutputKey']] = r['OutputValue']
        #    except KeyError:
        #        print("No Outputs found")

        return stk_output

    def get_net_alloc_id(self, ip=None):

        if ip is None:
            print("Must specify an IP address")
            return

        response = self.client_ec2.describe_addresses(PublicIps=[ip], DryRun=False)
        for r in response['Addresses']:
            return r['AllocationId']

    def get_stack_info(self, stack_name=None):

        if stack_name is None:
            stack_name = self.stack_name

        stack_status = self.ls_stacks(stack_name=stack_name)
        for stack, i in sorted(stack_status.items()):
            if stack == stack_name:
                print("\nStatus:")
                print('{0:<40.38} {1:<21.19} {2:<30.28} {3:<.30}'.format(stack, str(i[0]), i[1], i[2]))
                print("")

        response = self.client_cfn.describe_stacks(StackName=stack_name)

        for i in response['Stacks']:

            print('[Parameters]')
            try:
                for p in i['Parameters']:
                    print('{0:<38} = {1:<30}'.format(p['ParameterKey'], p['ParameterValue']))
            except Exception as e:
                print("No Parameters found")
                raise ValueError(e)

            print("")

            print('[Outputs]')
            try:
                for o in i['Outputs']:
                    print('{0:<38} = {1:<30}'.format(o['OutputKey'], o['OutputValue']))
            except Exception as e:
                print("No Outputs found")
                #print(ValueError(e))

        print("")
        return

    @staticmethod
    def get_bucket_and_key_from_url(url):

        path = urlparse.urlparse(url).path

        path_l = path.split('/')

        bucket = path_l[1]
        key = '/'.join(path_l[2:])

        return bucket, key

    def get_cfn_param_file(self, template=None):

        self.cfn_param_file_basename = os.path.basename(template)
        self.cfn_param_file = os.path.join(self.cfn_param_file_dir, self.cfn_param_file_basename)

        return self.cfn_param_file

    def rm_cfn_param_file(self, cfn_param_file=None):

        if cfn_param_file is None:
            cfn_param_file = self.cfn_param_file

        print('Removing incomplete parameters file {0}'.format(cfn_param_file))

        if os.path.exists(cfn_param_file):
            os.remove(cfn_param_file)
            return
        else:
            print('File does not exists: {0}'.format(cfn_param_file))
            sys.exit()

        sys.exit(1)

    def set_vpc_cfn_param_file(self, cfn_param_file='NULL', json_content=None, p=None ):

        print(self.vpc_variable_name)

        if cfn_param_file == 'NULL':
            cfn_param_file = self.cfn_param_file

        print('Getting VPC info...')

        all_vpcs = self.get_vpcs()

        vpc_ids = list()
        for vpc_k, vpc_values in all_vpcs.items():
            vpc_ids.append(vpc_k)

        #print(vpc_ids)

        for vpc_id, vpc_info in all_vpcs.items():
            try:
                print('  {0} | {1} | {2} | {3}'.format(vpc_id, vpc_info['CidrBlock'], vpc_info['IsDefault'],
                                                       vpc_info['Tag_Name']))
            except:
                print('  {0} | {1} | {2}'.format(vpc_id, vpc_info['CidrBlock'], vpc_info['IsDefault']))

        prompt_msg = "Select VPC"
        cli_val = self.get_cli_value(json_content, self.vpc_variable_name, prompt_msg)

        if cli_val not in vpc_ids:
            print("Valid VPC required.  Exiting... ")
            self.rm_cfn_param_file(cfn_param_file)
            return

        self.vpc_id = cli_val

        return self.vpc_id


    def get_cli_value(self, json_content, p, prompt_msg):

        cli_val = ""
        default_val = ""
        try:
            default_val = json_content['Parameters'][p]['Default']
        except KeyError:
            pass

        if default_val == "":
            cli_val = input('{0}: '.format(prompt_msg))
        else:
            cli_val = input('{0} [{1}]: '.format(prompt_msg, default_val))

        if cli_val == "":
            cli_val = default_val

        cli_val = cli_val.strip()
        return cli_val


    def build_cfn_param(self, stack_name, template, cli_template=None, verbose=False):

        command_line_template = cli_template
        template_url = None
        template_body = None

        value_already_set = list()
        cfn_param_file_to_write = dict()
        cfn_param_file = self.get_cfn_param_file(template + "." + stack_name)
        cfn_param_file_default = self.get_cfn_param_file(template + ".default")
        found_required_val = False

        if os.path.isfile(cfn_param_file_default):
            cli_val = input("Default parameters file {0} exists, use this file [Y/n]:  ".format(cfn_param_file_default))

            if not cli_val:
                cli_val = 'y'

            if cli_val.lower().startswith("n"):
                try:
                    if os.path.isfile(cfn_param_file):
                        if not os.path.isfile(cfn_param_file_default):
                            cli_val = input("Parameters (not default) file {0} already exists, use this file [y/N]:  ".format(cfn_param_file))

                        if not cli_val:
                            cli_val = 'n'

                        if cli_val.lower().startswith("n"):
                            try:
                                os.remove(cfn_param_file)
                                self.cfn_param_file = cfn_param_file
                            except Exception as e:
                                raise ValueError(e)
                        else:
                            # params file already built, nothing left to do here
                            return cfn_param_file
                    else:
                        print('Stack parameter file does not exists, continuing...')
                        self.cfn_param_file = cfn_param_file
                except Exception as e:
                    raise(ValueError(e))
            else:
                # Using the already build .default params file, nothing left to do here
                return cfn_param_file_default

        self.cfn_param_file = cfn_param_file

        if not os.path.isfile(cfn_param_file):
            # create parameters file and dir
            print("Creating parameters file {0}".format(cfn_param_file))
            if not os.path.isdir(self.cfn_param_file_dir):
                print("Creating parameters directory {0}".format(self.cfn_param_file_dir))
                try:
                    os.makedirs(self.cfn_param_file_dir)
                except OSError as e:
                    if e.errno != errno.EEXIST:
                        raise
        elif os.path.isfile(cfn_param_file):
            cli_val = input("Parameters file {0} already exists, use this file [y/N]:  ".format(cfn_param_file))

            if not cli_val:
                cli_val = 'n'

            if cli_val.lower().startswith("n"):
                try:
                    os.remove(cfn_param_file)
                    self.cfn_param_file = cfn_param_file
                except Exception as e:
                    raise ValueError(e)
            else:
                # params file already build, nothing left to do here
                return cfn_param_file

        if self.url_check(template):
            template_url = template

            (bucket, key) = self.get_bucket_and_key_from_url(template_url)
            s3_object = self.s3.Object(bucket, key)
            try:
                template_content = s3_object.get()['Body'].read().decode('utf-8')
            except ClientError as e:
                if e.response['Error']['Code'] == 'AccessDenied':
                    errmsg = "\nAccess Denied: Are you using the correct CFN template and region for the CFN template?"
                    raise ValueError(e[0] + errmsg)
                elif e.response['Error']['Code'] == 'NoSuchKey':
                    errmsg = "\nCan't find {0} in bucket {1}".format(key, bucket)
                    raise ValueError(e[0] + errmsg)
                raise ValueError(e)
        else:
            template_path = os.path.abspath(template)
            template_body = template_path
            template_content = self.parse_cfn_template(template)

        json_content = ""
        try:
            json_content = json.loads(template_content)
        except json.decoder.JSONDecodeError:
            try:
                json_content = yaml.safe_load(template_content)
            except Exception as e:
                print(e)
                print("Couldn't convert file {0} to JSON format".format(command_line_template))
                print(" -> The template has be in either JSON or YAML format")
                sys.exit()

        if json_content == "":
            print("Template file is blank, exiting...")
            sys.exit()

        for p in sorted(json_content['Parameters']):
            if json_content['Parameters'][p]['Type'] == 'AWS::EC2::VPC::Id':
                self.vpc_variable_name=p

        for p in sorted(json_content['Parameters']):

            default_val = None
            cli_val = None
            param_type = None

            # Debug
            #print('setting {0}'.format(p))

            # get and set AWS::EC2::KeyPair::KeyName
            try:
                if json_content['Parameters'][p]['Type'] == 'AWS::EC2::KeyPair::KeyName':
                    if not self.key_pairs:
                        print('No EC2 keys found in {0}'.format(self.region))
                        self.rm_cfn_param_file(cfn_param_file)
                        return
                    print('EC2 keys found in {0}:'.format(self.region))
                    #print('  {0}'.format(', '.join(self.key_pairs)))
                    for k in self.key_pairs:
                        print('  {0}'.format(k))

                    prompt_msg = "Select EC2 Key"
                    cli_val = self.get_cli_value(json_content, p, prompt_msg)

                    if cli_val not in self.key_pairs:
                        print("Valid EC2 Key Pair required.  Exiting... ")
                        self.rm_cfn_param_file(cfn_param_file)
                        sys.exit()
            except Exception as e:
                print(e)

            # get and set AWS::EC2::VPC::Id

            try:
                if json_content['Parameters'][p]['Type'] == 'AWS::EC2::VPC::Id':
                    if self.vpc_id is None:
                        self.vpc_id = self.set_vpc_cfn_param_file(cfn_param_file,json_content=json_content,p=p)
                        cfn_param_file_to_write[p] = self.vpc_id
                        value_already_set.append(p)
                    else:
                        cfn_param_file_to_write[p] = self.vpc_id
                        value_already_set.append(p)

            except Exception as e:
                print(e)

            # get and set List<AWS::EC2::Subnet::Id>
            try:
                if json_content['Parameters'][p]['Type'] == 'List<AWS::EC2::Subnet::Id>' or \
                                json_content['Parameters'][p]['Type'] == 'AWS::EC2::Subnet::Id':

                    if self.vpc_id is None:
                        try:
                            self.vpc_id = self.set_vpc_cfn_param_file(cfn_param_file,json_content=json_content,p=p)
                        except Exception as e:
                            raise ValueError(e)

                    print('Getting subnets for {0} ...'.format(self.vpc_id))

                    subnet_ids = list()
                    all_subnets = self.get_subnets_from_vpc(self.vpc_id)
                    for subnet_id, subnet_info in all_subnets.items():
                        subnet_ids.append(subnet_id)
                        try:
                            print('  {0} | {1} | {2}'.format(subnet_id, subnet_info['AvailabilityZone'],
                                                             subnet_info['Tag_Name'][0:20]))
                        except KeyError:
                            print('  {0} | {1}'.format(subnet_id, subnet_info['AvailabilityZone']))

                    prompt_msg = "Select subnet:"
                    cli_val = self.get_cli_value(json_content, p, prompt_msg)

                    if cli_val not in subnet_ids:
                        print("Valid subnet ID required.  Exiting... ")
                        self.rm_cfn_param_file(cfn_param_file)
                        return
            except Exception as e:
                pass

            # get and set AWS::EC2::SecurityGroup::Id
            try:
                if json_content['Parameters'][p]['Type'] == 'AWS::EC2::SecurityGroup::Id':

                    if self.vpc_id is None:
                        try:
                            self.vpc_id = self.set_vpc_cfn_param_file(cfn_param_file,json_content=json_content,p=p)
                        except Exception as e:
                            raise ValueError(e)

                    print('Getting security groups for {0} ...'.format(self.vpc_id))

                    security_group_ids = list()
                    all_security_group_info = self.get_security_groups(self.vpc_id)

                    for r in all_security_group_info:
                        security_group_ids.append(r['GroupId'])
                        print('  {0} | {1}'.format(r['GroupId'], r['GroupName'][0:20]))
                    prompt_msg = "Select secuirty group"
                    cli_val = self.get_cli_value(json_content, p, prompt_msg)
                    if cli_val not in security_group_ids:
                        print("Valid security group required.  Exiting... ")
                        self.rm_cfn_param_file(cfn_param_file)
            except Exception as e:
                print(e)

            try:
                default_val = json_content['Parameters'][p]['Default']
            except KeyError:
                pass

            try:
                param_type = json_content['Parameters'][p]['Type']
            except KeyError:
                pass

            if cli_val is None and p not in value_already_set:
                try:
                    if default_val is None:
                        default_val = ""

                    if verbose:
                        print
                        print('# Parameter: {}'.format(p))

                        try:
                            print('# Description: {0}'.format(json_content['Parameters'][p]['Description']))
                        except KeyError:
                            pass

                        try:
                            print('# Type: {0}'.format(json_content['Parameters'][p]['Type']))
                        except KeyError:
                            pass

                        print('# Default: {0}'.format(default_val))

                        try:
                            print('# ConstraintDescription: {0}'.format(json_content['Parameters'][p]['ConstraintDescription']))
                        except KeyError:
                            pass

                        try:
                            space = 16 * " "
                            a_val = ' '.join((json_content['Parameters'][p]['AllowedValues']))
                            a_val_formatted = textwrap.wrap(a_val, width=80, replace_whitespace=False)
                            a_val_formatted_0 = a_val_formatted[0]
                            a_val_formatted_1 = '\n#{0}'.join(a_val_formatted[1:]).format(space)

                            print('# AllowedValues: {0}\n#{1}{2}'.format(a_val_formatted_0, space, a_val_formatted_1))

                        except KeyError:
                            pass

                    cli_val = input('{0} [{1}]: '.format(p, default_val))

                    if cli_val == "":
                        cli_val = default_val

                except Exception as e:
                    print(e)

            try:
                if cli_val is None and default_val is None and json_content['Parameters'][p]['ConstraintDescription']:
                    print('Parameter "{0}" is required, but can be changed in the cfnctl parameters file'.format(p))
                    cli_val = input('Enter {0}: '.format(p))
                    if cli_val == "":
                        cli_val = "<VALUE_NEEDED>"
                        found_required_val = True
            except:
                pass

            try:
                if p not in value_already_set:
                    if cli_val is not None:
                        cfn_param_file_to_write[p] = cli_val
                        value_already_set.append(p)
                    elif default_val is not None:
                        cfn_param_file_to_write[p] = default_val
                        value_already_set.append(p)
                    else:
                        cfn_param_file_to_write[p] = ""
                        value_already_set.append(p)
            except KeyError:
                pass

        if found_required_val:
            print('Some values are still needed, replace "<VALUE_NEEDED>" in {0}'.format(cfn_param_file))

        # Debug
        # print (sorted(cfn_param_file_to_write.items()))
        with open(self.cfn_param_file, 'w') as cfn_out_file:

            cfn_out_file.write('[AWS-Config]\n')
            if template_url is not None:
                cfn_out_file.write('{0} = {1}\n'.format('TemplateURL', template_url))
            elif template_body is not None:
                cfn_out_file.write('{0} = {1}\n'.format('TemplateBody', template_body))
            cfn_out_file.write('\n')

            cfn_out_file.write('[Paramters]\n')

            for k, v in sorted(cfn_param_file_to_write.items()):
                cfn_out_file.write('{0:<35} = {1}\n'.format(k, v))

        print("Done building cfnctl parameters file {0}, includes template location".format(cfn_param_file))

        return cfn_param_file

    def get_instance_info(self, instance_state=None):

        # returns a dictionary

        #  Instance state can be:  pending | running | shutting-down | terminated | stopping | stopped

        instance_states = ['pending',
                           'running',
                           'shutting-down',
                           'terminated',
                           'stopping',
                           'stopped'
                           ]

        if instance_state is not None and instance_state not in instance_states:
            errmsg = 'Instance state "{0}" not valid. ' \
                     'Choose "pending | running | shutting-down | terminated | stopping | stopped"'.format(instance_state)
            raise ValueError(errmsg)

        if instance_state is None:
            instances = self.ec2.instances.all()
        else:
            instances = self.ec2.instances.filter(Filters=[{
                'Name': 'instance-state-name',
                'Values': [instance_state]}]
            )

        inst_info = dict()
        for i in instances:
            tag_name = 'NULL'
            try:
                for tag in i.tags:
                    if tag['Key'] == 'Name':
                        tag_name = tag['Value']
            except:
                pass
            inst_info[i.id] = {
                'TAG::Name': tag_name,
                'Type': i.instance_type,
                'State': i.state['Name'],
                'Private IP': i.private_ip_address,
                'Private DNS': i.private_dns_name,
                'Public IP': i.public_ip_address,
                'Launch Time': i.launch_time
            }

        return inst_info  # returns a dictionary

    def get_vpcs(self):

        response = self.client_ec2.describe_vpcs()

        vpc_keys_all = [
            'Tag_Name',
            'VpcId',
            'InstanceTenancy',
            'Tags',
            'State',
            'DhcpOptionsId',
            'CidrBlock',
            'IsDefault'
        ]

        all_vpcs = dict()

        for v in response['Vpcs']:
            all_vpcs[v['VpcId']] = dict()
            try:
                for t in (v['Tags']):
                    if (t['Key']) == 'Name':
                        all_vpcs[v['VpcId']]['Tag_Name'] = t['Value']
            except KeyError:
                pass

            for vpc_key in self.vpc_keys_to_print:
                try:
                    all_vpcs[v['VpcId']][vpc_key] = v[vpc_key]
                except KeyError:
                    pass

        return all_vpcs

    def get_subnets_from_vpc(self, vpc_to_get):

        subnet_keys_all = ['Tag_Name',
                           'VpcId',
                           'Tags',
                           'AvailableIpAddressCount',
                           'MapPublicIpOnLaunch',
                           'DefaultForAz',
                           'Ipv6CidrBlockAssociationSet',
                           'State',
                           'AvailabilityZone',
                           'SubnetId',
                           'CidrBlock',
                           'AssignIpv6AddressOnCreation'
                           ]

        response = self.client_ec2.describe_subnets(Filters=[{'Name': 'vpc-id', 'Values': [vpc_to_get]}])

        all_subnets = dict()

        for r in response['Subnets']:
            all_subnets[r['SubnetId']] = dict()
            try:
                for t in (r['Tags']):
                    if (t['Key']) == 'Name':
                        all_subnets[r['SubnetId']]['Tag_Name'] = t['Value']
            except KeyError:
                pass

            for sn_key in subnet_keys_all:
                try:
                    all_subnets[r['SubnetId']][sn_key] = r[sn_key]
                except KeyError:
                    pass

        return all_subnets

    def get_security_groups(self, vpc=None):

        sec_groups_all_keys = [
            'IpPermissionsEgress',
            'Description',
            'GroupName',
            'VpcId',
            'OwnerId',
            'GroupId',
        ]

        if vpc is None:
            try:
                response = self.client_ec2.describe_security_groups()
            except Exception as e:
                raise ValueError(e)
        else:
            try:
                response = self.client_ec2.describe_security_groups( Filters=[{'Name': 'vpc-id', 'Values': [vpc]}] )
            except Exception as e:
                raise ValueError(e)

        return response['SecurityGroups']

    def validate_cfn_template(self, template_url=None, template_body=None):

        response = None

        if template_url is not None and template_body is not None:
            errmsg = "Specify either TemplateURL or TemplateBody, not both"
            raise ValueError(errmsg)

        if template_url is not None:
            try:
                response = self.client_cfn.validate_template(TemplateURL=template_url)
            except Exception as e:
                raise ValueError("validate_cfn_template: " + e[0])
        elif template_body is not None:
            try:
                template_body = self.parse_cfn_template(template_body)
                response = self.client_cfn.validate_template(TemplateBody=template_body)
            except Exception as e:
                errmsg = e[0]
                if "Member must have length less than or equal to 51200" in e[0]:
                    errmsg = " Member must have length less than or equal to 51200"
                raise ValueError(errmsg)

        return

    def parse_cfn_template(self, template=None):

        if template is None:
            template = self.template

        with open(template) as file:
            template_obj = file.read()

        return template_obj

    def upload_to_bucket(self, filename, bucket, key):
        """

        :param bucket:  bucket name
        :param filename:  file to upload
        :return:  bucket URL
        """
        key = filename
        filename_path = os.path.abspath(filename)

        try:
            response = self.client_s3.upload_file(filename_path, bucket, key)
        except Exception as e:
            raise ValueError(e)

        url = '{}/{}/{}'.format(self.client_s3.meta.endpoint_url, bucket, key)

        return url

    def setup(self):
        pass

    def teardown(self):
        pass
