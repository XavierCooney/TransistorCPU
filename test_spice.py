import os
import subprocess
import typing as typ

import spice
import tester

us = 1e-6
ns = 1e-9
SPICE_ENCODING = 'utf-8'


def process_spice_output(
    output_names: typ.List[str]
) -> typ.Callable[[float], typ.Dict[str, float]]:
    with open('spice_script/out.data') as out_file:
        lines = out_file.read().split('\n')

    while lines[-1] == '':
        lines = lines[:-1]
    lines = lines[1:]  # header row

    output_data: typ.List[typ.Tuple[float, typ.List[float]]] = []

    for line in lines:
        assert len(line) == 2 * 16 * len(output_names)

        segments = [
            float(line[i * 16:(i + 1) * 16].strip())
            for i in range(len(output_names) * 2)
        ]
        time = segments[0]
        assert all(segment == time for segment in segments[::2])

        output_data.append((time, segments[1::2]))

    assert list(sorted(output_data)) == output_data

    REQUIRED_INCREMENT = 20 * 10 ** -9

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

        if abs(output_data[start][0] - required_time) > REQUIRED_INCREMENT:
            print(f"Can't find data at time {required_time}")
            assert False

        return dict(zip(output_names, output_data[start][1]))

    return find_output_data


def run_spice_script(
    source: str, interactive: bool,
    outputs: typ.List[str], verbose: bool,
    flash_graph: bool
) -> typ.Callable[[float], typ.Dict[str, float]]:
    if verbose:
        print(source)

    with open('spice_script/script.cir', 'w') as spice_file:
        spice_file.write(source)

    with open('spice_script/out.data', 'w') as out_file:
        out_file.write('')

    if flash_graph or interactive:
        # TODO: *nix support for this
        output = subprocess.check_output(
            ['spice64\\bin\\ngspice.exe', 'script.cir'],
            cwd=os.path.abspath('spice_script'),
            encoding='utf-8'
        )
        if verbose and output:
            print("Windowed output: ", output)

    if not interactive:
        completed_process = subprocess.run(
            ['spice64\\bin\\ngspice_con.exe', '-b', 'script.cir'],
            cwd=os.path.abspath('spice_script'),
            encoding=SPICE_ENCODING, check=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )

        stdout = completed_process.stdout
        stderr = completed_process.stderr

        if verbose and stdout:
            print('Console stdout:', stdout, sep='\n')

        if verbose and stderr:
            print('Console stderr:', stderr, sep='\n')

        ALLOWED_MESSAGES = {
            "Note: can't find init file.",
            'ERROR: (internal)  This operation is not '
            'defined for display type PrinterOnly.',
            "Can't open viewport for graphics."
        }
        for line in stderr.split('\n'):
            if not line:
                continue
            elif line in ALLOWED_MESSAGES:
                continue
            elif line.startswith(' Reference value :  '):
                continue
            else:
                print("Unknown stderr line:", line)
                assert False

        return process_spice_output(outputs)

    else:  # interactive
        def no_data(time: float) -> typ.NoReturn:
            assert False
        return no_data


def run_test(test: 'tester.Test') -> None:
    test.start_test()
    component = test.make_component()
    netlist = test.make_netlist(component)
    piecewise_inputs = test.make_input(component)

    for input_command_list in piecewise_inputs.values():
        assert input_command_list[-1][0] < test.test_length_us

    output_nodes = list(set(tester.component_nodes_by_name(
        component, test.output_nodes
    )) | set(piecewise_inputs.keys()))

    interactive_runs = [True, False] if test.interactive else [False]

    for interactive in interactive_runs:
        spice_src, output_list = spice.make_spice_script(
            test.test_name, netlist, piecewise_inputs,
            output_nodes, '5ns', f'{test.test_length_us}us',
            input_time_suffix='us', output_data=not interactive
        )  # TODO: make more of these params test-specifiable

        check_data = run_spice_script(
            spice_src, interactive, output_list, test.verbose,
            test.verbose
        )

        if not interactive:
            test.check_output(component, check_data)
