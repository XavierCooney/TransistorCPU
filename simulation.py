import abc
import math
import typing as typ

import component as comp
import eqn_solver
from netlist import NetList


class SimulatedComponent(abc.ABC):
    @abc.abstractmethod
    def step(self, dt: float, sim: 'Simulation') -> None: pass


class Simulation:
    # This kind of blew out of proportion
    # Modified nodal analysis:
    # https://aice.sjtu.edu.cn/msda/data/courseware/SPICE/lect07_element_stamping.pdf

    def __init__(self, netlist: NetList):
        self.netlist = netlist
        self.num_nodes = len(netlist.coalesced_nodes)
        self.time = 0
        self.pre_step_hooks: typ.List[typ.Callable[['Simulation'], None]] = []

        self.sim_components: typ.List[SimulatedComponent] = []
        for component in netlist.atomic_componenets:
            self.sim_components.append(component.make_sim_component(netlist))

        VoltageListType = typ.List[typ.Optional[float]]
        self.prev_voltages: VoltageListType = [None] * self.num_nodes
        self.prev_prev_voltages: VoltageListType = [None] * self.num_nodes

        self.system = eqn_solver.System()

    def get_branch_i_var_and_coefficient(
        self, pos: int, neg: int
    ) -> typ.Tuple[float, str]:
        # TODO: you can have one branch and multiple components?
        # assert pos != neg  # weird case

        if pos > neg:
            return 1, f'branch-{pos}-{neg}'
        else:
            return -1, f'branch-{neg}-{pos}'

    def stamp_resistor(self, pos: int, neg: int, ohms: float) -> None:
        assert ohms > 0
        conductance = 1 / ohms
        self.system.add_term(conductance, f'v{pos}', f'i{pos}')
        self.system.add_term(-conductance, f'v{neg}', f'i{pos}')
        self.system.add_term(-conductance, f'v{pos}', f'i{neg}')
        self.system.add_term(conductance, f'v{neg}', f'i{neg}')

    def stamp_current_src(self, pos: int, neg: int, amps: float) -> None:
        # swapped because current is +ve for going in
        self.system.add_constant(-amps, f'i{pos}')
        self.system.add_constant(amps, f'i{neg}')

    def stamp_voltage_src(self, pos: int, neg: int, volts: float) -> None:
        multiplier, var_name = self.get_branch_i_var_and_coefficient(pos, neg)
        volts *= multiplier

        self.system.add_term(1, f'{var_name}', f'i{pos}')
        self.system.add_term(-1, f'{var_name}', f'i{pos}')

        self.system.add_term(1, f'v{pos}', f'{var_name}-voltage')
        self.system.add_term(-1, f'v{neg}', f'{var_name}-voltage')
        self.system.add_constant(5, f'{var_name}-voltage')

    def stamp_abs_volate(self, pos: int, volts: float) -> None:
        var_name = f'branch-{pos}-gnd'

        self.system.add_term(1, f'{var_name}', f'i{pos}')
        # self.system.add_term(-1, f'{var_name}', f'i{neg}')

        self.system.add_term(1, f'v{pos}', f'{var_name}-voltage')
        self.system.add_constant(volts, f'{var_name}-voltage')
        # self.system.override_variable(f'v{pos}', volts)

    def get_prev_voltage(self, node: int) -> float:
        assert False
        # return self.prev_voltages[node]

    def do_stamping(self, dt: float) -> None:
        for hook in self.pre_step_hooks:
            hook(self)

        for sim_component in self.sim_components:
            sim_component.step(dt, self)

        # self.system.override_variable('v0', 0)

    def solve(self, dt: float) -> None:
        # Apply equations to determine the state of the system
        print(self.system.dump_equation())
        print()
        solution = self.system.solve()
        print(solution)

        self.prev_voltages = [None] * self.num_nodes
        for var_name, value in solution.items():
            if var_name[0] == 'v':
                self.prev_voltages[int(var_name[1:])] = value
            else:
                print(f'... {var_name=} {value=}')

    def step(self, dt: float) -> None:
        self.do_stamping(dt)
        self.solve(dt)


def simulate(
    netlist: NetList,
    inputs: typ.Dict['comp.Node', typ.List[typ.Tuple[float, float]]],
    output_nodes: typ.List['comp.Node'],
    time_step: float = 1e-3,
    time_stop: float = 5,
) -> typ.Dict['comp.Node', float]:
    sim = Simulation(netlist)

    def handle_inputs(sim: Simulation) -> None:
        for input_node, input_list in inputs.items():
            node_id = netlist.coalesced_numbering[input_node]
            assert len(input_list) > 0

            input_voltage = None
            for input_time, input_voltage in input_list:
                if sim.time > input_time:
                    break

            if input_voltage is not None:
                sim.stamp_abs_volate(node_id, input_voltage)

    sim.pre_step_hooks.append(handle_inputs)

    sim.step(time_step)
    print(sim.prev_voltages)

    output: typ.Dict['comp.Node', float] = {}
    for node in output_nodes:
        voltage = sim.prev_voltages[netlist.coalesced_numbering[node]]
        assert voltage is not None
        output[node] = voltage

    return output


if __name__ == '__main__':
    from component import Component
    from transistor import Ground, Resistor, Vdd

    class TestComponent(Component):
        # Voltage divider
        node_names = ['v', 'gnd', 'a']
        component_name = 'test'

        def build(self) -> None:
            voltage_source = self.add_component(Vdd(self, 'vdd'))
            ground = self.add_component(Ground(self, 'gnd'))
            r1 = self.add_component(Resistor(self, 'R1').set_resistance(1))
            r2 = self.add_component(Resistor(self, 'R2').set_resistance(3))

            self.connect('v', voltage_source.nodes['a'])
            self.connect('v', r1.nodes['a'])
            self.connect('a', r1.nodes['b'])
            self.connect('a', r2.nodes['a'])
            self.connect('gnd', r2.nodes['b'])
            # self.connect('gnd', r1.nodes['b'])
            self.connect('gnd', ground.nodes['a'])

    component = TestComponent(None, 'main')
    netlist = NetList.make(component)
    print(netlist.dump_info())

    final_output = simulate(netlist, {}, [
        component.nodes['v'], component.nodes['a'], component.nodes['gnd']
    ])
    print(final_output)

    assert math.isclose(final_output[component.nodes['v']], 5)
    print(component)
