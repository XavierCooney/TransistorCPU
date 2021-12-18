import config
from simulation import SimulatedComponent, Simulation


class SimulatedMosfet(SimulatedComponent):
    def __init__(self, drain: int, gate: int, source: int) -> None:
        self.charge = config.VOLTAGE / 2
        self.drain = drain
        self.gate = gate
        self.source = source

    def step(self, dt: float, sim: Simulation, comp_id: int) -> None:
        raise TypeError()


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
