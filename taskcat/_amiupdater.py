# TODO: add type hints
# type: ignore
# TODO: fix lint issues
# pylint: skip-file
import collections
import datetime
import json
import logging
import os
import re
from multiprocessing.dummy import Pool as ThreadPool
from functools import partial

import pkg_resources
import requests
import yaml

from taskcat._common_utils import deep_get
from dataclasses import dataclass, field

LOG = logging.getLogger(__name__)

class AMIUpdaterException(Exception):
    """Raised when AMIUpdater experiences a fatal error"""
    pass

def build_codenames(tobj, config):
    """Builds regional codename objects"""

    def _construct_filters(cname):
        formatted_filters = []
        fetched_filters = config.get_filter(cname)
        formatted_filters = [
            {"Name": k, "Values": [v]} for k,v in fetched_filters.items()
        ]
        if formatted_filters:
            formatted_filters.append({"Name": "state", "Values": ["available"]})
        return formatted_filters

    built_cn = []
    filters = deep_get(tobj.underlying.template, tobj.metadata_path, default=dict())
    mappings = deep_get(tobj.underlying.template, tobj.mapping_path, default=dict())

    for cname, cfilters in filters.items():
        config.update_filters({cname: cfilters})

    for region, cndata in mappings.items():
        if region == 'AMI':
            continue
        for cnname in cndata.keys():
            _filters = _construct_filters(cnname)
            region_cn = RegionalCodename(region=region, cn=cnname, filters=_filters)
            built_cn.append(region_cn)
    return built_cn

def query_codenames(codename_list, region_dict):
    """Fetches AMI IDs from AWS"""

    if len(codename_list) == 0:
        raise AMIUpdaterException(
            "No AMI filters were found. Nothing to fetch from the EC2 API."
        )

    def _per_codename_amifetch(region_dict, regional_cn):
        image_results = region_dict.get(regional_cn.region).client('ec2').describe_images(
                Filters=regional_cn.filters)['Images']
        return {'region': regional_cn.region, "cn": regional_cn.cn, "api_results": image_results}

    pool = ThreadPool(len(region_dict))
    p = partial(_per_codename_amifetch, region_dict)
    response = pool.map(p, codename_list)

def reduce_api_results(raw_results):
    def _image_timestamp(raw_ts):
        ts_int = datetime.datetime.strptime(raw_ts, "%Y-%m-%dT%H:%M:%S.%fZ").timestamp()
        return int(ts_int)

    unsorted_results = []
    sorted_results = []
    final_results = []
    result_state = {}

    for thread_result in raw_results:
        for cn_result in thread_result:
            if cn_result:
                _t = unsorted_results_dict.get(cn_result['region'])
                cn_api_reuslts_data =[ APIResultsData(
                        cn_result['cn'],
                        x['ImageId'],
                        _image_timestamp(x['CreationDate']),
                        cn_result['region']
                    ) for x in cn_result['api_results']
                ]

                unsorted_results = cn_api_results_data + unsorted_results

    sorted_results = unsorted_results.sort()

    for r in sorted_results:
        found_key = f"{r['region']}-{r['cn']}"
        already_found = result_state.get(found_key, False)
        if already_found:
            continue
        result_state[found_key] = True
        final_results.append(r)
    return final_results

class Config:
    raw_dict = {"global": {"AMIs": {}}}
    codenames = set()

    @classmethod
    def load(cls, fn, configtype=None):
        with open(fn, "r") as f:
            try:
                cls.raw_dict = yaml.safe_load(f)
            except yaml.YAMLError as e:
                LOG.error("[{}] - YAML Syntax Error!", fn)
                LOG.error("{}", e)
        try:
            for x in cls.raw_dict.get("global").get("AMIs").keys():
                cls.codenames.add(x)

        except Exception as e:
            LOG.error("{} config file [{}] is not structured properly!", configtype, fn)
            LOG.error("{}", e)
            raise AMIUpdaterException

    @classmethod
    def update_filter(cls, dn):
        cls.raw_dict["global"]["AMIs"].update(dn)

    @classmethod
    def get_filter(cls, dn):
        x = deep_get(cls.raw_dict, f"global/AMIs/{dn}")
        return x

@dataclass
class APIResultsData(object):
    codename = ''
    ami_id = ''
    creation_date = ''
    region = ''
    custom_comparisons=True

    def __lt__(self, other):
        # See Codenames.parse_api_results for notes on why this is here.
        if self.custom_comparisons:
            return self.creation_date < other.creation_date
        else:
            return object.__lt__(self, other)

    def __gt__(self, other):
        # See Codenames.parse_api_results for notes on why this is here.
        if self.custom_comparisons:
            return self.creation_date > other.creation_date
        else:
            return object.__gt__(self, other)


@dataclass
class RegionalCodename:
    region: str
    cn: str
    new_ami: str = field(default_factory=str)
    filters: list = field(default_factory=list)
    _creation_dt = datetime.datetime.now()

    def __hash__(self):
        return hash(self.region+self.cn+ self.new_ami+str(self.filters))

@dataclass
class Template:
    #TODO: Type these
    codenames = set()
    mapping_path = "Mappings/AWSAMIRegionMap"
    metadata_path = "Metadata/AWSAMIRegionMap/Filters"
    region_codename_lineno = {}
    region_names = set()
    underlying: ''

    def configure(self):
        self._configure_region_names()
        self._ls = self.underlying.linesplit

    def set_codename_ami(self, cname, region, new_ami):
        if region not in region_names:
            return
        key = f"{cname}/{region}"
        try:
            line_no = self.regional_codename_lineno[key]['line']
            old_ami = self.regional_codename_lineno[key]['old']
        except KeyError:
            return
        new_record = re.sub(old_ami, ami, self._ls[line_no-1])
        self._ls[line_no-1] = new_record

    def _configure_region_names(self):
        _template_regions = deep_get(self.underlying.template, self.mapping_path, {})
        for region_name, region_data in _template_regions.items():
            if region_name == "AMI":
                continue
            self.region_names.add(region_name)
            for codename, cnvalue in region_data.items():
                key = f"{codename}/{region_name}"
                self.region_codename_lineno[key] = {
                        'line': codename.start_mark.line,
                        'old': cnvalue
                        }

    def write(self):
        self.underlying.raw_template = "\n".join(self._ls)
        self.underlying.write()

class AMIUpdater:
    upstream_config_file = pkg_resources.resource_filename(
        "taskcat", "/cfg/amiupdater.cfg.yml"
    )
    upstream_config_file_url = (
        "https://raw.githubusercontent.com/aws-quickstart/"
        "taskcat/master/cfg/amiupdater.cfg.yml"
    )
    EXCLUDED_REGIONS = [
        "us-gov-east-1",
        "us-gov-west-1",
        "cn-northwest-1",
        "cn-north-1",
    ]

    def __init__(
        self,
        template_list,
        regions,
        user_config_file=None,
        use_upstream_mappings=True,
    ):
        if use_upstream_mappings:
            Config.load(self.upstream_config_file, configtype="Upstream")
        if user_config_file:
            Config.load(user_config_file, configtype="User")
        self.template_list = template_list
        self.regions = regions

    @classmethod
    def check_updated_upstream_mapping_spec(cls):
        # TODO: add v9 compatible logic to check versions
        return False

    @classmethod
    def update_upstream_mapping_spec(cls):
        r = requests.get(cls.upstream_config_file_url)
        if r.ok:
            with open(cls.upstream_config_file) as f:
                f.write(r.content)


    #TODO FIXME
    def list_unknown_mappings(self):
        pass
#        for template_file in self._fetch_template_files():
#            TemplateObject(template_file)
#
#        unknown_mappings = Codenames.unknown_mappings()
#        if unknown_mappings:
#            LOG.warning(
#                "The following mappings are unknown to AMIUpdater. Please investigate"
#            )
#            for unknown_map in unknown_mappings:
#                LOG.warning(unknown_map)
#
    def update_amis(self):
        templates = []
        regions = []
        codenames = set()
        _regions_with_creds = self.regions.keys()

        LOG.info("Determining templates and supported regions")
        # Flush out templates and supported regions
        for tc_template in self.template_list:
            _t = Template(underlying=tc_template)
            _t.configure()
            _new_region_list = []
            for region in _t.region_names:
                if (region in self.EXCLUDED_REGIONS) and (region not in _regions_with_creds):
                    continue
                _new_region_list.append(region)
                _t.region_names = set(_new_region_list)
            templates.append(_t)

        LOG.info("Determining regional search params for each AMI")
        # Flush out codenames.
        for template in templates:
            template_cn = build_codenames(template, Config)
            for tcn in template_cn:
                codenames.add(tcn)

        # Retrieve API Results.
        LOG.info("Retreiving results from the EC2 API")
        results = query_codenames(codenames, self.regions)

        LOG.info("Determining the latest AMI for each Codename/Region")
        updated_ami_results = reduce_api_results(results)

        # Figure out a way to sort dictionary by key-value (timestmap)

        LOG.info("Templates updated as necessary")
        for template in templates:
            for codename in updated_api_results:
                template.set_codename_ami(codename.cn, codename.region, codename.new_ami)
            template.write()

        LOG.info("Complete!")
