# A small module to solve sytems of linear equations for custom sim
import math
import typing as typ
from collections import defaultdict


class System:
    def __init__(self) -> None:
        self.vars: typ.Dict[str, int] = {}
        self.rows: typ.Dict[str, int] = {}

        MatEntryType = typ.Dict[typ.Tuple[int, int], float]
        # self.mat_entries indexed by (row, col)
        self.mat_entries: MatEntryType = defaultdict(int)
        self.const_vec: typ.List[float] = []

        self.variable_overrides: typ.Dict[int, float] = {}

        self.approximated = False

    def var_index(self, var: str) -> int:
        if var not in self.vars:
            self.vars[var] = len(self.vars)

        return self.vars[var]

    def row_index(self, row_name: str) -> int:
        if row_name not in self.rows:
            self.rows[row_name] = len(self.rows)

            while len(self.const_vec) < len(self.rows):
                self.const_vec.append(0)

        return self.rows[row_name]

    def add_term(
        self, coeff: float, term_var_name: str, row_var_name: str
    ) -> None:
        term_var = self.var_index(term_var_name)
        row_var = self.row_index(row_var_name)

        self.mat_entries[(row_var, term_var)] += coeff

    def add_constant(self, constant: float, row_var_name: str) -> None:
        row_var = self.row_index(row_var_name)
        self.const_vec[row_var] += constant

    def override_variable(self, var_name: str, value: float) -> None:
        # TODO: do this better
        var = self.var_index(var_name)
        if var in self.variable_overrides:
            assert self.variable_overrides[var] == value
        self.variable_overrides[var] = value

    def dump_equation(self) -> str:
        lines = [[f'{row_name:>20})'] for row_name in self.rows]

        var_idx_to_name = {}
        for var_name, var_idx in self.vars.items():
            var_idx_to_name[var_idx] = var_name

        for coord, coeff in self.mat_entries.items():
            if math.isclose(coeff, 0):
                continue
            if lines[coord[0]][-1][-1] != ')':  # TODO: yuck
                lines[coord[0]].append('+')
            lines[coord[0]].append(f'{coeff} * {var_idx_to_name[coord[1]]}')

        for row_id, constant in enumerate(self.const_vec):
            lines[row_id].append(f'= {constant}')

        return '\n'.join(map(' '.join, lines)) + '\n'

    def solve(self) -> typ.Dict[str, float]:
        # Delay import so no issue if sim not invoked
        import numpy
        import scipy.sparse  # type: ignore
        import scipy.sparse.linalg  # type: ignore

        # print(self.vars, self.rows, self.mat_entries)

        num_rows = len(self.rows)
        num_vars = len(self.vars) - len(self.variable_overrides)
        assert num_rows == num_vars

        var_renumbering: typ.Dict[int, int] = {}
        for var_name, old_var_num in self.vars.items():
            if old_var_num not in self.variable_overrides:
                var_renumbering[old_var_num] = len(var_renumbering)

        b_vec = numpy.zeros((num_rows,))
        for index, constant in enumerate(self.const_vec):
            b_vec[index] = constant

        # TODO: construct the sparse matrix better?
        matrix = scipy.sparse.lil_matrix((num_rows, num_vars))
        for coord, coefficient in self.mat_entries.items():
            row_var, term_var = coord
            if term_var in self.variable_overrides:
                actual_val = coefficient * self.variable_overrides[term_var]
                b_vec[coord[0]] -= actual_val
            else:
                matrix[(row_var, var_renumbering[term_var])] = coefficient

        # print(matrix, b_vec, sep='\n')

        try:
            solution = scipy.sparse.linalg.spsolve(matrix.tocsr(), b_vec)
        except RuntimeError:
            import traceback
            traceback.print_exc()
            print()
            print('=' * 80)
            print()
            solution = scipy.sparse.linalg.lsqr(matrix.tocsr(), b_vec)
            self.approximated = True

        final_result = {
            var_name: solution[var_renumbering[var_index]]
            for var_name, var_index in self.vars.items()
            if var_index not in self.variable_overrides
        }
        final_result.update({
            var_name: self.variable_overrides[var_index]
            for var_name, var_index in self.vars.items()
            if var_index in self.variable_overrides
        })

        return final_result


if __name__ == '__main__':
    # x = 5, y = -7, z = 2
    # 2x + 3y +  z = -9   (1)
    #  x -  y - 3z =  6   (2)

    system = System()

    system.add_term(2, 'x', '1')
    system.add_term(3, 'y', '1')
    system.add_term(1, 'z', '1')
    system.add_constant(-9, '1')

    system.add_term(-1, 'y', '2')
    system.add_term(1, 'x', '2')
    system.add_term(-3, 'z', '2')
    system.add_constant(6, '2')

    system.override_variable('z', 2)

    print(system.dump_equation())

    result = system.solve()

    print(result)

    assert len(result) == 3
    assert math.isclose(result['x'], 5)
    assert math.isclose(result['y'], -7)
    assert math.isclose(result['z'], 2)
    assert not system.approximated
