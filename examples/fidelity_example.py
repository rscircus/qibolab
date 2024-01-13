from qibolab import create_platform
from qibolab.paths import qibolab_folder

# Define platform and load specific runcard
runcard = qibolab_folder / "runcards" / "tii5q.yml"
platform = create_platform("tii5q", runcard)

# Connects to lab instruments using the details specified in the calibration settings.
platform.connect()
# Executes a pulse sequence.
results = platform.measure_fidelity(qubits=[1, 2, 3, 4], nshots=3000)
print(
    f"results[qubit] (rotation_angle, threshold, fidelity, assignment_fidelity): {results}"
)
# Disconnect from the instruments
platform.disconnect()
