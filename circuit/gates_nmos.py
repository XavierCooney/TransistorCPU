""" Gates based on NMOS logic """

from component import Component
from discrete_components import Ground, NTypeMosfet, PullUpResistor


class NandGate(Component):
    node_names = ['a', 'b', 'out', '_mid', '_gnd']
    component_name = 'nand'

    def build(self) -> None:
        mosfet_a = self.add_component(NTypeMosfet(self, 'nmos_a'))
        mosfet_b = self.add_component(NTypeMosfet(self, 'nmos_b'))
        resistor = self.add_component(PullUpResistor(self, 'pullup'))
        ground = self.add_component(Ground(self, 'gnd'))

        self.connect('out', resistor.nodes['a'])
        self.connect('out', mosfet_a.nodes['drain'])
        self.connect('a', mosfet_a.nodes['gate'])
        self.connect('_mid', mosfet_a.nodes['source'])
        self.connect('_mid', mosfet_b.nodes['drain'])
        self.connect('b', mosfet_b.nodes['gate'])
        self.connect('_gnd', mosfet_b.nodes['source'])
        self.connect('_gnd', ground.nodes['a'])


class NorGate(Component):
    node_names = ['a', 'b', 'out', '_gnd']
    component_name = 'nor'

    def build(self) -> None:
        mosfet_a = self.add_component(NTypeMosfet(self, 'nmos_a'))
        mosfet_b = self.add_component(NTypeMosfet(self, 'nmos_b'))
        resistor = self.add_component(PullUpResistor(self, 'pullup'))
        ground = self.add_component(Ground(self, 'gnd'))

        self.connect('out', resistor.nodes['a'])
        self.connect('out', mosfet_a.nodes['drain'])
        self.connect('out', mosfet_b.nodes['drain'])

        self.connect('a', mosfet_a.nodes['gate'])
        self.connect('b', mosfet_b.nodes['gate'])

        self.connect('_gnd', mosfet_a.nodes['source'])
        self.connect('_gnd', mosfet_b.nodes['source'])
        self.connect('_gnd', ground.nodes['a'])


class NotGate(Component):
    node_names = ['a', 'out', '_gnd']
    component_name = 'not'

    def build(self) -> None:
        mosfet = self.add_component(NTypeMosfet(self, 'nmos'))
        pullup = self.add_component(PullUpResistor(self, 'pullup'))
        ground = self.add_component(Ground(self, 'ground'))

        self.connect('a', mosfet.nodes['gate'])
        self.connect('out', mosfet.nodes['drain'])
        self.connect('out', pullup.nodes['a'])
        self.connect('_gnd', mosfet.nodes['source'])
        self.connect('_gnd', ground.nodes['a'])


class AndGate(Component):
    node_names = ['a', 'b', '_nand_res', 'out']
    component_name = 'and'

    def build(self) -> None:
        nand_gate = self.add_component(NandGate(self, 'nand'))
        not_gate = self.add_component(NotGate(self, 'not'))

        self.connect('a', nand_gate.nodes['a'])
        self.connect('b', nand_gate.nodes['b'])
        self.connect('_nand_res', nand_gate.nodes['out'])
        self.connect('_nand_res', not_gate.nodes['a'])
        self.connect('out', not_gate.nodes['out'])


class OrGate(Component):
    node_names = ['a', 'b', '_nor_res', 'out']
    component_name = 'or'

    def build(self) -> None:
        nor_gate = self.add_component(NorGate(self, 'nor'))
        not_gate = self.add_component(NotGate(self, 'not'))

        self.connect('a', nor_gate.nodes['a'])
        self.connect('b', nor_gate.nodes['b'])
        self.connect('_nor_res', nor_gate.nodes['out'])
        self.connect('_nor_res', not_gate.nodes['a'])
        self.connect('out', not_gate.nodes['out'])


class XOrGate(Component):
    node_names = [
        'a', 'b', '_not_a', '_not_b', '_gnd',
        '_mid_left', '_mid_right', 'out'
    ]
    component_name = 'xor'

    def build(self) -> None:
        not_a = self.add_component(NotGate(self, 'not_a'))
        not_b = self.add_component(NotGate(self, 'not_b'))

        self.connect('a', not_a.nodes['a'])
        self.connect('b', not_b.nodes['a'])

        self.connect('_not_a', not_a.nodes['out'])
        self.connect('_not_b', not_b.nodes['out'])

        pullup = self.add_component(PullUpResistor(self, 'pullup'))
        self.connect('out', pullup.nodes['a'])

        ground = self.add_component(Ground(self, 'gnd'))
        self.connect('_gnd', ground.nodes['a'])

        nmos_a = self.add_component(NTypeMosfet(self, 'nmos_a'))
        nmos_b = self.add_component(NTypeMosfet(self, 'nmos_b'))

        self.connect('a', nmos_a.nodes['gate'])
        self.connect('b', nmos_b.nodes['gate'])

        self.connect('out', nmos_a.nodes['drain'])
        self.connect('_mid_right', nmos_a.nodes['source'])
        self.connect('_mid_right', nmos_b.nodes['drain'])
        self.connect('_gnd', nmos_b.nodes['source'])

        nmos_not_a = self.add_component(NTypeMosfet(self, 'nmos_not_a'))
        nmos_not_b = self.add_component(NTypeMosfet(self, 'nmos_not_b'))

        self.connect('_not_a', nmos_not_a.nodes['gate'])
        self.connect('_not_b', nmos_not_b.nodes['gate'])

        self.connect('out', nmos_not_a.nodes['drain'])
        self.connect('_mid_left', nmos_not_a.nodes['source'])
        self.connect('_mid_left', nmos_not_b.nodes['drain'])
        self.connect('_gnd', nmos_not_b.nodes['source'])
