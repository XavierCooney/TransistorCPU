import typing as typ

import gates_nmos
import spice
from netlist import NetList
from component import Node


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


if __name__ == '__main__':
    and_gate = gates_nmos.AndGate(None, 'main')
    netlist = NetList.make(and_gate)
    print(netlist)
    print(netlist.dump_info())

    piecewise_inputs = calculate_piecewise_inputs([
        and_gate.nodes['a'],
        and_gate.nodes['b']
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
            and_gate.nodes['out'], and_gate.nodes['a'],
            and_gate.nodes['b']
        ],
        time_step='1ns',
        time_stop='15us',
        input_time_suffix='us',
    )

    print(spice_src)
    with open('spice_script/test2.cir', 'w') as spice_file:
        spice_file.write(spice_src)
