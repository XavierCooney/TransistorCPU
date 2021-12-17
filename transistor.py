import typing as typ

import config
import netlist
from component import AtomicComponent, Component
from netlist import NetList
from sim_components import SimulatedMosfet, SimulatedResistor, SimulatedVoltage
from simulation import SimulatedComponent


class NTypeMosfet(AtomicComponent):
    node_names = ['gate', 'drain', 'source']
    component_name = 'nmos'

    def build(self) -> None: pass

    def ngspice_line(self, comp_id: str, nodes: typ.Dict[str, str]) -> str:
        return (
            f'X{comp_id} {nodes["drain"]} '
            f'{nodes["gate"]} {nodes["source"]} 2N7000'
        )

    def make_sim_component(self, netlist: NetList) -> SimulatedMosfet:
        return SimulatedMosfet(
            netlist.coalesced_numbering[self.nodes['drain']],
            netlist.coalesced_numbering[self.nodes['gate']],
            netlist.coalesced_numbering[self.nodes['source']]
        )


class Ground(AtomicComponent):
    node_names = ['a']
    component_name = 'gnd'

    def build(self) -> None: pass

    def ngspice_line(self, comp_id: str, nodes: typ.Dict[str, str]) -> str:
        # 0 voltage source = short circuit
        # return f'V{comp_id} {nodes["a"]} gnd 0'
        return f'R{comp_id} {nodes["a"]} gnd 0.01'

    def make_sim_component(self, nl: netlist.NetList) -> SimulatedComponent:
        return SimulatedVoltage(
            nl.coalesced_numbering[self.nodes['a']], 0
        )


class Vdd(AtomicComponent):
    node_names = ['a']
    component_name = 'vdd'

    def build(self) -> None: pass

    def ngspice_line(self, comp_id: str, nodes: typ.Dict[str, str]) -> str:
        return f'V{comp_id} {nodes["a"]} gnd {config.VOLTAGE}'

    def make_sim_component(self, nl: netlist.NetList) -> SimulatedComponent:
        return SimulatedVoltage(
            nl.coalesced_numbering[self.nodes['a']],
            config.VOLTAGE
        )


class Resistor(AtomicComponent):
    node_names = ['a', 'b']
    component_name = 'resistor'

    def set_resistance(self, value: float) -> 'Resistor':
        self.resistance = value
        return self

    def build(self) -> None: pass

    def ngspice_line(self, comp_id: str, nodes: typ.Dict[str, str]) -> str:
        return f'R{comp_id} {nodes["a"]} {nodes["b"]} {self.resistance}'

    def make_sim_component(self, nl: netlist.NetList) -> SimulatedComponent:
        return SimulatedResistor(
            nl.coalesced_numbering[self.nodes['a']],
            nl.coalesced_numbering[self.nodes['b']],
            self.resistance
        )


class PullUpResistor(Component):
    node_names = ['a', '_vdd']
    component_name = 'pullup_resistor'

    def build(self) -> None:
        res = self.add_component(Resistor(self, 'pullup').set_resistance(5000))
        vdd = self.add_component(Vdd(self, 'vdd'))
        self.connect('a', res.nodes['a'])
        self.connect('_vdd', res.nodes['b'])
        self.connect('_vdd', vdd.nodes['a'])
