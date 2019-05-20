from taskcat import ClientFactory
from taskcat.common_utils import fan_out, group_stacks_by_region, merge_dicts
import uuid
import boto3


class CfnStacker(object):

    NULL_UUID = uuid.UUID(int=0)
    CAPABILITIES = ['CAPABILITY_IAM', 'CAPABILITY_NAMED_IAM', 'CAPABILITY_AUTO_EXPAND']
    STATUSES = {
        "COMPLETE": [
            'CREATE_COMPLETE', 'UPDATE_COMPLETE', 'DELETE_COMPLETE'
        ],
        "IN_PROGRESS": [
            'CREATE_IN_PROGRESS', 'DELETE_IN_PROGRESS', 'UPDATE_IN_PROGRESS', 'UPDATE_COMPLETE_CLEANUP_IN_PROGRESS'
        ],
        "FAILED": [
            'DELETE_FAILED', 'CREATE_FAILED', 'ROLLBACK_IN_PROGRESS', 'ROLLBACK_FAILED', 'ROLLBACK_COMPLETE',
            'UPDATE_ROLLBACK_IN_PROGRESS''UPDATE_ROLLBACK_FAILED', 'UPDATE_ROLLBACK_COMPLETE_CLEANUP_IN_PROGRESS',
            'UPDATE_ROLLBACK_COMPLETE'
        ]
    }

    def __init__(self, project_name: str, uid: uuid.UUID = NULL_UUID, template_urls: list = None, regions: list = None,
                 recurse: bool = True, stack_name_prefix: str = 'tCat', tags: list = None,
                 client_factory_instance=None):
        self.project_name = project_name
        self.recurse = recurse
        self.stack_name_prefix = stack_name_prefix
        self.template_urls = template_urls if template_urls else []
        self.regions = regions if regions else []
        self.tags = tags if tags else []
        self.client_factory = client_factory_instance if client_factory_instance else ClientFactory()
        self.uid = uuid.uuid4() if uid == CfnStacker.NULL_UUID else uid

    def _get_client(self, region):
        if region:
            return self.client_factory.get("cloudformation", region=region)
        else:
            return self.client_factory.get("cloudformation")

    @staticmethod
    def _get_regions():
        return boto3.Session().get_available_regions("cloudformation")

    def validate_templates(self, template_urls: list = None, regions: list = None, recurse: bool = True, threads=8):
        template_urls = template_urls if template_urls else self.template_urls
        regions = regions if regions else self.regions
        recurse = recurse if recurse else self.recurse
        # TODO: implement child template discovery
        results = fan_out(self._validate_templates_across_regions, {"regions": regions}, template_urls, threads)
        failures = []
        for t in results:
            failures += [r for r in t if r]
        return failures

    def _validate_templates_across_regions(self, template_url: str, regions: list, threads: int = 32):
        results = fan_out(self.validate_template, {"template": template_url}, regions, threads)
        return [r for r in results if r]

    def validate_template(self, template, region=None):
        cfn_client = self._get_client(region)
        try:
            cfn_client.validate_template(TemplateURL=template)
        except cfn_client.exceptions.ClientError as e:
            if e.response["Error"]["Code"] == "ValidationError":
                return "{} - {} - {}".format(template, region, e.response["Error"]["Message"])
            raise
        return None

    @staticmethod
    def _tests_dict_to_list(tests: dict):
        test_list = []
        for test_name in tests.keys():
            test = tests[test_name]
            test["Name"] = test_name
            test_list.append(test)
        return test_list

    @staticmethod
    def _tests_list_to_dict(tests: list):
        test_dict = {}
        for test in tests:
            test_name = test["Name"]
            test.pop("Name")
            test_dict[test_name] = test["StackIds"]
        return test_dict

    def create_stacks(self, tests: dict, threads: int = 8):
        tests = self._tests_dict_to_list(tests)
        tags = [{"Key": "taskcat-id", "Value": self.uid.hex}]
        tags += [t for t in self.tags if t["Key"] not in ["taskcat-name", "taskcat-id"]]
        stack_ids = fan_out(self._create_stacks_for_test, {"tags": tags}, tests, threads)
        return self._tests_list_to_dict(stack_ids)

    def _create_stacks_for_test(self, test, tags, threads: int = 32):
        stack_name = "{}-{}-{}-{}".format(self.stack_name_prefix, self.project_name, test["Name"], self.uid.hex)
        tags += [{"Key": "taskcat-name", "Value": test["Name"]}]
        partial_kwargs = {"stack_name": stack_name, "template_url": test["TemplateUrl"],
                          "parameters": test["Parameters"], "tags": tags}
        stack_ids = fan_out(self.create_stack, partial_kwargs, test["Regions"], threads)
        return {"Name": test["Name"], "StackIds": stack_ids}

    def create_stack(self, stack_name: str, template_url: str, parameters: list, tags: list, region=None):
        cfn_client = self._get_client(region=region)
        stack_id = cfn_client.create_stack(
            StackName=stack_name,
            TemplateURL=template_url,
            Parameters=parameters,
            Tags=tags,
            Capabilities=CfnStacker.CAPABILITIES
        )["StackId"]
        return stack_id

    # Not used by tCat at present
    def update_stacks(self, tests: dict):
        raise NotImplementedError()

    def delete_stacks(self, stack_ids: list, deep=False, threads=32):
        if deep:
            raise NotImplementedError("deep delete not yet implemented")
        fan_out(self._delete_stacks_for_region, None, group_stacks_by_region(stack_ids), threads)
        return None

    def _delete_stacks_for_region(self, stacks, threads=8):
        fan_out(self.delete_stack, {"region": stacks["Region"]}, stacks["StackIds"], threads)

    def delete_stack(self, stack_id, region):
        cfn_client = self._get_client(region=region)
        cfn_client.delete_stack(StackName=stack_id)

    def stacks_status(self, stack_ids: list, recurse: bool = False, threads: int = 32):
        if recurse:
            raise NotImplementedError("recurse not implemented")
        results = fan_out(self._stacks_status_for_region, None, group_stacks_by_region(stack_ids), threads)
        statuses = {"IN_PROGRESS": {}, "COMPLETE": {}, "FAILED": {}}
        for region in results:
            for status in region:
                statuses[status[1]][status[0]] = status[2]
        return statuses

    def _stacks_status_for_region(self, stacks, threads: int = 8):
        return fan_out(self.stack_status, {"region": stacks["Region"]}, stacks["StackIds"], threads)

    def stack_status(self, stack_id: str, region: str):
        # TODO: get time to complete for complete stacks and % complete (no of resources in complete state) for
        #       in-progress stacks
        cfn_client = self._get_client(region=region)
        results = cfn_client.describe_stacks(StackName=stack_id)["Stacks"][0]
        status = results["StackStatus"]
        reason = ''
        if "StackStatusReason" in results:
            reason = results["StackStatusReason"]
        for s in CfnStacker.STATUSES.keys():
            if status in CfnStacker.STATUSES[s]:
                return stack_id, s, reason

    def describe_stacks_events(self, stack_ids, recurse=False, threads: int = 32):
        if recurse:
            raise NotImplementedError("recurse not implemented")
        #return Events  # {'arn::cloudformation::blah::StackId/blah': {"Events": CfnEvents, "ChildStacks": {"ChildId": CfnEvents}}
        results = fan_out(self._describe_stack_events_for_region, None, group_stacks_by_region(stack_ids), threads)
        # TODO: format results
        return results

    def _describe_stack_events_for_region(self, stacks, threads: int = 8):
        return fan_out(self.describe_stack_events, {"region": stacks["Region"]}, stacks["StackIds"], threads)

    def describe_stack_events(self, stack_id: str, region: str):
        cfn_client = self._get_client(region=region)
        # TODO: pagination
        return cfn_client.describe_stack_events(StackName=stack_id)["'StackEvents'"]

    def list_stacks_resources(self, stack_ids, status=None, recurse=False, threads: int = 32):
        if recurse:
            raise NotImplementedError("recurse not implemented")
        #return Resources  # {'arn::cloudformation::blah::StackId/blah': {"Events": CfnEvents, "ChildStacks": {"ChildId": CfnResources}}
        results = fan_out(self._list_stack_resources_for_region, {"status": status}, group_stacks_by_region(stack_ids),
                          threads)
        return merge_dicts(results)

    def _list_stack_resources_for_region(self, stacks, status, threads: int = 8):
        kwargs = {"region": stacks["Region"]}
        if status:
            kwargs['status'] = status
        results = fan_out(self.list_stack_resources, kwargs, stacks["StackIds"], threads)
        return merge_dicts(results)

    def list_stack_resources(self, stack_id: str, region: str, status=None):
        cfn_client = self._get_client(region=region)
        resources = []
        for page in cfn_client.get_paginator('list_stack_resources').paginate(StackName=stack_id):
            resources += page["StackResourceSummaries"]
        if status:
            resources = [resource for resource in resources if resource['ResourceStatus'] == status]
        return {stack_id: resources}

    # Return all stacks with instance's uuid
    def get_stackids(self, include_deleted=False, recurse=False, threads=32):
        if recurse:
            raise NotImplementedError("recurse not implemented")
        results = fan_out(self._get_stackids_for_region, None, self._get_regions(), threads)
        stack_ids = {}
        for r in results:
            for s in r:
                if s[1] not in stack_ids.keys():
                    stack_ids[s[1]] = {}
                if s[0] not in stack_ids[s[1]].keys():
                    stack_ids[s[1]][s[0]] = {}
        return stack_ids
        # return StackIds  # {"TestName": {'arn::cloudformation::blah::StackId/blah': {"ChildId": CfnResources}}}

    def _get_stackids_for_region(self, region):
        cfn_client = self._get_client(region=region)
        stack_ids = []
        for p in cfn_client.get_paginator("describe_stacks").paginate():
            for stack in p["Stacks"]:
                match = False
                name = ''
                stack_id = stack["StackId"]
                for tag in stack["Tags"]:
                    if tag["Key"] == 'taskcat-id' and tag["Value"] == self.uid.hex:
                        match = True
                    elif tag["Key"] == "taskcat-name":
                        name = tag["Value"]
                if match and name:
                    stack_ids.append([stack_id, name])
        return stack_ids
