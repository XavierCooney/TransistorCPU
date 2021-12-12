""" Gates based on NMOS logic """

from component import Component
from transistor import Ground, NTypeMosfet, PullUpResistor


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


class NotGateWithNand(Component):
    node_names = ['a', 'out']
    component_name = 'not_w_nand'

    def build(self) -> None:
        main_nand = self.add_component(NandGate(self, 'nand'))

        self.connect('a', main_nand.nodes['a'])
        self.connect('a', main_nand.nodes['b'])
        self.connect('out', main_nand.nodes['out'])


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
        main_nand = self.add_component(NandGate(self, 'main_nand'))
        not_nand = self.add_component(NandGate(self, 'not_nand'))

        self.connect('a', main_nand.nodes['a'])
        self.connect('b', main_nand.nodes['b'])
        self.connect('_nand_res', main_nand.nodes['out'])
        self.connect('_nand_res', not_nand.nodes['a'])
        self.connect('_nand_res', not_nand.nodes['b'])
        self.connect('out', not_nand.nodes['out'])
