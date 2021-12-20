import config
from simulation import SimulatedComponent, Simulation


class SimulatedMosfet(SimulatedComponent):
    # OK so I think I know how to actually simulate a MOSFET
    # using Newton-Raphson to do non-linear iteration of these
    # components to converge each time, step, but really that feels
    # like a lot of effort. So instead for right now I'll just
    # use a really crude model and see if it kind of works.

    def __init__(self, drain: int, gate: int, source: int) -> None:
        self.charge = config.VOLTAGE / 2
        self.drain = drain
        self.gate = gate
        self.source = source

    def step(self, dt: float, sim: Simulation, comp_id: int) -> None:
        # TODO: make this actually kind of correct
        sim.stamp_capacitor(
            self.gate, self.source,
            50 * 10**-12, dt,
            f'{comp_id}c1'
        )

        if sim.time == 0:
            # start off high resistance
            sim.stamp_resistor(self.drain, self.source, 10 * 10 ** 6)  # 10M
        else:
            v_gate = sim.get_prev_voltage(self.gate)
            v_drain = sim.get_prev_voltage(self.drain)
            v_source = sim.get_prev_voltage(self.source)

            vgs = v_gate - v_source
            assert v_drain - v_source >= -10

            if vgs > 3:
                sim.stamp_resistor(self.drain, self.source, 5.3)
            else:
                sim.stamp_resistor(self.drain, self.source, 200e3)


class SimulatedResistor(SimulatedComponent):
    def __init__(self, a: int, b: int, value: float) -> None:
        self.a = a
        self.b = b
        self.value = value

    def step(self, dt: float, sim: Simulation, comp_id: int) -> None:
        sim.stamp_resistor(self.a, self.b, self.value)


class SimulatedVoltage(SimulatedComponent):
    def __init__(self, a: int, value: float) -> None:
        self.a = a
        self.value = value

    def step(self, dt: float, sim: Simulation, comp_id: int) -> None:
        sim.stamp_abs_volate(self.a, self.value, str(comp_id))


class SimulatedCapacitor(SimulatedComponent):
    def __init__(self, a: int, b: int, value: float) -> None:
        self.a = a
        self.b = b
        self.value = value

    def step(self, dt: float, sim: Simulation, comp_id: int) -> None:
        sim.stamp_capacitor(self.a, self.b, self.value, dt, str(comp_id))
