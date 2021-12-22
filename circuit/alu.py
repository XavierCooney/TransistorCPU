import typing as typ

import component
import gates_nmos
from config import bits_suffix


class HalfAdder(component.Component):
    component_name = 'half_adder'
    node_names = ['a', 'b', 'sum_out', 'carry_out']

    def build(self) -> None:
        # TODO: I think the gate number (9) is fairly optimal,
        #       but speed might able to be improved a bit. Also
        #       when chained toogether the negation of the carry
        #       in the and gate is unnecessary.
        carry_and = self.add_component(gates_nmos.AndGate(self, 'carry_and'))
        sum_xor = self.add_component(gates_nmos.XOrGate(self, 'sum_xor'))

        self.connect('a', sum_xor.nodes['a'])
        self.connect('b', sum_xor.nodes['b'])
        self.connect('sum_out', sum_xor.nodes['out'])

        self.connect('a', carry_and.nodes['a'])
        self.connect('b', carry_and.nodes['b'])
        self.connect('carry_out', carry_and.nodes['out'])


class UnsizedIncrementor(component.Component):
    component_name = 'unsized_incrementor'
    node_names = ['']

    def __init__(
        self, parent: typ.Optional['component.Component'],
        role: str, num_bits: int
    ) -> None:
        self.num_bits = num_bits
        assert num_bits >= 2

        self.node_names = [
            *bits_suffix('in_', self.num_bits),
            *bits_suffix('out_', self.num_bits + 1),
            *bits_suffix('_carry_', self.num_bits)[1:-1],
        ]

        super().__init__(parent, role)

    def build(self) -> None:
        in_0_not = self.add_component(gates_nmos.NotGate(self, 'in_0_not'))
        self.connect('in_0', in_0_not.nodes['a'])
        self.connect('out_0', in_0_not.nodes['out'])

        previous_carry_node = 'in_0'
        for bit in range(1, self.num_bits):
            adder = self.add_component(HalfAdder(self, f'adder_{bit}'))
            self.connect(f'in_{bit}', adder.nodes['a'])
            self.connect(previous_carry_node, adder.nodes['b'])
            self.connect(f'out_{bit}', adder.nodes['sum_out'])

            next_carry_node = f'_carry_{bit}'
            if bit == self.num_bits - 1:
                next_carry_node = f'out_{bit + 1}'
            self.connect(next_carry_node, adder.nodes['carry_out'])
            previous_carry_node = next_carry_node
