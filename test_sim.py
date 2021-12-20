import typing as typ

import simulation
import tester


def run_test(test: tester.Test) -> None:
    # TODO: move the start of this to the tester module
    test.start_test()
    component = test.make_component()
    netlist = test.make_netlist(component)
    piecewise_inputs = test.make_input(component)

    for input_command_list in piecewise_inputs.values():
        assert input_command_list[-1][0] < test.test_length_us

    output_nodes = list(set(tester.component_nodes_by_name(
        component, test.output_nodes
    )) | set(piecewise_inputs.keys()))

    output_node_names = [output_node.name for output_node in output_nodes]

    time_step = 80e-9

    output_data = simulation.simulate(
        netlist, piecewise_inputs, output_nodes,
        time_step=time_step, time_stop=(test.test_length_us * 1e-6),
        verbose=test.verbose
    )

    if test.interactive:
        # delay import incase matplotlib not installed
        import matplotlib.pyplot as plt  # type: ignore
        sim_times = [output[0] for output in output_data]

        fig, ax = plt.subplots()
        ax.set_xlabel('time')

        for node_num, node in enumerate(output_nodes):
            node_data = [
                output_line[1][node_num]
                for output_line in output_data
            ]
            line, = ax.plot(sim_times, node_data)
            line.set_label(node)

        ax.legend()
        plt.show()

    def find_output_data(required_time: float) -> typ.Dict[str, float]:
        # binary search for the data at a given time
        start = 0
        end = len(output_data)

        while start + 1 < end:
            mid = (start + end) // 2
            if output_data[mid][0] < required_time:
                start = mid
            else:
                end = mid

        if abs(output_data[start][0] - required_time) > time_step * 2:
            print(f"Can't find data at time {required_time}")
            assert False

        return dict(zip(output_node_names, output_data[start][1]))

    test.check_output(component, find_output_data)
