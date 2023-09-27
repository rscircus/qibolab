import itertools

import networkx as nx
import numpy as np
import pytest
from qibo import gates
from qibo.models import Circuit

from qibolab.native import NativeType
from qibolab.transpilers.optimizer import Preprocessing
from qibolab.transpilers.pipeline import (
    Passes,
    TranspilerPipelineError,
    assert_cirucuit_equivalence,
    assert_transpiling,
)
from qibolab.transpilers.placer import Random, ReverseTraversal, Trivial
from qibolab.transpilers.router import ShortestPaths
from qibolab.transpilers.unroller import NativeGates


def generate_random_circuit(nqubits, ngates, seed=None):
    """Generate random circuits one-qubit rotations and CZ gates."""
    pairs = list(itertools.combinations(range(nqubits), 2))
    if seed is not None:  # pragma: no cover
        np.random.seed(seed)

    one_qubit_gates = [gates.RX, gates.RY, gates.RZ, gates.X, gates.Y, gates.Z, gates.H]
    two_qubit_gates = [
        gates.CNOT,
        gates.CZ,
        gates.SWAP,
        gates.iSWAP,
        gates.CRX,
        gates.CRY,
        gates.CRZ,
    ]
    n1, n2 = len(one_qubit_gates), len(two_qubit_gates)
    n = n1 + n2 if nqubits > 1 else n1
    circuit = Circuit(nqubits)
    for _ in range(ngates):
        igate = int(np.random.randint(0, n))
        if igate >= n1:
            q = tuple(np.random.randint(0, nqubits, 2))
            while q[0] == q[1]:
                q = tuple(np.random.randint(0, nqubits, 2))
            gate = two_qubit_gates[igate - n1]
        else:
            q = (np.random.randint(0, nqubits),)
            gate = one_qubit_gates[igate]
        if issubclass(gate, gates.ParametrizedGate):
            theta = 2 * np.pi * np.random.random()
            circuit.add(gate(*q, theta=theta))
        else:
            circuit.add(gate(*q))
    return circuit


def small_circuit():
    circuit = Circuit(2)
    circuit.add(gates.H(0))
    circuit.add(gates.CZ(0, 1))
    return circuit


def star_connectivity():
    Q = ["q" + str(i) for i in range(5)]
    chip = nx.Graph()
    chip.add_nodes_from(Q)
    graph_list = [(Q[i], Q[2]) for i in range(5) if i != 2]
    chip.add_edges_from(graph_list)
    return chip


@pytest.mark.parametrize("ngates", [5, 10, 50])
def test_pipeline_default(ngates):
    circ = generate_random_circuit(nqubits=5, ngates=ngates)
    default_transpiler = Passes(connectivity=star_connectivity())
    transpiled_circ, final_layout = default_transpiler(circ)
    initial_layout = default_transpiler.get_initial_layout()
    assert_transpiling(
        circuit=transpiled_circ,
        connectivity=star_connectivity(),
        initial_layout=initial_layout,
        final_layout=final_layout,
        native_gates=NativeType.CZ,
    )


def test_asser_circuit_equivalence():
    circ1 = Circuit(2)
    circ2 = Circuit(2)
    circ1.add(gates.X(0))
    circ1.add(gates.CZ(0, 1))
    circ2.add(gates.X(0))
    circ2.add(gates.CZ(0, 1))
    assert_cirucuit_equivalence(circ1, circ2)


def test_error_connectivity():
    with pytest.raises(TranspilerPipelineError):
        default_transpiler = Passes()


def test_is_satisfied():
    default_transpiler = Passes(connectivity=star_connectivity())
    circuit = Circuit(5)
    circuit.add(gates.CZ(0, 2))
    circuit.add(gates.Z(0))
    assert default_transpiler.is_satisfied(circuit)


def test_is_satisfied_false_decomposition():
    default_transpiler = Passes(connectivity=star_connectivity())
    circuit = Circuit(5)
    circuit.add(gates.CZ(0, 2))
    circuit.add(gates.X(0))
    assert not default_transpiler.is_satisfied(circuit)


def test_is_satisfied_false_connectivity():
    default_transpiler = Passes(connectivity=star_connectivity())
    circuit = Circuit(5)
    circuit.add(gates.CZ(0, 1))
    circuit.add(gates.Z(0))
    assert not default_transpiler.is_satisfied(circuit)


@pytest.mark.parametrize("circ", [generate_random_circuit(nqubits=5, ngates=20), small_circuit()])
def test_custom_passes(circ):
    custom_passes = []
    custom_passes.append(Preprocessing(connectivity=star_connectivity()))
    custom_passes.append(Random(connectivity=star_connectivity()))
    custom_passes.append(ShortestPaths(connectivity=star_connectivity()))
    custom_passes.append(NativeGates(two_qubit_natives=NativeType.iSWAP))
    custom_pipeline = Passes(custom_passes, connectivity=star_connectivity(), native_gates=NativeType.iSWAP)
    transpiled_circ, final_layout = custom_pipeline(circ)
    initial_layout = custom_pipeline.get_initial_layout()
    assert_transpiling(
        circuit=transpiled_circ,
        connectivity=star_connectivity(),
        initial_layout=initial_layout,
        final_layout=final_layout,
        native_gates=NativeType.iSWAP,
    )


@pytest.mark.parametrize("circ", [generate_random_circuit(nqubits=5, ngates=20), small_circuit()])
def test_custom_passes_reverse(circ):
    custom_passes = []
    custom_passes.append(Preprocessing(connectivity=star_connectivity()))
    custom_passes.append(
        ReverseTraversal(
            connectivity=star_connectivity(),
            routing_algorithm=ShortestPaths(connectivity=star_connectivity()),
            depth=20,
        )
    )
    custom_passes.append(ShortestPaths(connectivity=star_connectivity()))
    custom_passes.append(NativeGates(two_qubit_natives=NativeType.iSWAP))
    custom_pipeline = Passes(custom_passes, connectivity=star_connectivity(), native_gates=NativeType.iSWAP)
    transpiled_circ, final_layout = custom_pipeline(circ)
    initial_layout = custom_pipeline.get_initial_layout()
    assert_transpiling(
        circuit=transpiled_circ,
        connectivity=star_connectivity(),
        initial_layout=initial_layout,
        final_layout=final_layout,
        native_gates=NativeType.iSWAP,
    )


def test_custom_passes_multiple_placer():
    custom_passes = []
    custom_passes.append(Random(connectivity=star_connectivity()))
    custom_passes.append(Trivial(connectivity=star_connectivity()))
    custom_pipeline = Passes(custom_passes, connectivity=star_connectivity(), native_gates=NativeType.CZ)
    circ = generate_random_circuit(nqubits=5, ngates=20)
    with pytest.raises(TranspilerPipelineError):
        transpiled_circ, final_layout = custom_pipeline(circ)


def test_custom_passes_no_placer():
    custom_passes = []
    custom_passes.append(ShortestPaths(connectivity=star_connectivity()))
    custom_pipeline = Passes(custom_passes, connectivity=star_connectivity(), native_gates=NativeType.CZ)
    circ = generate_random_circuit(nqubits=5, ngates=20)
    with pytest.raises(TranspilerPipelineError):
        transpiled_circ, final_layout = custom_pipeline(circ)


def test_custom_passes_wrong_pass():
    custom_passes = [0]
    custom_pipeline = Passes(passes=custom_passes)
    circ = generate_random_circuit(nqubits=5, ngates=5)
    with pytest.raises(TranspilerPipelineError):
        transpiled_circ, final_layout = custom_pipeline(circ)
