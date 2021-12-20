import itertools
import typing as typ

import gates_nmos
import latch
import tester
from component import Component


class NandGateTest(tester.StatelessGateTest):
    expected_gate_delay_us = 4
    input_nodes = ['a', 'b']
    output_nodes = ['out']
    test_name = 'nand gate'

    def make_component(self) -> Component:
        return gates_nmos.NandGate(None, 'main')

    def expected_input(self, *inputs: bool) -> typ.List[bool]:
        a, b = inputs
        return [not (a and b)]


class AndGateTest(tester.StatelessGateTest):
    expected_gate_delay_us = 3
    input_nodes = ['a', 'b']
    output_nodes = ['out']
    test_name = 'and gate'

    def make_component(self) -> Component:
        return gates_nmos.AndGate(None, 'main')

    def expected_input(self, *inputs: bool) -> typ.List[bool]:
        a, b = inputs
        return [a and b]


class NorGateTest(tester.StatelessGateTest):
    expected_gate_delay_us = 3
    input_nodes = ['a', 'b']
    output_nodes = ['out']
    test_name = 'nor gate'

    def make_component(self) -> Component:
        return gates_nmos.NorGate(None, 'main')

    def expected_input(self, *inputs: bool) -> typ.List[bool]:
        a, b = inputs
        return [not (a or b)]


class OrGateTest(tester.StatelessGateTest):
    expected_gate_delay_us = 3
    input_nodes = ['a', 'b']
    output_nodes = ['out']
    test_name = 'or gate'

    def make_component(self) -> Component:
        return gates_nmos.OrGate(None, 'main')

    def expected_input(self, *inputs: bool) -> typ.List[bool]:
        a, b = inputs
        return [a or b]


class NotGateTest(tester.StatelessGateTest):
    expected_gate_delay_us = 2
    input_nodes = ['a']
    output_nodes = ['out']
    test_name = 'not gate'

    def make_component(self) -> Component:
        return gates_nmos.NotGate(None, 'main')

    def expected_input(self, *inputs: bool) -> typ.List[bool]:
        a, = inputs
        return [not a]


class XOrGateTest(tester.StatelessGateTest):
    expected_gate_delay_us = 5
    input_nodes = ['a', 'b']
    output_nodes = ['out']
    test_name = 'xor gate'

    def make_component(self) -> Component:
        return gates_nmos.XOrGate(None, 'main')

    def expected_input(self, *inputs: bool) -> typ.List[bool]:
        a, b = inputs
        return [a ^ b]


class SRLatchTest(tester.ComponentWithStateTest):
    input_nodes = ['s', 'r']
    output_nodes = ['q', 'q_not']
    test_name = 'sr latch'

    def make_component(self) -> Component:
        return latch.SRLatch(None, 'main')

    def get_io(self) -> tester.StatefulIO:
        time = 0
        io: tester.StatefulIO = []
        for pre, post, delay in itertools.product([0, 1], [0, 1], [0, 1]):
            io.append((time, {}, [pre, not pre]))
            time += 5
            if delay:
                io.append((time, {'q': pre, 'q_not': not pre}, [False, False]))
                time += 4
                io.append((time, {'q': pre, 'q_not': not pre}, [False, False]))
                time += 2
            io.append((time, {'q': pre, 'q_not': not pre}, [post, not post]))
            time += 2
            io.append((time, {}, [False, False]))
            time += 3
            io.append((time, {'q': post, 'q_not': not post}, [False, False]))
            time += 1
        return io


class DLatchTest(tester.ComponentWithStateTest):
    input_nodes = ['in', 'clock']
    output_nodes = ['out', 'not_out']
    test_name = 'd latch'

    def make_component(self) -> Component:
        return latch.DLatch(None, 'main')

    def get_io(self) -> tester.StatefulIO:
        time = 0
        io: tester.StatefulIO = []
        for pre, post, delay, do_clock in itertools.product(*([[0, 1]] * 4)):
            expected_pre = {'out': pre, 'not_out': not pre}
            expected_post = {'out': post, 'not_out': not post}

            io.append((time, {}, [pre, True]))
            time += 8

            if delay:
                io.append((time, expected_pre, [pre, False]))
                time += 4
                io.append((time, expected_pre, [not pre, 0]))
                time += 2

            if do_clock:
                io.append((time, expected_pre, [post, True]))
                time += 3
                io.append((time, {}, [post, False]))
                time += 1
                io.append((time, {}, [not post, False]))
                time += 4
                io.append((time, expected_post, [not post, False]))
                time += 1
            else:
                io.append((time, expected_pre, [post, False]))
                time += 2
                io.append((time, expected_pre, [post, False]))
                time += 1
                io.append((time, expected_pre, [not post, False]))
                time += 2
                io.append((time, expected_pre, [not post, False]))
                time += 1

        return io


class TempTest(tester.Test):
    # For putting components in the test harness temporarily
    test_name = 'temp'
    test_length_us = 10
    output_nodes = ['out']

    def make_component(self) -> Component:
        return gates_nmos.NotGate(None, 'main')

    def make_input(self, component: Component) -> tester.PieceWiseInputByNode:
        return {
            component.nodes['a']: [
                (0, 0),
                (3, 0),
                (3.2, 5),
                (6, 5),
                (6.2, 0),
            ]
        }

    def check_output(
        self, component: Component,
        get_output: typ.Callable[[float], typ.Dict[str, float]]
    ) -> None:
        assert False
