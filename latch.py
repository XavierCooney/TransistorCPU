import gates_nmos
from component import Component


class DLatch(Component):
    node_names = ['in', 'clock', 'out', 'not_out', '_mid_up', '_mid_down']
    component_name = 'd_latch'

    def build(self) -> None:
        nand_1_up = self.add_component(gates_nmos.NandGate(self, 'nand1.up'))
        nand_1_down = self.add_component(gates_nmos.NandGate(self, 'nand1.dn'))
        nand_2_up = self.add_component(gates_nmos.NandGate(self, 'nand2.up'))
        nand_2_down = self.add_component(gates_nmos.NandGate(self, 'nand2.dn'))

        self.connect('in', nand_1_up.nodes['a'])
        self.connect('clock', nand_1_up.nodes['b'])
        self.connect('_mid_up', nand_1_down.nodes['a'])
        self.connect('clock', nand_1_down.nodes['b'])

        self.connect('_mid_up', nand_1_up.nodes['out'])
        self.connect('_mid_down', nand_1_down.nodes['out'])

        self.connect('_mid_up', nand_2_up.nodes['a'])
        self.connect('not_out', nand_2_up.nodes['b'])
        self.connect('out', nand_2_down.nodes['a'])
        self.connect('_mid_down', nand_2_down.nodes['b'])

        self.connect('out', nand_2_up.nodes['out'])
        self.connect('not_out', nand_2_down.nodes['out'])


class SRLatch(Component):
    node_names = ['s', 'r', 'q', 'q_not']
    component_name = 'sr_latch'

    def build(self) -> None:
        nor_up = self.add_component(gates_nmos.NorGate(self, 'up'))
        nor_down = self.add_component(gates_nmos.NorGate(self, 'down'))

        self.connect('r', nor_up.nodes['a'])
        self.connect('q_not', nor_up.nodes['b'])
        self.connect('q', nor_down.nodes['a'])
        self.connect('s', nor_down.nodes['b'])

        self.connect('q', nor_up.nodes['out'])
        self.connect('q_not', nor_down.nodes['out'])
