import abc
import itertools
import sys
import typing as typ

import config
import test_spice
from component import Component, Node
from netlist import NetList

PieceWiseInputByNode = typ.Dict[Node, typ.List[typ.Tuple[float, float]]]


def construct_linear_piecewise_input(
    nodes: typ.List[Node], transition_time: float,
    intervals: typ.List[typ.Tuple[float, typ.List[float]]]
) -> PieceWiseInputByNode:
    pieces: typ.Dict[Node, typ.List[typ.Tuple[float, float]]] = {
        node: [] for node in nodes
    }

    for interval_num, new_interval in enumerate(intervals):
        assert len(new_interval[1]) == len(nodes)

        if interval_num == 0:
            for node, node_val in zip(nodes, new_interval[1]):
                node_voltage = node_val * config.VOLTAGE
                pieces[node].append((new_interval[0], node_voltage))
        else:
            old_interval = intervals[interval_num - 1]
            for node, node_val in zip(nodes, old_interval[1]):
                node_voltage = node_val * config.VOLTAGE
                pieces[node].append((new_interval[0], node_voltage))

            for node, node_val in zip(nodes, new_interval[1]):
                node_voltage = node_val * config.VOLTAGE
                pieces[node].append((
                    new_interval[0] + transition_time, node_voltage
                ))

    return pieces


def component_nodes_by_name(
    component: Component, names: typ.List[str]
) -> typ.List[Node]:
    return [component.nodes[name] for name in names]


class Test(abc.ABC):
    @abc.abstractproperty
    def test_name(self) -> str: pass

    @abc.abstractproperty
    def output_nodes(self) -> typ.List[str]: pass

    @abc.abstractproperty
    def test_length_us(self) -> float: pass

    def __init__(self, verbose: bool, interactive: bool) -> None:
        self.verbose = verbose
        self.interactive = interactive

    def start_test(self) -> None:
        if self.verbose or True:
            print(f"\n  === {self.test_name} ===")

    @abc.abstractmethod
    def make_component(self) -> Component: pass

    def make_netlist(self, component: Component) -> NetList:
        netlist = NetList.make(component)
        if self.verbose:
            print(netlist.dump_info())
        return netlist

    @abc.abstractmethod
    def make_input(self, component: Component) -> PieceWiseInputByNode: pass

    @abc.abstractmethod
    def check_output(
        self, component: Component,
        get_output: typ.Callable[[float], typ.Dict[str, float]]
    ) -> None: pass


class StatelessGateTest(Test):
    @abc.abstractproperty
    def input_nodes(self) -> typ.List[str]: pass

    @abc.abstractproperty
    def expected_gate_delay_us(self) -> float: pass

    @property
    def test_length_us(self) -> float:
        num_states: float = 2 ** (2 * len(self.input_nodes)) + 1
        return self.expected_gate_delay_us * (2 * num_states + 1)

    def get_input_pieces(
        self, component: Component
    ) -> typ.List[typ.Tuple[float, typ.List[float]]]:
        input_state_len = len(self.input_nodes)

        all_states = itertools.product(
            *[[0, 1] for i in range(input_state_len * 2)]
        )

        time: float = 0
        input_pieces: typ.List[typ.Tuple[float, typ.List[float]]] = []

        for state in all_states:
            state_pre = list(state[:input_state_len])
            input_pieces.append((time, state_pre))
            time += self.expected_gate_delay_us
            state_actual = list(state[input_state_len:])
            input_pieces.append((time, state_actual))
            time += self.expected_gate_delay_us

        return input_pieces

    def make_input(self, component: Component) -> PieceWiseInputByNode:
        input_pieces = self.get_input_pieces(component)
        if self.verbose:
            print(input_pieces)

        return construct_linear_piecewise_input(
            component_nodes_by_name(component, self.input_nodes),
            0.1, input_pieces
        )

    @abc.abstractmethod
    def expected_input(self, *inputs: bool) -> typ.List[bool]: pass

    def check_output(
        self, component: Component,
        get_output: typ.Callable[[float], typ.Dict[str, float]]
    ) -> None:
        input_pieces = self.get_input_pieces(component)

        for piece in input_pieces:
            check_time = piece[0] + self.expected_gate_delay_us - 0.1
            actual_output = get_output(check_time * 1e-6)
            input_as_bools = [bool(inp) for inp in piece[1]]
            expected_output = self.expected_input(*input_as_bools)

            assert len(self.output_nodes) == len(expected_output)

            for i, output_node in enumerate(self.output_nodes):
                is_correct = False
                if expected_output[i]:
                    is_correct = actual_output[output_node] > config.HIGH
                else:
                    is_correct = actual_output[output_node] < config.LOW

                if not is_correct:
                    print(f"Incorrect value @ t = {check_time} us:")
                    print(f"      Input: {input_as_bools}")
                    print(f"   Expected: {expected_output}")
                    print(f"     Actual: {actual_output}")
                    print(f"      State: {i=} {output_node=}")
                    assert False


StatefulIO = typ.List[typ.Tuple[float, typ.Dict[str, float], typ.List[float]]]


class ComponentWithStateTest(Test):
    @abc.abstractproperty
    def input_nodes(self) -> typ.List[str]: pass

    @abc.abstractmethod
    def get_io(self) -> StatefulIO:
        pass

    @property
    def test_length_us(self) -> float:
        io = self.get_io()  # TODO: cache this
        return io[-1][0] + 5

    def make_input(self, component: Component) -> PieceWiseInputByNode:
        io = self.get_io()
        if self.verbose:
            print(io)

        input_pieces = []
        for io_command in io:
            input_pieces.append((io_command[0], io_command[2]))

        return construct_linear_piecewise_input(
            component_nodes_by_name(component, self.input_nodes),
            0.1, input_pieces
        )

    def check_output(
        self, component: Component,
        get_output: typ.Callable[[float], typ.Dict[str, float]]
    ) -> None:
        io = self.get_io()

        for io_command in io:
            check_time = io_command[0] - 0.05
            if len(io_command[1]) == 0:
                continue  # no tests
            actual_output = get_output(check_time * 1e-6)
            expected_output = io_command[1]

            for node_name, expected in expected_output.items():
                voltage = actual_output[node_name]
                if expected:
                    is_correct = voltage > config.HIGH
                else:
                    is_correct = voltage < config.LOW

                if not is_correct:
                    print(f"Incorrect value @ t = {check_time} us:")
                    print(f"   Expected: {expected_output}")
                    print(f"     Actual: {actual_output}")
                    assert False


def make_test_dict() -> typ.Dict[str, typ.Type[Test]]:
    import all_tests

    dict_obj: typ.Dict[str, typ.Type[Test]] = {
        'nand': all_tests.NandGateTest,
        'and': all_tests.AndGateTest,
        'nor': all_tests.NorGateTest,
        'or': all_tests.OrGateTest,
        'not': all_tests.NotGateTest,
        'sr_latch': all_tests.SRLatchTest,
        'd_latch': all_tests.DLatchTest,
    }

    assert len(set(dict_obj.values())) == len(dict_obj)

    return dict_obj


def main() -> None:
    test_dict = make_test_dict()

    tests_to_run = []
    is_interactive = False
    is_verbose = False

    for arg in sys.argv[1:]:
        if arg in ('-i', '--interactive'):
            is_interactive = True
        elif arg in ('-v', '--verbose'):
            is_verbose = True
        elif arg in test_dict.keys():
            tests_to_run.append(arg)
        else:
            print("Unknown argument:", arg)
            print("           Flags: -i, --interactive, -v, --verbose")
            print("           Tests: ", ', '.join(test_dict.keys()))
            sys.exit(1)

    if len(tests_to_run) == 0:
        tests_to_run = list(test_dict.keys())

    for test_name in tests_to_run:
        test = test_dict[test_name](is_verbose, is_interactive)
        test_spice.run_test(test)


if __name__ == '__main__':
    main()
