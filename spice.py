# Specifically ngspice

import typing as typ

from netlist import NetList
from component import Node

VOLTAGE = 5


def make_node_id(
    netlist: NetList, node: Node,
    special_node_groups: typ.Dict[int, str]
) -> str:
    if netlist.coalesced_numbering[node] in special_node_groups:
        return special_node_groups[netlist.coalesced_numbering[node]]

    node_id = f'n{netlist.coalesced_numbering[node]}'
    return node_id


def make_spice_script(  # TODO: this is a bit ugly...
    title: str, netlist: NetList,
    inputs: typ.Dict[Node, typ.List[typ.Tuple[float, float]]],
    output_nodes: typ.List[Node],
    time_step: str = '1ns',
    time_stop: str = '5us',
    input_time_suffix: str = "us",
) -> str:
    segments: typ.List[str] = []

    special_nodes: typ.Dict[int, str] = {}
    for output_node in output_nodes:
        assert netlist.coalesced_numbering[output_node] not in special_nodes
        special_id = f'n_{output_node.name}'
        special_nodes[netlist.coalesced_numbering[output_node]] = special_id

    segments.append(f'.title {title}')
    segments.append('.option TEMP=25C')
    segments.append('.include 2N7000.mod')
    segments.append(f'Vdd vdd gnd dc {VOLTAGE}')

    comp_id = 1

    for atomic in netlist.atomic_componenets:
        atomic_node_numbering = {
            node_name: f'{make_node_id(netlist, node, special_nodes)}'
            for node_name, node in atomic.nodes.items()
        }
        segments.append(atomic.ngspice_line(
            f'a{comp_id}',
            atomic_node_numbering
        ))
        comp_id += 1

    for input_node, input_commands in inputs.items():
        piecewise_form = ' '.join(
            f'{input_time}{input_time_suffix} {input_val}'
            for input_time, input_val in input_commands
        )
        segments.append(
            f'V{comp_id} {make_node_id(netlist, input_node, special_nodes)}'
            f' gnd PWL({piecewise_form})'
        )
        comp_id += 1

    segments.append('.control')
    segments.append(f'tran {time_step} {time_stop}')

    segments.append(
        'plot ' + ' '.join(
            f'v({make_node_id(netlist, output_node, special_nodes)})'
            for output_node in output_nodes
        )
    )

    segments.append('.endc')

    segments.append('.end')

    return '\n'.join(segments)
