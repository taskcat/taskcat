from __future__ import print_function

import unittest
from mock import Mock

from taskcat.exceptions import TaskCatException
from taskcat.cfn_stacker import CfnStacker
import uuid

class TestCfnStacker(unittest.TestCase):

    def test__init__(self):
        """(self, project_name: str, uid: uuid.UUID = NULL_UUID, template_urls: list = None, regions: list = None,
                 recurse: bool = True, stack_name_prefix: str = 'tCat', tags: list = None,
                 client_factory_instance=None)
        self.project_name = project_name
        self.recurse = recurse
        self.stack_name_prefix = stack_name_prefix
        self.template_urls = template_urls if template_urls else []
        self.regions = regions if regions else []
        self.tags = tags if tags else []
        self.client_factory = client_factory_instance if client_factory_instance else ClientFactory()
        self.uid = uuid.uuid4() if uid == CfnStacker.NULL_UUID else uid"""
        c = CfnStacker("pn")

        # Check defaults are what's expected
        defaults = [["project_name", "pn", c.project_name], ["recurse", True, c.recurse], ["regions",[], c.regions],
                    ["stack_name_prefix", 'tCat', c.stack_name_prefix], ["template_urls", [], c.template_urls],
                    ["tags", [], c.tags]]
        msg = "Backwards incompatible change to CfnStacker init defaults {}"
        for p in defaults:
            self.assertEqual(p[1], p[2], msg.format(p[0]))

        # Check passed in values are being set for instance
        id = uuid.UUID()
        cfi = Mock()
        params = [["project_name", "pn", c.project_name], ["recurse", True, c.recurse], ["regions",[], c.regions],
                    ["stack_name_prefix", 'tCat', c.stack_name_prefix], ["template_urls", [], c.template_urls],
                    ["tags", [], c.tags]]
        c = CfnStacker("pn", uid=id, template_urls=["t1"], regions=["r1"], recurse=False,
                       stack_name_prefix='pfx', tags=["t1"], client_factory_instance=cfi)
