import math

import matplotlib.pyplot as plt  # type: ignore

import simulation
from discrete_components import TempTestComponent
from netlist import NetList

component = TempTestComponent(None, 'main')
netlist = NetList.make(component)
print(netlist.dump_info())

all_outputs = simulation.simulate(netlist, {}, [
    component.nodes['v'], component.nodes['a'], component.nodes['gnd']
], time_step=10e-9, time_stop=9e-6)

assert math.isclose(all_outputs[-1][1][component.nodes['v']], 5)
print(component)

# print(all_outputs[:5])

sim_times = [output[0] for output in all_outputs]

fig, ax = plt.subplots()
ax.set_xlabel('time')

for node in all_outputs[-1][1]:
    line, = ax.plot(sim_times, [output[1][node] for output in all_outputs])
    line.set_label(node.name)

ax.legend()

plt.show()
