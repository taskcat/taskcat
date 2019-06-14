from taskcat.config import Config

class Test:
    """
    Performs functional tests on CloudFormation templates.
    """

    def run(self, entry_point, project_root='./'):
        print("doing a run, yeah!")
        config = Config(entry_point, project_root=project_root)


    def resume(self, run_id):
        # do some stuff