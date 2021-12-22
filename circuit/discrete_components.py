import typing as typ

import config
import netlist
from component import AtomicComponent, Component
from netlist import NetList
from sim_components import (SimulatedCapacitor, SimulatedMosfet,
                            SimulatedResistor, SimulatedVoltage)
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


class Capacitor(AtomicComponent):
    node_names = ['a', 'b']
    component_name = 'capacitor'

    def set_capacitance(self, value: float) -> 'Capacitor':
        self.capacitance = value
        return self

    def build(self) -> None: pass

    def ngspice_line(self, comp_id: str, nodes: typ.Dict[str, str]) -> str:
        return f'C{comp_id} {nodes["a"]} {nodes["b"]} {self.capacitance} ic=0'
        # complicated to get the uncharged initial conditions right
        # return (
        #     f'.model custom_cap_a{comp_id} capacitor '
        #     f'(c={self.capacitance} ic=0)\n'
        #     f'A{comp_id} {nodes["a"]} {nodes["b"]} custom_cap_a{comp_id}'
        # )

    def make_sim_component(self, nl: netlist.NetList) -> SimulatedComponent:
        return SimulatedCapacitor(
            nl.coalesced_numbering[self.nodes['a']],
            nl.coalesced_numbering[self.nodes['b']],
            self.capacitance
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


class TempTestComponent(Component):
    # Not strictly discrete but this is the best place to put it
    node_names = ['v', 'gnd', 'a']
    component_name = 'test'

    def build(self) -> None:
        voltage_source = self.add_component(Vdd(self, 'vdd'))
        ground = self.add_component(Ground(self, 'gnd'))
        r1 = self.add_component(Resistor(self, 'R1').set_resistance(100))
        # r2 = self.add_component(Resistor(self, 'R2').set_resistance(300))
        cap = self.add_component(Capacitor(self, 'C1').set_capacitance(20e-9))

        self.connect('v', voltage_source.nodes['a'])
        self.connect('v', r1.nodes['a'])
        self.connect('a', r1.nodes['b'])
        # self.connect('a', r2.nodes['a'])
        # self.connect('gnd', r2.nodes['b'])
        # self.connect('gnd', r1.nodes['b'])
        self.connect('gnd', ground.nodes['a'])

        self.connect('a', cap.nodes['a'])
        self.connect('gnd', cap.nodes['b'])
