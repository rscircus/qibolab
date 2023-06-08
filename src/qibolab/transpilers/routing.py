import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
from more_itertools import pairwise
from qibo import gates
from qibo.config import log, raise_error
from qibo.models import Circuit

from qibolab.transpilers.abstract import Transpiler, create_circuit_repr
from qibolab.transpilers.placer import Trivial, assert_placement


def respect_connectivity(connectivity, circuit, verbose=False):
    """Checks if a circuit can be executed on Hardware.

    Args:
        circuit (qibo.models.Circuit): Circuit model to check.
        connectivity (networkx.graph): chip connectivity.
        verbose (bool): If ``True`` it prints info messages.

    Returns ``True`` if the following conditions are satisfied:
        - Circuit does not contain more than two-qubit gates.
        - Circuit matches connectivity.
    otherwise returns ``False``.
    """

    for gate in circuit.queue:
        if len(gate.qubits) > 2 and not isinstance(gate, gates.M):
            if verbose:
                log.info(f"{gate.name} acts on more than two qubits.")
            return False
        elif len(gate.qubits) == 2:
            if ("q" + str(gate.qubits[0]), "q" + str(gate.qubits[1])) not in connectivity.edges:
                if verbose:
                    log.info("Circuit does not respect connectivity. " f"{gate.name} acts on {gate.qubits}.")
                return False
    if verbose:
        log.info("Circuit respects connectivity.")
    return True


def remap_circuit(circuit, qubit_map):
    """Map logical to physical qubits in a circuit

    Args:
        circuit (:class:`qibo.models.Circuit`): qibo circuit to be remapped.
        qubit_map (np.array): new qubit mapping.

    Returns:
        new_circuit (:class:`qibo.models.Circuit`): transpiled circuit mapped with initial qubit mapping.
    """
    new_circuit = Circuit(circuit.nqubits)
    for gate in circuit.queue:
        new_circuit.add(gate.on_qubits({q: qubit_map[q] for q in gate.qubits}))
    return new_circuit


class ShortestPaths(Transpiler):
    """A class to perform initial qubit mapping and connectivity matching.

    Properties:
        sampling_split (float): fraction of paths tested (between 0 and 1).

    Attributes:
        connectivity (networkx.Graph): chip connectivity.
        verbose (bool): print info messages.
        initial_layout (dict): initial physical to logical qubit mapping
        added_swaps (int): number of swaps added to the circuit to match connectivity.
        _circuit_repr (list): quantum circuit represented as a list (only 2 qubit gates).
        _mapping (dict): circuit to physical qubit mapping during transpiling.
        _graph (networkx.graph): qubit mapped as nodes of the connectivity graph.
        _qubit_map (np.array): circuit to physical qubit mapping during transpiling as vector.
        _circuit_position (int): position in the circuit.

    """

    def __init__(self, connectivity: nx.Graph, sampling_split=1.0, verbose=False):
        """Args:
        connectivity (networkx.graph): chip connectivity.
        sampling_split (float): fraction of paths tested (between 0 and 1).
        verbose(bool): print info messages.

        """
        self.connectivity = connectivity
        self.sampling_split = sampling_split
        self.verbose = verbose
        self.initial_layout = None
        self.added_swaps = 0
        self.final_map = None
        self._circuit_repr = None
        self._mapping = None
        self._graph = None
        self._qubit_map = None
        self._transpiled_circuit = None
        self._circuit_position = 0

    # TODO: This may become a stand alone function
    def is_satisfied(self, circuit):
        """Checks if a circuit can be executed on Hardware.

        Args:
            circuit (qibo.models.Circuit): Circuit model to check.

        Returns ``True`` if the following conditions are satisfied:
            - Circuit does not contain more than two-qubit gates.
            - Circuit matches connectivity.
            otherwise returns ``False``.
        """
        return respect_connectivity(connectivity=self.connectivity, circuit=circuit, verbose=self.verbose)

    def __call__(self, circuit, initial_layout):
        """Circuit connectivity matching.

        Args:
            circuit (:class:`qibo.models.Circuit`): circuit to be matched to hardware connectivity.
            initial_layout (dict): initial qubit mapping.

        Returns:
            hardware_mapped_circuit (qibo.Circuit): circut mapped to hardware topology.
            final_mapping (dict): final qubit mapping.
        """
        self._mapping = initial_layout
        init_qubit_map = np.asarray(list(initial_layout.values()))
        self.initial_checks(circuit.nqubits)
        self._circuit_repr = create_circuit_repr(circuit)
        self._graph = nx.relabel_nodes(self.connectivity, self._mapping)
        self._qubit_map = np.sort(init_qubit_map)
        self.first_transpiler_step(circuit)
        while len(self._circuit_repr) != 0:
            self.transpiler_step(circuit)
        final_mapping = {
            key: self._qubit_map[init_qubit_map[i]] for i, key in enumerate(list(self.connectivity.nodes()))
        }
        hardware_mapped_circuit = remap_circuit(self._transpiled_circuit, np.argsort(init_qubit_map))
        return hardware_mapped_circuit, final_mapping

    def transpiler_step(self, qibo_circuit):
        """Transpilation step. Find new mapping, add swap gates and apply gates that can be run with this configuration.

        Args:
            qibo_circuit (:class:`qibo.models.Circuit`): circuit to be transpiled.
        """
        len_2q_circuit = len(self._circuit_repr)
        path, meeting_point = self.relocate()
        self.add_swaps(path, meeting_point)
        self.update_qubit_map()
        self.add_gates(qibo_circuit, len_2q_circuit - len(self._circuit_repr))

    def first_transpiler_step(self, qibo_circuit):
        """First transpilation step. Apply gates that can be run with the initial qubit mapping.

        Args:
            qibo_circuit (:class:`qibo.models.Circuit`): circuit to be transpiled.
        """
        self._circuit_position = 0
        self.added_swaps = 0
        len_2q_circuit = len(self._circuit_repr)
        self._circuit_repr = self.reduce(self._graph)
        self.add_gates(qibo_circuit, len_2q_circuit - len(self._circuit_repr))

    @property
    def sampling_split(self):
        return self._sampling_split

    @sampling_split.setter
    def sampling_split(self, sampling_split):
        """Set the sampling split.

        Args:
            sampling_split (float): define fraction of shortest path tested.
        """

        if sampling_split > 0.0 and 1.0 >= sampling_split:
            self._sampling_split = sampling_split
        else:
            raise_error(ValueError, "Sampling_split must be in (0:1]")

    def draw_connectivity(self):  # pragma: no cover
        """Draw connectivity graph."""
        pos = nx.spectral_layout(self.connectivity)
        nx.draw(self.connectivity, pos=pos, with_labels=True)
        plt.show()

    def reduce(self, graph):
        """Reduce the circuit, delete a 2-qubit gate if it can be applied on the current configuration.

        Args:
            graph (networkx.Graph): current hardware qubit mapping.

        Returns:
            new_circuit (list): reduced circuit.
        """
        new_circuit = self._circuit_repr.copy()
        while new_circuit != [] and (new_circuit[0][0], new_circuit[0][1]) in graph.edges():
            del new_circuit[0]
        return new_circuit

    def map_list(self, path):
        """Return all possible walks of qubits, or a fraction, for a given path.

        Args:
            path (list): path to move qubits.

        Returns:
            mapping_list (list): all possible walks of qubits, or a fraction of them based on self.sampling_split, for a given path.
            meeting_point_list (list): qubit meeting point for each path.
        """
        path_ends = [path[0], path[-1]]
        path_middle = path[1:-1]
        mapping_list = []
        meeting_point_list = []
        test_paths = list(range(len(path) - 1))
        if self.sampling_split != 1.0:
            test_paths = np.random.choice(
                test_paths, size=int(np.ceil(len(test_paths) * self.sampling_split)), replace=False
            )
        for i in test_paths:
            values = path_middle[:i] + path_ends + path_middle[i:]
            mapping = dict(zip(path, values))
            mapping_list.append(mapping)
            meeting_point_list.append(i)
        return mapping_list, meeting_point_list

    def relocate(self):
        """A small greedy algorithm to decide which path to take, and how qubits should walk.

        Returns:
            final_path (list): best path to move qubits.
            meeting_point (int): qubit meeting point in the path.
        """
        nodes = self._graph.number_of_nodes()
        circuit = self.reduce(self._graph)
        final_circuit = circuit
        keys = list(range(nodes))
        final_graph = self._graph
        final_mapping = dict(zip(keys, keys))
        # Consider all shortest paths
        path_list = [p for p in nx.all_shortest_paths(self._graph, source=circuit[0][0], target=circuit[0][1])]
        self.added_swaps += len(path_list[0]) - 2
        # Here test all paths
        for path in path_list:
            # map_list uses self.sampling_split
            list_, meeting_point_list = self.map_list(path)
            for j, mapping in enumerate(list_):
                new_graph = nx.relabel_nodes(self._graph, mapping)
                new_circuit = self.reduce(new_graph)
                # Greedy looking for the optimal path and the optimal walk on this path
                if len(new_circuit) < len(final_circuit):
                    final_graph = new_graph
                    final_circuit = new_circuit
                    final_mapping = mapping
                    final_path = path
                    meeting_point = meeting_point_list[j]
        self._graph = final_graph
        self._mapping = final_mapping
        self._circuit_repr = final_circuit
        return final_path, meeting_point

    def initial_checks(self, qubits):
        """Initialize the transpiled circuit and check if it can be mapped to the defined connectivity.

        Args:
            Args: qubits (int): number of qubits in the circuit to be transpiled.
        """
        nodes = self.connectivity.number_of_nodes()
        if qubits > nodes:
            raise_error(ValueError, "There are not enough physical qubits in the hardware to map the circuit")
        elif qubits == nodes:
            new_circuit = Circuit(nodes)
        else:
            if self.verbose:
                log.info(
                    "You are using more physical qubits than required by the circuit, some qubits will be added to the circuit"
                )
            new_circuit = Circuit(nodes)
        if not assert_placement(new_circuit, self._mapping, verbose=False):
            raise_error(ValueError, "The provided initial layout can't be used on this connectivity.")
        self._transpiled_circuit = new_circuit

    def add_gates(self, qibo_circuit, matched_gates):
        """Add one and two qubit gates to transpiled circuit until connectivity is matched

        Args:
            qibo_circuit (:class:`qibo.models.Circuit`): circuit to be transpiled.
            matched_gates (int): number of two qubit gates that can be applied with the current qubit mapping.
        """
        index = 0
        while self._circuit_position < len(qibo_circuit.queue):
            gate = qibo_circuit.queue[self._circuit_position]
            if len(gate.qubits) == 1:
                self._transpiled_circuit.add(gate.on_qubits({gate.qubits[0]: self._qubit_map[gate.qubits[0]]}))
                self._circuit_position += 1
            else:
                index += 1
                if index == matched_gates + 1:
                    break
                else:
                    self._transpiled_circuit.add(
                        gate.on_qubits(
                            {
                                gate.qubits[0]: self._qubit_map[gate.qubits[0]],
                                gate.qubits[1]: self._qubit_map[gate.qubits[1]],
                            }
                        )
                    )
                    self._circuit_position += 1

    def add_swaps(self, path, meeting_point):
        """Add swaps to the transpiled circuit to move qubits

        Args:
            path (list): path to move qubits.
            meeting_point (int): qubit meeting point in the path.
        """
        forward = path[0 : meeting_point + 1]
        backward = list(reversed(path[meeting_point + 1 :]))
        if len(forward) > 1:
            for f1, f2 in pairwise(forward):
                self._transpiled_circuit.add(gates.SWAP(self._qubit_map[f1], self._qubit_map[f2]))
        if len(backward) > 1:
            for b1, b2 in pairwise(backward):
                self._transpiled_circuit.add(gates.SWAP(self._qubit_map[b1], self._qubit_map[b2]))

    def update_qubit_map(self):
        """Update the qubit mapping after adding swaps"""
        old_mapping = self._qubit_map.copy()
        for key, value in self._mapping.items():
            self._qubit_map[value] = old_mapping[key]


class Sabre(Transpiler):
    # TODO: requires block circuit
    """
    Routing algorithm proposed in
    https://doi.org/10.48550/arXiv.1809.02573
    """

    def __init__(self):  # pragma: no cover
        super().__init__()
