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
from functools import reduce
from multiprocessing.dummy import Pool as ThreadPool

import pkg_resources
import requests
import yaml

from taskcat._client_factory import ClientFactory
from taskcat._common_utils import deep_get

LOG = logging.getLogger(__name__)

class AMIUpdaterException(Exception):
    """Raised when AMIUpdater experiences a fatal error"""\
    pass

def build_codenames(tobj, config):
    """Builds regional codename objects"""

    def _construct_filters(cname):
        formatted_filters = []
        retreived_filters = config.get_filter(cname)
        formatted_filters = [
            {"Name": k, "Values": [v]} for k,v in retrieved_filters.items()
        ]
        formatted_filters.append[{"Name": "state", "Values": ["available"]})
        return formatted_filters

    built_cn = []
    filters = deep_get(tobj.underlying.template, tobj.metadata_path)
    mappings = deep_get(tobj.underlying.template, tobj.mapping_path)

    for cname, cfilters in filters.items()
        config.update({cname: cfilters})

    for region, cndata in mappings.items():
        for cnname in cndata.keys():
            _filters = _construct_filters(cnname)
            region_cn = RegionalCodename(region=region, cn=cnname, filters=_filters)
            built_cn.append(region_cn)
    return built_cn

def query_codenames(codename_list, region_list):
    """Fetches AMI IDs from AWS"""

    if len(codename_list) == 0:
        raise AMIUpdaterException(
            "No AMI filters were found. Nothing to fetch from the EC2 API."
        )

    def _per_codename_amifetch(regional_cn):
        regional_cn.results = region_dict.get(regional_cn.region).client('ec2').describe_images(
                Filters=regional_cn.filters)['Images']

    pool = ThreadPool(len(region_list))
    pool.map(_per_codename_amifetch, codename_list)

def reduce_api_results(codename_list):
    def _image_timestamp(raw_ts):
        ts_int = datetime.datetime.strptime(raw_ts, "%Y-%m-%dT%H:%M:%S.%fZ").timestamp()
        return int(ts_int)

    raw_ami_names = {}
    region_codename_result_list = []
    missing_results_list = []

    # For each RegionalCodename.
    #     Create a Dictionary like so:
    #     CODENAME
    #       - REGION_NAME
    #           [{RAW_API_RESULTS_1}, {RAW_API_RESULTS_2}, {RAW_API_RESULTS_N}]
    for rcn in codename_list:
        objectified_results = [
            APIResultsData(
                rcn.cn,
                x['ImageId'],
                _image_timestamp(x['CreationDate']),
                rcn.region
            ) for x in rcn.results
        ]

        rcn_cn_data = raw_ami_names.get(rcn.cn, None)
        if rcn_cn_data:
            raw_ami_names[rcn.cn][rcn.region] = objectified_results
        else:
            raw_ami_names.update({rcn.cn: {rcn.region: objectified_results}})

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

class Codenames:
    filters = None
    _objs = {}
    _no_filters = {}


    def _create_codename_filters(self):
        # I'm grabbing the filters from the config file, and adding them to
        # self.filters; The RegionalCodename instance can access this value. That's
        # important for threading the API queries - which we do.
        cnfilter = TemplateClass.deep_get(
            Config.raw_dict, "global/AMIs/{}".format(self.cn)
        )
        if self._filters:
            cnfilter = self._filters
        if cnfilter:
        if not self.filters:
            return None
        return True

    @classmethod
    def unknown_mappings(cls):
        return cls._no_filters.keys()


        for codename, regions in raw_ami_names.items():
            for region, results_list in regions.items():
                if len(results_list) == 0:
                    missing_results_list.append((codename, region))
                    continue
                latest_ami = sorted(results_list, reverse=True)[0]
                latest_ami.custom_comparisons = False
                region_codename_result_list.append(latest_ami)
        if missing_results_list:
            for code_reg in missing_results_list:
                LOG.error(
                    f"The following Codename / Region  had no results from the EC2 "
                    f"API. {code_reg}"
                )
            raise AMIUpdaterException(
                "One or more filters returns no results from the EC2 API."
            )
        APIResultsData.results = region_codename_result_list


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
    region = ''
    cn = ''
    new_ami = ''
    filters = []
    _creation_dt = datetime.datetime.now()


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
        _template_regions = deep_get(self.underlying.template, self.mapping_path)
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
        self._template_path = path_to_templates

    def _load_config_file(self):
        """Loads the AMIUpdater Config File"""
        with open(self._user_config_file) as f:
            config_contents = yaml.safe_load(f)
        self.config = config_contents


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
        for template_file in self._fetch_template_files():
            TemplateObject(template_file)

        unknown_mappings = Codenames.unknown_mappings()
        if unknown_mappings:
            LOG.warning(
                "The following mappings are unknown to AMIUpdater. Please investigate"
            )
            for unknown_map in unknown_mappings:
                LOG.warning(unknown_map)

    def update_amis(self):
        templates = []
        regions = []
        codenames = set()
        _regions_with_creds = [r.region_name for r in self.regions]

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
            template_cn = build_codenames(template)
            for tcn in template_cn:
                codenames.add(tcn)

        # Retrieve API Results.
        LOG.info("Retreiving results from the EC2 API")
        results = query_api(codenames)

        LOG.info("Determining the latest AMI for each Codename/Region")
        updated_ami_results = reduce_api_results(results)

        LOG.info("Templates updated as necessary")
        for template in templates:
            for codename in updated_api_results:
                template.set_codename_ami(codename.cn, codename.region, codename.new_ami)
            template.write()

        LOG.info("Complete!")
