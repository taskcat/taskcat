import time

from reprint import output

from taskcat._cfn.threaded import Stacker as TaskcatStacker
from taskcat._logger import PrintMsg


class TerminalPrinter:
    def __init__(self):
        self._buffer_type = "list"
        self.buffer = self._add_buffer()

    def _add_buffer(self):
        with output(output_type=self._buffer_type) as output_buffer:
            return output_buffer

    def report_test_progress(self, stacker: TaskcatStacker, poll_interval=10):
        _status_dict = stacker.status()
        while self._is_test_in_progress(_status_dict):
            for stack in stacker.stacks:
                self._print_stack_tree(stack, buffer=self.buffer)
            time.sleep(poll_interval)
            self.buffer.clear()

    @staticmethod
    def _print_stack_tree(stack, buffer):
        padding_1 = "         "
        buffer.append(
            "{}{}stack {} {}".format(padding_1, "\u250f ", "\u24c5", stack.name)
        )
        buffer.append("{}{} region: {}".format(padding_1, "\u2523", stack.region_name))
        buffer.append(
            "{}{}status: {}{}{}".format(
                padding_1, "\u2517 ", PrintMsg.white, stack.status, PrintMsg.rst_color
            )
        )

    #        if stack.children:
    #            for child in stack.descendants():
    #                buffer.append(f'         ┗ {child.name}')

    @staticmethod
    def _is_test_in_progress(status_dict, status_condition="IN_PROGRESS"):
        return bool(len(status_dict[status_condition]) > 0)

        # for stack in stack:

    #    LOG.info(
    #        f"Launching test_definition: {stack.name} in Region: {stack.region_name}"
    #    )