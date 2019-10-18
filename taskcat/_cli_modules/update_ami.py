import logging
import os
from taskcat._config import Config
from taskcat._client_factory import Boto3Cache
from taskcat._amiupdater import AMIUpdater
from taskcat._dataclasses import RegionObj
from taskcat.exceptions import TaskCatException
from dulwich.config import ConfigFile, parse_submodules
from pathlib import Path

LOG = logging.getLogger(__name__)


class UpdateAMI:
    """
    Updates AMI IDs within CloudFormation templates
    """

    CLINAME = "update-ami"


    def __init__(self, project_root: str = "./"):
        """
        :param input_file: path to project config or CloudFormation template
        :param project_root: base path for project
        """

        if project_root == "./":
            project_root = Path(os.getcwd())
        else:
            project_root = Path(project_root)

        config_obj_args = {
                'project_config_path': Path(project_root/'.taskcat.yml')
        }

        c = Config.create(**config_obj_args)
        _boto3cache = Boto3Cache()

        # Stripping out any test-specific regions/auth.
        config_dict = c.config.to_dict()
        for test_name, test_config in config_dict['tests'].items():
            if test_config.get('auth', None):
                del test_config['auth']
            if test_config.get('regions', None):
                del test_config['regions']
        new_config = Config.create(**config_obj_args, args=config_dict)

        # Fetching the region objects.
        regions = new_config.get_regions(boto3_cache=_boto3cache)
        rk = list(regions.keys())[0]
        regions = reconcile_all_regions(regions[rk])

        # Fetching the template objects.
        _template_dict = {}
        _templates = new_config.get_templates(
                project_root=Path(project_root),
                boto3_cache=_boto3cache)

        ## one template object per path.
        for _template in _templates.values():
            _template_dict[_template.template_path] = _template
            for _template_descendent in _template.descendents:
                _template_dict[_template_descendent.template_path] = _template_descendent

        # Removing those within a submodule.
        submodule_path_prefixes = []
        gitmodule_config = ConfigFile.from_path(Path(project_root/'.gitmodules'))

        for submodule_path, _, _ in parse_submodules(gitmodule_config):
            submodule_path_prefixes.append(Path(project_root/submodule_path.decode('utf-8')))

        finalized_templates = []
        for template_obj in _template_dict.values():
            gitmodule_template = False
            for gm_path in submodule_path_prefixes:
                if gm_path in template_obj.template_path.parents:
                    gitmodule_template = True
            if not gitmodule_template:
                finalized_templates.append(template_obj)

        amiupdater = AMIUpdater(template_list=finalized_templates, regions=regions)
        amiupdater.update_amis()


    def reconcile_all_regions(self, test_regions, boto3_cache, profile='default'):
        ec2_client = boto3_cache.client('ec2', region='us-east-1', profile=profile)
        region_result = ec2_client.describe_regions()
        taskcat_id = test_regions[0].taskcat_id

        all_region_names = [x['RegionName'] for x in region_result['Regions']]
        existing_region_names = [x.name for x in test_regions]
        region_name_delta = [x for in all_region_names if x not in existing_region_names]
        
        for region_name_to_add in region_name_delta:
            region_object = RegionObj(
                name=region_name,
                account_id=boto3_cache.account_id(profile),
                partition=boto3_cache.partition(profile),
                profile=profile,
                _boto3_cache=boto3_cache,
                taskcat_id=taskcat_id
            )
            test_regions.append(region_object)
        return test_regions
