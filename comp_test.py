import os
import subprocess
import sys
import typing as typ

import config
import gates_nmos
import latch
import spice
from component import Component, Node
from config import VOLTAGE
from discrete_components import TempTestComponent
from netlist import NetList

us = 1e-6
ns = 1e-9
HIGH = config.VOLTAGE - 0.3
LOW = 0.3


def calculate_piecewise_inputs(
    nodes: typ.List[Node],
    transition_time: float,
    intervals: typ.List[typ.Tuple[float, typ.List[float]]]
) -> typ.Dict[Node, typ.List[typ.Tuple[float, float]]]:
    pieces: typ.Dict[Node, typ.List[typ.Tuple[float, float]]] = {
        node: [] for node in nodes
    }

    for interval_num, new_interval in enumerate(intervals):
        assert len(new_interval[1]) == len(nodes)

        if interval_num == 0:
            for node, node_val in zip(nodes, new_interval[1]):
                pieces[node].append((new_interval[0], node_val * VOLTAGE))
        else:
            old_interval = intervals[interval_num - 1]
            for node, node_val in zip(nodes, old_interval[1]):
                pieces[node].append((new_interval[0], node_val * VOLTAGE))

            for node, node_val in zip(nodes, new_interval[1]):
                pieces[node].append((
                    new_interval[0] + transition_time, node_val * VOLTAGE
                ))

    return pieces


def process_spice_output(
    output_names: typ.List[str]
) -> typ.Callable[[float], typ.Dict[str, float]]:
    with open('spice_script/out.data') as out_file:
        lines = out_file.read().split('\n')

    while lines[-1] == '':
        lines = lines[:-1]
    lines = lines[1:]  # header row

    output_data: typ.List[typ.Tuple[float, typ.List[float]]] = []

    for line in lines:
        assert len(line) == 2 * 16 * len(output_names)

        segments = [
            float(line[i * 16:(i + 1) * 16].strip())
            for i in range(len(output_names) * 2)
        ]
        time = segments[0]
        assert all(segment == time for segment in segments[::2])

        output_data.append((time, segments[1::2]))

    assert list(sorted(output_data)) == output_data

    REQUIRED_INCREMENT = 5 * 10 ** -9  # 5 ns

    def find_output_data(required_time: float) -> typ.Dict[str, float]:
        # binary search for the data at a given time
        start = 0
        end = len(output_data)

        while start + 1 < end:
            mid = (start + end) // 2
            if output_data[mid][0] < required_time:
                start = mid
            else:
                end = mid

        assert abs(output_data[start][0] - required_time) < REQUIRED_INCREMENT

        return dict(zip(output_names, output_data[start][1]))

    # reveal_type(find_output_data)
    return find_output_data


def run_spice_script(
    source: str, interactive: bool,
    outputs: typ.List[str]
) -> typ.Callable[[float], typ.Dict[str, float]]:
    print(source)

    with open('spice_script/script.cir', 'w') as spice_file:
        spice_file.write(source)

    with open('spice_script/out.data', 'w') as out_file:
        out_file.write('')

    # TODO: *nix support for this
    output = subprocess.check_output(
        ['spice64\\bin\\ngspice.exe', 'script.cir'],
        cwd=os.path.abspath('spice_script'),
        encoding='utf-8'
    )
    print(output)

    if not interactive:
        output = subprocess.check_output(
            ['spice64\\bin\\ngspice_con.exe', '-b', 'script.cir'],
            cwd=os.path.abspath('spice_script'),
            encoding='utf-8'
        )

        print(output)

        return process_spice_output(outputs)
    else:
        def no_data(time: float) -> typ.NoReturn:
            assert False
        return no_data


def test_binary_gate(interactive: bool, gate: Component) -> None:
    netlist = NetList.make(gate)
    print(netlist)
    print(netlist.dump_info())

    piecewise_inputs = calculate_piecewise_inputs([
        gate.nodes['a'],
        gate.nodes['b'],
    ], 0.5, [
        (0, [0, 0]),
        (3, [0, 1]),
        (6, [1, 1]),
        (9, [0, 1]),
        (12, [0, 0]),
    ])

    print(piecewise_inputs)

    spice_src, output_list = spice.make_spice_script(
        'Binary Gate', netlist,
        piecewise_inputs,
        output_nodes=[
            gate.nodes['out'], gate.nodes['a'],
            gate.nodes['b']
        ],
        time_step='1ns',
        time_stop='17us',
        input_time_suffix='us',
        output_data=not interactive
    )

    run_spice_script(spice_src, interactive, output_list)


def test_srlatch(interactive: bool) -> None:
    srlatch = latch.SRLatch(None, 'main')
    netlist = NetList.make(srlatch)
    print(netlist)
    print(netlist.dump_info())

    piecewise_inputs = calculate_piecewise_inputs([
        srlatch.nodes['s'],
        srlatch.nodes['r'],
    ], 0.5, [
        (0, [0, 0]),
        (3, [1, 0]),
        (4, [0, 0]),
        (9, [0, 1]),
        (10, [0, 0]),
    ])

    spice_src, output_list = spice.make_spice_script(
        'SR Latch', netlist,
        piecewise_inputs,
        output_nodes=[
            srlatch.nodes['s'], srlatch.nodes['q'],
            srlatch.nodes['r'], srlatch.nodes['q_not']
        ],
        time_step='1ns',
        time_stop='17us',
        input_time_suffix='us',
        output_data=not interactive,
    )

    check_data = run_spice_script(spice_src, interactive, output_list)
    if not interactive:
        assert check_data(8 * us)['q'] > HIGH
        assert check_data(8 * us)['q_not'] < LOW
        assert check_data(14 * us)['q'] < LOW
        assert check_data(14 * us)['q_not'] > HIGH


def test_dlatch(interactive: bool) -> None:
    dlatch = latch.DLatch(None, 'main')
    netlist = NetList.make(dlatch)
    print(netlist)
    print(netlist.dump_info())

    piecewise_inputs = calculate_piecewise_inputs([
        dlatch.nodes['clock'], dlatch.nodes['in']
    ], 0.1, [
        (0, [0, 0]),
        (1, [0, 1]),
        (3, [1, 1]),
        (4, [0, 1]),
        (6, [0, 0]),
        (9, [1, 0]),
        (10, [0, 0]),
    ])

    spice_src, output_list = spice.make_spice_script(
        'D Latch', netlist,
        piecewise_inputs,
        output_nodes=[
            dlatch.nodes['out'], dlatch.nodes['not_out'],
            dlatch.nodes['clock'], dlatch.nodes['in'],
            # dlatch.nodes['_mid_up'], dlatch.nodes['_mid_down']
        ],
        time_step='1ns',
        time_stop='17us',
        input_time_suffix='us',
        output_data=not interactive
    )

    check_data = run_spice_script(spice_src, interactive, output_list)
    if not interactive:
        assert check_data(7 * us)['out'] > HIGH
        assert check_data(7 * us)['not_out'] < LOW
        assert check_data(15 * us)['out'] < LOW
        assert check_data(15 * us)['not_out'] > HIGH


def test_temp_component(interactive: bool) -> None:
    component = TempTestComponent(None, 'main')
    netlist = NetList.make(component)
    print(netlist)
    print(netlist.dump_info())

    piecewise_inputs = calculate_piecewise_inputs([], 0.1, [])

    spice_src, output_list = spice.make_spice_script(
        'Test', netlist,
        piecewise_inputs,
        output_nodes=[
            component.nodes['v'], component.nodes['gnd'],
            component.nodes['a']
        ],
        time_step='1ns',
        time_stop='17us',
        input_time_suffix='us',
        output_data=not interactive
    )

    check_data = run_spice_script(spice_src, interactive, output_list)
    if not interactive:
        assert check_data(0.05 * us)['v'] > HIGH
        assert check_data(0.05 * us)['gnd'] < LOW
        assert 3.7 < check_data(8 * us)['a'] < 3.8


TEST_OVERRIDE: typ.Optional[str] = sys.argv[-1] if len(sys.argv) >= 2 else None
TEST_ALL = TEST_OVERRIDE is None

tests: typ.Dict[str, typ.Callable[[bool], None]] = {
    'dlatch': test_dlatch,
    'srlatch': test_srlatch,
    'nand': lambda i: test_binary_gate(i, gates_nmos.NandGate(None, 'main')),
    'and': lambda i: test_binary_gate(i, gates_nmos.AndGate(None, 'main')),
    'nor': lambda i: test_binary_gate(i, gates_nmos.NorGate(None, 'main')),
    'or': lambda i: test_binary_gate(i, gates_nmos.OrGate(None, 'main')),
    'temp_test': test_temp_component,
}

if __name__ == '__main__':
    if TEST_ALL:
        for test_name, test in tests.items():
            test(False)
    elif TEST_OVERRIDE is not None:
        tests[TEST_OVERRIDE](len(sys.argv) < 2 or sys.argv[1] != 'ni')
