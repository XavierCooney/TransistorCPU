import gates_nmos
from netlist import NetList
import spice

if __name__ == '__main__':
    not_gate = gates_nmos.NotGate(None, 'main')
    netlist = NetList.make(not_gate)
    print(netlist)
    print(netlist.dump_info())

    spice_src = spice.make_spice_script(
        'testing', netlist,
        {
            not_gate.nodes['a']: [(0, 5), (1, 5), (1.1, 0), (4, 0), (4.1, 5)],
        },
        output_nodes=[not_gate.nodes['out'], not_gate.nodes['a']],
        time_step='1ns',
        time_stop='6us',
        input_time_suffix='us',
    )

    print(spice_src)
    with open('spice_script/test2.cir', 'w') as spice_file:
        spice_file.write(spice_src)
