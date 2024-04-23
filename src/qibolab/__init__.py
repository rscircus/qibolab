import importlib.metadata as im
import importlib.util
import os
from pathlib import Path

from qibo import Circuit
from qibo.config import raise_error

from qibolab.execution_parameters import (
    AcquisitionType,
    AveragingMode,
    ExecutionParameters,
)
from qibolab.platform import Platform
from qibolab.serialize import PLATFORM

__version__ = im.version(__package__)

PLATFORMS = "QIBOLAB_PLATFORMS"


def get_platforms_path():
    """Get path to repository containing the platforms.

    Path is specified using the environment variable QIBOLAB_PLATFORMS.
    """
    profiles = os.environ.get(PLATFORMS)
    if profiles is None or not os.path.exists(profiles):
        raise_error(RuntimeError, f"Profile directory {profiles} does not exist.")
    return Path(profiles)


def create_platform(name, path: Path = None) -> Platform:
    """A platform for executing quantum algorithms.

    It consists of a quantum processor QPU and a set of controlling instruments.

    Args:
        name (str): name of the platform. Options are 'tiiq', 'qili' and 'icarusq'.
        path (pathlib.Path): path with platform serialization
    Returns:
        The plaform class.
    """
    if name == "dummy" or name == "dummy_couplers":
        from qibolab.dummy import create_dummy

        return create_dummy(with_couplers=name == "dummy_couplers")

    platform = get_platforms_path() / f"{name}"
    if not platform.exists():
        raise_error(ValueError, f"Platform {name} does not exist.")

    spec = importlib.util.spec_from_file_location("platform", platform / PLATFORM)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if path is None:
        return module.create()
    return module.create(path)


def execute_qasm(circuit: str, platform, runcard=None, initial_state=None, nshots=1000):
    """Executes a QASM circuit.

    Args:
        circuit (str): the QASM circuit.
        platform (str): the platform where to execute the circuit.
        runcard (pathlib.Path): the path to the runcard used for the platform.
        initial_state (:class:`qibo.models.circuit.Circuit`): Circuit to prepare the initial state.
                If ``None`` the default ``|00...0>`` state is used.
        nshots (int): Number of shots to sample from the experiment.

    Returns:
        ``MeasurementOutcomes`` object containing the results acquired from the execution.
    """
    from qibolab.backends import QibolabBackend

    circuit = Circuit.from_qasm(circuit)
    return QibolabBackend(platform, runcard).execute_circuit(
        circuit, initial_state=initial_state, nshots=nshots
    )


def get_available_platforms() -> list[str]:
    """Returns the platforms found in the $QIBOLAB_PLATFORMS directory."""
    return [
        d.name
        for d in get_platforms_path().iterdir()
        if d.is_dir() and not (d.name.startswith("_") or d.name.startswith("."))
    ]


class MetaBackend:
    """Meta-backend class which takes care of loading the qibolab backend."""

    @staticmethod
    def load(platform: str):
        """Loads the backend.

        Args:
            platform (str): Name of the platform to load.
        Returns:
            qibo.backends.abstract.Backend: The loaded backend.
        """
        from qibolab.backends import QibolabBackend

        platforms = get_available_platforms()
        if platform in platforms:
            return QibolabBackend(platform=platform)
        else:
            raise_error(
                ValueError,
                f"Unsupported platform, please use one among {platforms}.",
            )

    def list_available(self) -> dict:
        """Lists all the available qibolab platforms."""
        available_platforms = {}
        for platform in get_available_platforms():
            try:
                MetaBackend.load(platform)
                available_platforms[platform] = True
            except:
                available_platforms[platform] = False
        return available_platforms
