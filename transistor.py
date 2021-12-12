import typing as typ

from component import AtomicComponent


class NTypeMosfet(AtomicComponent):
    node_names = ['gate', 'drain', 'source']
    component_name = 'nmos'

    def build(self) -> None: pass

    def ngspice_line(self, comp_id: str, nodes: typ.Dict[str, str]) -> str:
        return (
            f'X{comp_id} {nodes["drain"]} '
            f'{nodes["gate"]} {nodes["source"]} 2N7000'
        )


class PullUpResistor(AtomicComponent):
    node_names = ['a']
    component_name = 'pullup_resistor'

    def build(self) -> None: pass

    def ngspice_line(self, comp_id: str, nodes: typ.Dict[str, str]) -> str:
        PULLUP_RESISTANCE = '10k'
        return f'R{comp_id} {nodes["a"]} vdd {PULLUP_RESISTANCE}'


class Ground(AtomicComponent):
    node_names = ['a']
    component_name = 'gnd'

    def build(self) -> None: pass

    def ngspice_line(self, comp_id: str, nodes: typ.Dict[str, str]) -> str:
        # 0 voltage source = short circuit
        return f'V{comp_id} {nodes["a"]} gnd 0'
