import json
import logging
import os
from pathlib import Path
from typing import Dict, Set, List

import yaml
from jsonschema import RefResolver, validate, exceptions

from taskcat.cfn.template import Template
from taskcat.client_factory import ClientFactory
from taskcat.common_utils import absolute_path
from taskcat.exceptions import TaskCatException

LOG = logging.getLogger(__name__)


class Test:  # pylint: disable=too-few-public-methods
    def __init__(
        self,
        template_file: Path,
        parameter_input: Path = None,
        parameters: dict = None,
        regions: set = None,
        project_root: Path = Path("./"),
    ):
        self._project_root: Path = project_root
        self.template_file: Path = self._guess_path(template_file)
        self.parameter_input_file: Path = self._guess_path(parameter_input)
        self.parameters: Dict[
            str, int, bool
        ] = self._params_from_file() if parameter_input else {}
        if parameters:
            self.parameters.update(parameters)
        Config.validate(self.parameters, "overrides")
        self.regions = list(regions) if regions else []

    def _guess_path(self, path):
        abs_path = absolute_path(path)
        if not abs_path:
            abs_path = absolute_path(self._project_root / path)
        if not abs_path:
            abs_path = self._legacy_path_prefix(path)
        if not abs_path:
            raise TaskCatException(
                f"Cannot find {path} with project root" f" {self._project_root}"
            )
        return abs_path

    def _legacy_path_prefix(self, path):
        abs_path = absolute_path(self._project_root / "templates" / path)
        if abs_path:
            LOG.warning(
                "found path with deprecated relative path, support for this will be "
                "removed in future versions, please update %s to templates/%s",
                path,
                path,
            )
            return abs_path
        abs_path = absolute_path(self._project_root / "ci" / path)
        if abs_path:
            LOG.warning(
                "found path with deprecated relative path, support for this will be "
                "removed in future versions, please update %s to ci/%s",
                path,
                path,
            )
        return abs_path

    def _params_from_file(self):
        if not self.parameter_input_file:
            return None
        params = yaml.safe_load(open(str(self.parameter_input_file), "r"))
        self._validate_params(params)
        try:
            Config.validate(params, "legacy_parameters")
            params = self._convert_legacy_params(params)
        except exceptions.ValidationError:
            pass
        return params

    @staticmethod
    def _convert_legacy_params(legacy_params):
        return {p["ParameterKey"]: p["ParameterValue"] for p in legacy_params}

    def _validate_params(self, params):
        try:
            Config.validate(params, "overrides")
        except exceptions.ValidationError as e:
            try:
                Config.validate(params, "legacy_parameters")
                LOG.warning(
                    "%s parameters are in a format that will be deprecated in "
                    "the next version of taskcat",
                    str(self.parameter_input_file),
                )
            except exceptions.ValidationError:
                # raise original exception
                raise e

    @classmethod
    def from_dict(cls, raw_test: dict, project_root=Path("./")):
        return Test(**raw_test, project_root=project_root)


class Config:  # pylint: disable=too-many-instance-attributes,too-few-public-methods
    """
    Config hierarchy (items lower down override items above them):
    global config
    project config
    template config
    ENV vars
    CLI args
    Override file (for parameter overrides)
    """

    DEFAULT_PROJECT_PATHS = [
        "./.taskcat.yml",
        "./.taskcat.yaml",
        "./ci/taskcat.yaml",
        "./ci/taskcat.yml",
    ]

    def __init__(
        self,
        args: dict = None,
        global_config_path: str = "~/.taskcat.yml",
        template_path: str = None,
        project_config_path: str = None,
        project_root: str = "./",
        override_file: str = None,
        all_env_vars: List[dict] = os.environ.items(),
        client_factory_instance: ClientFactory = ClientFactory(),
    ):  # #pylint: disable=too-many-arguments
        # inputs
        if template_path:
            if not Path(template_path).exists():
                raise TaskCatException(
                    f"failed adding config from template file "
                    f"{template_path} file not found"
                )
        self.project_root: [Path, None] = absolute_path(project_root)
        self.args: dict = args if args else {}
        self.global_config_path: [Path, None] = absolute_path(global_config_path)
        self.template_path: [Path, None] = self._absolute_path(template_path)
        self.override_file: Path = self._absolute_path(override_file)

        # general config
        self.boto_profile: str = ""
        self.aws_access_key: str = ""
        self.aws_secret_key: str = ""
        self.no_cleanup: bool = False
        self.no_cleanup_failed: bool = False
        self.public_s3_bucket: bool = False
        self.verbosity: str = "DEBUG"
        self.tags: dict = {}
        self.stack_prefix: str = ""
        self.lint: bool = False
        self.upload_only: bool = False
        self.lambda_build_only: bool = False
        self.exclude: str = ""
        self.enable_sig_v2: bool = False

        # project config
        self.name: str = ""
        self.owner: str = ""
        self.package_lambda: bool = True
        self.s3_bucket: str = ""
        self.tests: Dict[Test] = {}
        self.regions: Set[str] = set()
        self.env_vars = {}

        # clever processors, not well liked
        self._harvest_env_vars(all_env_vars)
        self._parse_project_config(project_config_path)

        # build config object from gathered entries
        self._process_global_config()
        self._process_project_config()
        self._process_template_config()
        self._process_env_vars()
        self._process_args()
        self._propogate_regions(client_factory_instance)
        if not self.template_path and not self.tests:
            raise TaskCatException(
                "minimal config requires at least one test or a "
                "template_path to be defined"
            )

    def _parse_project_config(self, project_config_path):
        self.project_config_path: [Path, None] = self._absolute_path(
            project_config_path
        )
        if self.project_config_path is None:
            for path in Config.DEFAULT_PROJECT_PATHS:
                try:
                    self.project_config_path: [Path, None] = self._absolute_path(path)
                    LOG.debug("found project config in default location %s", path)
                    break
                except TaskCatException:
                    LOG.debug("didn't find project config in %s", path)

    def _absolute_path(self, path: [str, Path]) -> [Path, None]:
        if path is None:
            return path
        path = Path(path)
        abs_path = absolute_path(path)
        if self.project_root and not abs_path:
            abs_path = absolute_path(self.project_root / Path(path))
        if not abs_path:
            raise TaskCatException(
                f"Unable to resolve path {path}, with project_root "
                f"{self.project_root}"
            )
        return abs_path

    def _set(self, opt, val):
        if opt in ["project", "general"]:
            for k, v in val.items():
                self._set(k, v)
            return
        if opt not in self.__dict__:
            raise ValueError(f"{opt} is not a valid config option")
        setattr(self, opt, val)

    def _set_all(self, config: dict):
        for k, v in config.items():
            self._set(k, v)

    def _propogate_regions(self, client_factory_instance):
        default_region = client_factory_instance.get_default_region(
            None, None, None, None
        )
        for test in self.tests:
            if not self.tests[test].regions and not default_region and not self.regions:
                raise TaskCatException(
                    f"unable to define region for test {test}, you must define regions "
                    f"or set a default region in the aws cli"
                )
            if not self.tests[test].regions:
                self.tests[test].regions = (
                    self.regions if self.regions else [default_region]
                )

    @staticmethod
    def validate(instance, schema_name):
        instance_copy = instance.copy()
        if isinstance(instance_copy, dict):
            if "tests" in instance_copy.keys():
                instance_copy["tests"] = Config._tests_to_dict(instance_copy["tests"])
        schema_path = Path(__file__).parent.absolute() / "cfg"
        schema = json.load(open(schema_path / f"schema_{schema_name}.json", "r"))
        validate(
            instance_copy,
            schema,
            resolver=RefResolver(str(schema_path.as_uri()) + "/", None),
        )

    @staticmethod
    def _tests_to_dict(tests):
        rendered_tests = {}
        for test in tests.keys():
            rendered_tests[test] = {}
            for k, v in tests[test].__dict__.items():
                if not k.startswith("_"):
                    if isinstance(v, Path):
                        v = str(v)
                    rendered_tests[test][k] = v
        return rendered_tests

    def _process_global_config(self):
        if self.global_config_path is None:
            return
        instance = yaml.safe_load(open(str(self.global_config_path), "r"))
        self.validate(instance, "global_config")
        self._set_all(instance)

    def _process_project_config(self):
        if self.project_config_path is None:
            return
        instance = yaml.safe_load(open(str(self.project_config_path), "r"))
        if "tests" in instance.keys():
            tests = {}
            for test in instance["tests"].keys():
                tests[test] = Test.from_dict(
                    instance["tests"][test], project_root=self.project_root
                )
            instance["tests"] = tests
        try:
            self.validate(instance, "project_config")
        except exceptions.ValidationError:
            if self._process_legacy_project(instance) is not None:
                self.validate(instance, "project_config")
        self._set_all(instance)

    def _process_legacy_project(self, instance) -> [None, Exception]:
        try:
            self.validate(instance, "legacy_project_config")
            LOG.warning(
                "%s config file is in a format that will be deprecated in the next "
                "version of taskcat",
                str(self.project_config_path),
            )
        except exceptions.ValidationError as e:
            LOG.debug("legacy config validation failed: %s", e)
            return e
        # rename global to project
        if "global" in instance:
            instance["project"] = instance["global"]
            del instance["global"]
        if "project" in instance:
            # delete unneeded config items
            for item in ["marketplace-ami", "reporting"]:
                del instance["project"][item]
            # rename items with new keys
            for item in [["qsname", "name"]]:
                instance["project"][item[1]] = instance["project"][item[0]]
                del instance["project"][item[0]]
        return None

    def _process_template_config(self):
        if not self.template_path:
            return
        template = Template(str(self.template_path)).template
        try:
            template_config = template["Metadata"]["taskcat"]
        except KeyError:
            raise TaskCatException(
                f"failed adding config from template file {str(self.template_path)} "
                f"Metadata['taskcat'] not present"
            )
        self._add_template_path(template_config)
        self.validate(template_config, "project_config")
        self._set_all(template_config)

    def _add_template_path(self, template_config):
        if "tests" in template_config.keys():
            for test in template_config["tests"].keys():
                if "template_file" not in template_config["tests"][test].keys():
                    rel_path = str(self.template_path.relative_to(self.project_root))
                    template_config["tests"][test]["template_file"] = rel_path
                template_config["tests"][test] = Test.from_dict(
                    template_config["tests"][test], project_root=self.project_root
                )

    def _process_env_vars(self):
        self._to_project(self.env_vars)
        self._to_tests(self.env_vars)
        self._to_general(self.env_vars)
        if not self.env_vars:
            return
        self.validate(self.env_vars, "project_config")
        self._set_all(self.env_vars)

    def _process_args(self):
        self._to_project(self.args)
        self._to_tests(self.args)
        self._to_general(self.args)
        if not self.args:
            return
        self.validate(self.args, "project_config")
        self._set_all(self.args)

    @staticmethod
    def _to_project(args: dict):
        for arg in args.keys():
            if arg.startswith("project_"):
                if "project" not in args.keys():
                    args["project"] = {}
                args["project"][arg[8:]] = args[arg]
                del args[arg]

    def _to_tests(self, args: dict):
        if (
            "template_file" in args.keys()
            or "parameter_input" in args.keys()
            or "regions" in args.keys()
        ):
            template_file = (
                args["template_file"] if "template_file" in args.keys() else None
            )
            parameter_input = (
                args["parameter_input"] if "parameter_input" in args.keys() else None
            )
            regions = (
                set(args["regions"].split(",")) if "regions" in args.keys() else set()
            )
            test = Test(
                template_file=template_file,
                parameter_input=parameter_input,
                regions=regions,
                project_root=self.project_root,
            )
            args["tests"] = {"default": test}
            del args["template_file"]
            del args["parameter_input"]

    @staticmethod
    def _to_general(args: dict):
        for arg in args.keys():
            if "general" not in args.keys():
                args["general"] = {}
            args["general"][arg] = args[arg]
            del args[arg]

    def _harvest_env_vars(self, env_vars):
        for key, value in env_vars:
            if key.startswith("TASKCAT_"):
                key = key[8:].lower()
                if value.isnumeric():
                    value = int(value)
                elif value.lower() in ["true", "false"]:
                    value = value.lower() == "true"
                self.env_vars[key] = value
