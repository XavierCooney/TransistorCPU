import gates_nmos
import component


class HalfAdder(component.Component):
    component_name = 'half_adder'
    node_names = ['a', 'b', 'sum_out', 'carry_out']

    def build(self) -> None:
        # TODO: I think the gate number (9) is fairly optimal,
        #       but speed might able to be improved a bit. Also
        #       when chained toogether the negation of the carry
        #       in the and gate is unnecessary.
        carry_and = self.add_component(gates_nmos.AndGate(None, 'carry_and'))
        sum_xor = self.add_component(gates_nmos.XOrGate(None, 'sum_xor'))

        self.connect('a', sum_xor.nodes['a'])
        self.connect('b', sum_xor.nodes['b'])
        self.connect('sum_out', sum_xor.nodes['out'])

        self.connect('a', carry_and.nodes['a'])
        self.connect('b', carry_and.nodes['b'])
        self.connect('carry_out', carry_and.nodes['out'])
