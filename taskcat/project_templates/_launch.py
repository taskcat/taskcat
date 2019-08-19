import logging
from pathlib import Path
from taskcat._config import Config
#from taskcat._cfn.threaded import Stacker
from taskcat._cfn.stack import Stack as Stacker
from taskcat._s3_stage import stage_in_s3 as Stager
from taskcat.exceptions import TaskCatException

LOG = logging.getLogger(__name__)

c = Config(
    project_config_path=Path('../tests/data/nested_fail/ci/taskcat.yml' '').resolve(),
    project_root=Path('../tests/data/nested_fail/').resolve()
)

Stager(c)
stacker = Stacker(c)
stacker.create_stacks()

stacker.stacks
stacker.status()


