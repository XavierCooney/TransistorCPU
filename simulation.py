import abc
import typing as typ

import component as comp
import eqn_solver
from netlist import NetList


class SimulatedComponent(abc.ABC):
    @abc.abstractmethod
    def step(self, dt: float, sim: 'Simulation', comp_id: int) -> None: pass


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

    def get_branch_var(self, pos: int, neg: int, comp_id: str) -> str:
        return f'branch_{pos}_to_{neg}__{comp_id}'

    def get_prev_voltage(self, node: int) -> float:
        voltage = self.prev_voltages[node]
        assert voltage is not None
        return voltage

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

    def stamp_voltage_src(
        self, pos: int, neg: int,
        volts: float, comp_id: str
    ) -> None:
        var_name = self.get_branch_var(pos, neg, comp_id)

        self.system.add_term(1, f'{var_name}', f'i{pos}')
        self.system.add_term(-1, f'{var_name}', f'i{neg}')

        self.system.add_term(1, f'v{pos}', f'{var_name}_voltage')
        self.system.add_term(-1, f'v{neg}', f'{var_name}_voltage')
        self.system.add_constant(volts, f'{var_name}_voltage')

    def stamp_abs_volate(self, pos: int, volts: float, comp_id: str) -> None:
        var_name = f'branch_{pos}_gnd__{comp_id}'

        self.system.add_term(1, f'{var_name}', f'i{pos}')

        self.system.add_term(1, f'v{pos}', f'{var_name}_voltage')
        self.system.add_constant(volts, f'{var_name}_voltage')
        # TODO: maybe use variable override? Might be more efficient

    def stamp_capacitor(
        self, a: int, b: int, capacitance: float,
        dt: float, comp_id: str
    ) -> None:
        # value in farads
        var_name = self.get_branch_var(a, b, comp_id)

        self.system.add_term(1, f'{var_name}', f'i{a}')
        self.system.add_term(-1, f'{var_name}', f'i{b}')

        c_on_h = capacitance / dt
        if self.time == 0:
            old_voltage: float = 0
        else:
            v_a, v_b = self.prev_voltages[a], self.prev_voltages[b]
            assert v_a is not None
            assert v_b is not None
            old_voltage = v_a - v_b

        cap_row_name = f'{var_name}_cap_i'
        self.system.add_term(c_on_h, f'v{a}', cap_row_name)
        self.system.add_term(-c_on_h, f'v{b}', cap_row_name)
        self.system.add_term(-1, var_name, cap_row_name)
        self.system.add_constant(c_on_h * old_voltage, cap_row_name)

    def do_stamping(self, dt: float) -> None:
        for hook in self.pre_step_hooks:
            hook(self)

        for comp_id, sim_component in enumerate(self.sim_components):
            sim_component.step(dt, self, comp_id)

    def solve(self, dt: float) -> None:
        # Apply equations to determine the state of the system
        if self.verbose:
            print(self.system.dump_equation())

        solution = self.system.solve()
        assert not self.system.approximated
        if self.verbose:
            print(self.time, solution, '', sep='\n')

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
) -> typ.List[typ.Tuple[float, typ.List[float]]]:
    sim = Simulation(netlist, verbose)

    def handle_inputs(sim: Simulation) -> None:
        for input_id, input_command in enumerate(inputs.items()):
            input_node, input_list = input_command
            node_id = netlist.coalesced_numbering[input_node]
            assert len(input_list) > 0

            for inp_before, inp_after in zip(input_list, input_list[1:]):
                time = sim.time * 1e6
                if not (inp_before[0] <= time <= inp_after[0]):
                    continue

                t = (time - inp_before[0]) / (inp_after[0] - inp_before[0])
                assert 0 <= t <= 1

                voltage = (1 - t) * inp_before[1] + inp_after[1] * t
                sim.stamp_abs_volate(node_id, voltage, f'input_{input_id}')
                break
            else:
                if sim.time >= input_list[-1][0] * 1e-6:
                    sim.stamp_abs_volate(
                        node_id, input_list[-1][1],
                        f'input_{input_id}'
                    )
                else:
                    assert False

    sim.pre_step_hooks.append(handle_inputs)

    all_outputs: typ.List[typ.Tuple[float, typ.List[float]]] = []

    while sim.time < time_stop:
        sim.step(time_step)

        output: typ.List[float] = []
        for node in output_nodes:
            voltage = sim.prev_voltages[netlist.coalesced_numbering[node]]
            assert voltage is not None
            output.append(voltage)

        # print('\n', sim.time, output, '\n')
        all_outputs.append((sim.time, output))

    return all_outputs
