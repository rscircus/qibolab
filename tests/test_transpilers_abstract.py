import pytest
from qibo import gates
from qibo.models import Circuit

from qibolab.transpilers.abstract import create_circuit_repr


def test_circuit_representation():
    circuit = Circuit(5)
    circuit.add(gates.CNOT(1, 0))
    circuit.add(gates.CNOT(2, 0))
    circuit.add(gates.X(1))
    circuit.add(gates.CZ(3, 0))
    circuit.add(gates.CNOT(4, 0))
    repr = create_circuit_repr(circuit)
    assert repr == [[0, i + 1] for i in range(4)]


def test_circuit_representation_fail():
    circuit = Circuit(5)
    circuit.add(gates.TOFFOLI(0, 1, 2))
    with pytest.raises(ValueError):
        repr = create_circuit_repr(circuit)