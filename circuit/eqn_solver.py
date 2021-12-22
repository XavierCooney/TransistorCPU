# A small module to solve sytems of linear equations for custom sim
import math
import typing as typ
import warnings

import numpy as np
import scipy.sparse  # type: ignore
import scipy.sparse.linalg  # type: ignore


class System:
    def __init__(self) -> None:
        self.vars: typ.Dict[str, int] = {}
        self.rows: typ.Dict[str, int] = {}

        self.row_entries: typ.List[int] = []
        self.col_entries: typ.List[int] = []
        self.data_entries: typ.List[float] = []
        self.const_vec: typ.List[float] = []

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

        self.row_entries.append(row_var)
        self.col_entries.append(term_var)
        self.data_entries.append(coeff)

    def add_constant(self, constant: float, row_var_name: str) -> None:
        row_var = self.row_index(row_var_name)
        self.const_vec[row_var] += constant

    def make_matrix(self):  # type: ignore
        num_rows = len(self.rows)
        num_vars = len(self.vars)
        assert num_rows == num_vars

        return scipy.sparse.coo_matrix(
            (self.data_entries, (self.row_entries, self.col_entries)),
            shape=(num_rows, num_vars)
        )

    def dump_equation(self) -> str:
        lines = [[f'{row_name:>20})'] for row_name in self.rows]

        var_idx_to_name = {}
        for var_name, var_idx in self.vars.items():
            var_idx_to_name[var_idx] = var_name

        matrix = self.make_matrix().tolil()  # type: ignore

        coords_already_done = set()

        for row, col in zip(self.row_entries, self.col_entries):
            if (row, col) in coords_already_done:
                continue
            coords_already_done.add((row, col))

            coeff = matrix[row, col]
            if math.isclose(coeff, 0):
                continue

            if lines[row][-1][-1] != ')':  # TODO: yuck
                lines[row].append('+')

            lines[row].append(f'{coeff} * {var_idx_to_name[col]}')

        for row_id, constant in enumerate(self.const_vec):
            lines[row_id].append(f'= {constant}')

        return '\n'.join(map(' '.join, lines)) + '\n'

    def sparse_matrix_solve(self, A, b):  # type: ignore
        USE_PYPARDISO = False  # it actually seems to be slower?>>
        if USE_PYPARDISO:
            try:
                import pypardiso  # type: ignore
                solution = pypardiso.spsolve(A.tocsc(), b)
                return solution
            except ImportError:
                warnings.warn("Can't import pypardiso")

        try:
            solution = scipy.sparse.linalg.spsolve(A.tocsc(), b)
        except RuntimeError:
            import traceback
            traceback.print_exc()
            print()
            print('=' * 80)
            print()
            solution = scipy.sparse.linalg.lsqr(A, b)
            self.approximated = True
            warnings.warn("Approximating sparse matrix solve!")

        return solution

    def solve(self) -> typ.Dict[str, float]:
        b_vec = np.array(self.const_vec)
        matrix = self.make_matrix()  # type: ignore

        solution = self.sparse_matrix_solve(
            matrix, b_vec
        )  # type: ignore

        return {
            var_name: solution[var_index]
            for var_name, var_index in self.vars.items()
        }


if __name__ == '__main__':
    # x = 5, y = -7
    # 2x + 3y = -11   (1)
    #  x -  y =  12   (2)

    system = System()

    system.add_term(2, 'x', '1')
    system.add_term(3, 'y', '1')
    system.add_constant(-11, '1')

    system.add_term(-1, 'y', '2')
    system.add_term(1, 'x', '2')
    system.add_constant(12, '2')

    print(system.dump_equation())

    result = system.solve()

    print(result)

    assert math.isclose(result['x'], 5)
    assert math.isclose(result['y'], -7)
    assert not system.approximated
