from __future__ import print_function

import unittest
from mock import Mock

from taskcat.cfn_template import CfnTemplate


class TestCfnStacker(unittest.TestCase):

    def test_round_trip_(self):
        test_yaml = b"""
foo:
  - !Yes
    - 1
    - 2
    - 3
  - No # comment
        """
        print(type(test_yaml))
        cfnt = CfnTemplate()
        x = cfnt.load(test_yaml)
        y = cfnt.dump(x)
        print("RAW: \n%s\n\n" % test_yaml.decode('utf-8'))
        print("LOAD: \n%s\n\n" % x)
        print("DUMP: \n%s\n\n" % y)
