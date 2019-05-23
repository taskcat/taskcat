import datetime
import textwrap
import tabulate
import logging

from taskcat.logger import PrintMsg
from taskcat.cfn.threaded import ThreadedStack
from taskcat.common_utils import region_from_stack_id, name_from_stack_id

log = logging.getLogger(__name__)


class CfnLogTools:
    def __init__(self, project_name, boto_client, testdata_list):
        self._boto_client = boto_client
        cfn = ThreadedStack(project_name)
        self.stack_ids = []
        for test_stacks in [test.get_test_stacks() for test in testdata_list]:
            self.stack_ids += [stack['StackId'] for stack in test_stacks]
        self.events = cfn.describe_stacks_events(self.stack_ids)
        self.resources = cfn.list_stacks_resources(self.stack_ids)
        self.stack_statuses = cfn.stacks_status(self.stack_ids)

    @staticmethod
    def _format_events(raw_events):
        """
        This function returns a sub set of event keys for display in a report
        :param raw_events: events from the cfn api
        :return: Event logs of the stack
        """

        events = []
        for event in raw_events:
            event_details = {
                'TimeStamp': event['Timestamp'],
                'ResourceStatus': event['ResourceStatus'],
                'ResourceType': event['ResourceType'],
                'LogicalResourceId': event['LogicalResourceId'],
                'ResourceStatusReason': ''
            }
            if 'ResourceStatusReason' in event:
                event_details['ResourceStatusReason'] = event['ResourceStatusReason']
            events.append(event_details)
        return events

    # V8SHIM
    def createcfnlogs(self, logpath):
        """
        This function creates the CloudFormation log files.

        :param logpath: Log file path
        :return:
        """
        log.info("Collecting CloudFormation Logs")

        for stack_id in self.stack_ids:
            extension = '.txt'
            test_logpath = '{}/{}-{}-{}{}'.format(logpath, name_from_stack_id(stack_id), region_from_stack_id(stack_id),
                                                  'cfnlogs', extension)
            self.write_logs(stack_id, test_logpath)

    def write_logs(self, stack_id, logpath):
        """
        This function writes the event logs of the given stack and all the child stacks to a given file.
        :param stack_id: Stack Id
        :param logpath: Log file path
        :return:
        """

        if stack_id in self.stack_statuses['COMPLETE']:
            reason = "Stack launch was successful"
        else:
            reasons = []
            for event in self._format_events(self.events[stack_id]):
                if event['ResourceStatus'] == 'CREATE_FAILED' and \
                        event['ResourceStatusReason'] != 'Resource creation cancelled' and \
                        not event['ResourceStatusReason'].startswith('The following resource(s) failed to create: '):
                    reasons.append('[{}] {}'.format(event['LogicalResourceId'], event['ResourceStatusReason']))
            reason = '\n'.join(reasons)
        msg = "StackName: %s \n" % name_from_stack_id(stack_id)
        msg += "\t |Region: %s\n" % region_from_stack_id(stack_id)
        msg += "\t |Logging to: %s\n" % logpath
        msg += "\t |Tested on: %s\n" % str(datetime.datetime.now().strftime("%A, %d. %B %Y %I:%M%p"))
        msg += "------------------------------------------------------------------------------------------\n"
        msg += "ResourceStatusReason: \n"
        msg += textwrap.fill(str(reason), 85) + "\n"
        msg += "==========================================================================================\n"
        if reason == "Stack launch was successful":
            log.info(msg, extra={"nametag": PrintMsg.PASS})
        else:
            log.error(msg)
        log.warning(" |GENERATING REPORTS{}".format(PrintMsg.header, PrintMsg.rst_color),
                    extra={"nametag": PrintMsg.NAMETAG})
        with open(logpath, "a") as log_output:
            log_output.write("-----------------------------------------------------------------------------\n")
            log_output.write("Region: " + region_from_stack_id(stack_id) + "\n")
            log_output.write("StackName: " + name_from_stack_id(stack_id) + "\n")
            log_output.write("*****************************************************************************\n")
            log_output.write("ResourceStatusReason:  \n")
            log_output.write(textwrap.fill(str(reason), 85) + "\n")
            log_output.write("*****************************************************************************\n")
            log_output.write("*****************************************************************************\n")
            log_output.write("Events:  \n")
            log_output.writelines(tabulate.tabulate(self._format_events(self.events[stack_id]), headers="keys"))
            log_output.write("\n*****************************************************************************\n")
            log_output.write("-----------------------------------------------------------------------------\n")
            log_output.write("Tested on: " + datetime.datetime.now().strftime("%A, %d. %B %Y %I:%M%p") + "\n")
            log_output.write("-----------------------------------------------------------------------------\n\n")
            log_output.close()

        for resource in self.resources[stack_id]:
            if resource['ResourceType'] == 'AWS::CloudFormation::Stack':
                self.write_logs(resource['PhysicalId'], logpath)
