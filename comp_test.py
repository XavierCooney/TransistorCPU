import typing as typ

import gates_nmos
import latch
import spice
from component import Component, Node
from netlist import NetList


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
                pieces[node].append((new_interval[0], node_val))
        else:
            old_interval = intervals[interval_num - 1]
            for node, node_val in zip(nodes, old_interval[1]):
                pieces[node].append((new_interval[0], node_val))

            for node, node_val in zip(nodes, new_interval[1]):
                pieces[node].append((
                    new_interval[0] + transition_time, node_val
                ))

    return pieces


def test_binary_gate(gate: Component) -> None:
    netlist = NetList.make(gate)
    print(netlist)
    print(netlist.dump_info())

    piecewise_inputs = calculate_piecewise_inputs([
        gate.nodes['a'],
        gate.nodes['b'],
    ], 0.5, [
        (0, [0, 0]),
        (3, [0, 5]),
        (6, [5, 5]),
        (9, [0, 5]),
        (12, [0, 0]),
    ])

    print(piecewise_inputs)

    spice_src = spice.make_spice_script(
        'testing', netlist,
        piecewise_inputs,
        output_nodes=[
            gate.nodes['out'], gate.nodes['a'],
            gate.nodes['b']
        ],
        time_step='1ns',
        time_stop='17us',
        input_time_suffix='us',
    )

    print(spice_src)
    with open('spice_script/test2.cir', 'w') as spice_file:
        spice_file.write(spice_src)


def test_srlatch() -> None:
    srlatch = latch.SRLatch(None, 'main')
    netlist = NetList.make(srlatch)
    print(netlist)
    print(netlist.dump_info())

    piecewise_inputs = calculate_piecewise_inputs([
        srlatch.nodes['s'],
        srlatch.nodes['r'],
    ], 0.5, [
        (0, [0, 0]),
        (3, [5, 0]),
        (4, [0, 0]),
        (9, [0, 5]),
        (10, [0, 0]),
    ])

    spice_src = spice.make_spice_script(
        'testing', netlist,
        piecewise_inputs,
        output_nodes=[
            srlatch.nodes['s'], srlatch.nodes['q'],
            srlatch.nodes['r'], srlatch.nodes['q_not']
        ],
        time_step='1ns',
        time_stop='17us',
        input_time_suffix='us',
    )

    print(spice_src)
    with open('spice_script/test2.cir', 'w') as spice_file:
        spice_file.write(spice_src)


def test_dlatch() -> None:
    dlatch = latch.DLatch(None, 'main')
    netlist = NetList.make(dlatch)
    print(netlist)
    print(netlist.dump_info())

    piecewise_inputs = calculate_piecewise_inputs([
        dlatch.nodes['clock'], dlatch.nodes['in']
    ], 0.1, [
        (0, [0, 0]),
        (1, [0, 5]),
        (3, [5, 5]),
        (4, [0, 5]),
        (6, [0, 0]),
        (9, [5, 0]),
        (9.8, [0, 0]),
    ])

    spice_src = spice.make_spice_script(
        'testing', netlist,
        piecewise_inputs,
        output_nodes=[
            dlatch.nodes['out'], dlatch.nodes['not_out'],
            dlatch.nodes['clock'], dlatch.nodes['in'],
            # dlatch.nodes['_mid_up'], dlatch.nodes['_mid_down']
        ],
        time_step='1ns',
        time_stop='17us',
        input_time_suffix='us',
    )

    print(spice_src)
    with open('spice_script/test2.cir', 'w') as spice_file:
        spice_file.write(spice_src)


TO_TEST = 'dlatch'

if __name__ == '__main__':
    if TO_TEST == 'binary':
        test_binary_gate(gates_nmos.OrGate(None, 'main'))
    elif TO_TEST == 'dlatch':
        test_dlatch()
    elif TO_TEST == 'srlatch':
        test_srlatch()
    else:
        raise ValueError()
