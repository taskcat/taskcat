# flake8: noqa B950,F841
import logging

from taskcat._cfn.threaded import Stacker
from taskcat._cfn_lint import Lint as TaskCatLint
from taskcat._config import Config
from taskcat._s3_stage import stage_in_s3
from taskcat.exceptions import TaskCatException

LOG = logging.getLogger(__name__)
# LOG.name = "[taskcat]"


class Test:
    """
    Performs functional tests on CloudFormation templates.
    """

    # pylint: disable=no-self-use, line-too-long, unused-variable
    def run(self, input_file, project_root="./"):
        """tests whether CloudFormation templates are able to successfully launch

        :param input_file: path to either a taskat project config file or a CloudFormation template
        :param project_root: root path of the project relative to input_file
        """
        config = Config(
            project_root=project_root,
            # TODO detect if input file is taskcat config or CloudFormation template
            project_config_path=input_file,
        )  # pylint: disable=unused-variable
        # 1. build lambdas
        # 2. lint
        lint = TaskCatLint(config, strict=False)
        errors = lint.lints[1]
        lint.output_results()
        if errors or not lint.passed:
            raise TaskCatException("Lint failed with errors")
        # 3. s3 sync
        stage_in_s3(config)
        # 4. validate
        # 5. launch stacks
        test_definition = Stacker(config)
        LOG.info(f"Project Name: {test_definition.project_name}")
        for test in test_definition.config.tests:
            LOG.info(f"Starting Test: {test}")
            LOG.info(f"Queuing Test: in {test_definition.config.regions}")
            test_definition.create_stacks()

            for stack in test_definition.stacks:
                LOG.info(
                    f"Launching test_definition: {stack.name} in Region: {stack.region_name}"
                )
        # 6. wait for completion
        # 7. delete stacks
        # 8. create report

    def resume(self, run_id):  # pylint: disable=no-self-use
        """resumes a monitoring of a previously started test run"""
        # do some stuff
        raise NotImplementedError()
