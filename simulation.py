import abc
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

    def __init__(self, netlist: NetList, verbose: bool):
        self.verbose = verbose

        self.netlist = netlist
        self.num_nodes = len(netlist.coalesced_nodes)
        self.time: float = 0
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
        self.system.add_term(-1, f'{var_name}', f'i{neg}')

        self.system.add_term(1, f'v{pos}', f'{var_name}-voltage')
        self.system.add_term(-1, f'v{neg}', f'{var_name}-voltage')

    def stamp_abs_volate(self, pos: int, volts: float) -> None:
        var_name = f'branch-{pos}-gnd'

        self.system.add_term(1, f'{var_name}', f'i{pos}')
        # self.system.add_term(-1, f'{var_name}', f'i{neg}')

        self.system.add_term(1, f'v{pos}', f'{var_name}-voltage')
        self.system.add_constant(volts, f'{var_name}-voltage')
        # self.system.override_variable(f'v{pos}', volts)

    def stamp_capacitor(self, a: int, b: int, value: float, dt: float) -> None:
        # value in farads
        multiplier, var_name = self.get_branch_i_var_and_coefficient(a, b)
        # value *= multiplier

        self.system.add_term(1, f'{var_name}', f'i{a}')
        self.system.add_term(-1, f'{var_name}', f'i{b}')

        c_on_h = value / dt
        if self.time == 0:
            old_voltage: float = 0
        else:
            v_a, v_b = self.prev_voltages[a], self.prev_voltages[b]
            assert v_a is not None
            assert v_b is not None
            old_voltage = v_a - v_b

        self.system.add_term(c_on_h, f'v{a}', f'{var_name}-cap-i')
        self.system.add_term(-c_on_h, f'v{b}', f'{var_name}-cap-i')
        self.system.add_term(-1, f'{var_name}', f'{var_name}-cap-i')
        self.system.add_constant(c_on_h * old_voltage, f'{var_name}-cap-i')

    def get_prev_voltage(self, node: int) -> float:
        assert False
        # return self.prev_voltages[node]

    def do_stamping(self, dt: float) -> None:
        for hook in self.pre_step_hooks:
            hook(self)

        for sim_component in self.sim_components:
            sim_component.step(dt, self)

    def solve(self, dt: float) -> None:
        # Apply equations to determine the state of the system
        if self.verbose:
            print(self.system.dump_equation())

        solution = self.system.solve()
        assert not self.system.approximated
        if self.verbose:
            print(solution, '', sep='\n')

        self.prev_voltages = [None] * self.num_nodes
        for var_name, value in solution.items():
            if var_name[0] == 'v':
                self.prev_voltages[int(var_name[1:])] = value
            else:
                # print(f'... {var_name=} {value=}')
                pass

    def step(self, dt: float) -> None:
        self.system = eqn_solver.System()
        self.do_stamping(dt)
        self.solve(dt)
        self.time += dt


def simulate(
    netlist: NetList,
    inputs: typ.Dict['comp.Node', typ.List[typ.Tuple[float, float]]],
    output_nodes: typ.List['comp.Node'],
    time_step: float = 5e-9,
    time_stop: float = 5e-6,
    verbose: bool = False
) -> typ.List[typ.Tuple[float, typ.Dict['comp.Node', float]]]:
    sim = Simulation(netlist, verbose)

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

    all_outputs: typ.List[typ.Tuple[float, typ.Dict['comp.Node', float]]] = []

    while sim.time < time_stop:
        sim.step(time_step)

        output: typ.Dict['comp.Node', float] = {}
        for node in output_nodes:
            voltage = sim.prev_voltages[netlist.coalesced_numbering[node]]
            assert voltage is not None
            output[node] = voltage

        # print('\n', sim.time, output, '\n')
        all_outputs.append((sim.time, output))

    return all_outputs
