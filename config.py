import typing as typ

VOLTAGE = 5
HIGH = 4.7
LOW = 0.3
BITS = 6


def bits_suffix(prefix: str) -> typ.List[str]:
    return [f'{prefix}{i}' for i in range(BITS)]
