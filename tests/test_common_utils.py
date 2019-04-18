from __future__ import print_function

import unittest
from mock import call, Mock

from taskcat.exceptions import TaskCatException
from taskcat.common_utils import param_list_to_dict, fan_out, group_stacks_by_region


class TestCommonUtils(unittest.TestCase):

    def test_get_param_includes(self):
        bad_testcases = [
            {},
            [[]],
            [{}]
        ]
        for bad in bad_testcases:
            with self.assertRaises(TaskCatException):
                param_list_to_dict(bad)

    def test_fan_out(self):
        func = Mock()
        fan_out(func, {}, [1, 2, 3], 3)
        self.assertEqual(3, func.call_count)
        self.assertEqual([call(1), call(2), call(3)], func.call_args_list)

        func.reset_mock()
        fan_out(func, {"foo": "bar"}, [1, 2, 3], 3)
        self.assertEqual([call(1, foo='bar'), call(2, foo='bar'), call(3, foo='bar')], func.call_args_list)

    def test_group_stacks_by_region(self):
        outp = group_stacks_by_region([
            "arn:aws:cloudformation:us-west-2:860521661824:stack/tCaT-qs-ci-quickstart-suse-cap-defaults-b88d1561-EKSStack-1CSWHBHBZRHQ3/7f869250-54aa-11e9-b697-0af0816e310e",
            "arn:aws:cloudformation:eu-west-2:860521661824:stack/tCaT-qs-ci-quickstart-suse-cap-defaults-b88d1561-EKSStack-1CSWHBHBZRHQ3/7f869250-54aa-11e9-b697-0af0816e310e"
        ])
        self.assertEqual([
            {'Region': 'us-west-2',
             'StackIds': ['arn:aws:cloudformation:us-west-2:860521661824:stack/tCaT-qs-ci-quickstart-suse-cap-defaults-b88d1561-EKSStack-1CSWHBHBZRHQ3/7f869250-54aa-11e9-b697-0af0816e310e']},
            {'Region': 'eu-west-2',
             'StackIds': ['arn:aws:cloudformation:eu-west-2:860521661824:stack/tCaT-qs-ci-quickstart-suse-cap-defaults-b88d1561-EKSStack-1CSWHBHBZRHQ3/7f869250-54aa-11e9-b697-0af0816e310e']}]
            , outp)
