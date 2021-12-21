import typing as typ

import component
import latch
from config import bits_suffix


class Register(component.Component):
    component_name = 'register'
    node_names = ['']

    def __init__(
        self, parent: typ.Optional['component.Component'],
        role: str, num_bits: int
    ) -> None:
        self.num_bits = num_bits
        assert num_bits >= 2

        self.node_names = [
            'write_to_reg',  # TODO: add a reset line
            *bits_suffix('in_', self.num_bits),
            *bits_suffix('out_', self.num_bits),
            *bits_suffix('not_out_', self.num_bits),
        ]
        self.component_name += f'_{self.num_bits}'

        super().__init__(parent, role)

    def build(self) -> None:
        for i in range(self.num_bits):
            d_latch = self.add_component(latch.DLatch(self, f'latch_{i}'))
            self.connect(f'in_{i}', d_latch.nodes['in'])
            self.connect('write_to_reg', d_latch.nodes['clock'])
            self.connect(f'out_{i}', d_latch.nodes['out'])
            self.connect(f'not_out_{i}', d_latch.nodes['not_out'])
