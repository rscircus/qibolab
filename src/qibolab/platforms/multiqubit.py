import copy
import os
import signal

import numpy as np
import yaml
from qibo.config import log, raise_error

from qibolab import AcquisitionType, AveragingMode, ExecutionParameters
from qibolab.channels import ChannelMap
from qibolab.platform import Platform
from qibolab.pulses import PulseSequence, PulseType
from qibolab.qubits import Qubit
from qibolab.result import (
    AveragedIntegratedResults,
    AveragedRawWaveformResults,
    AveragedSampleResults,
    IntegratedResults,
    RawWaveformResults,
    SampleResults,
)
from qibolab.sweeper import Parameter, Sweeper


class MultiqubitPlatform(Platform):
    """Platform based on qblox instruments.

    The functionality of this class will soon be refactored to align it with DesignPlatform.

    Attributes:
        instruments (dict): A dictionay of instruments :class:`qibolab.instruments.abstract.AbstractInstrument` connected to the experiment.
        qubit_instrument_map (dict): A dictionary mapping qubits to lists of instruments performing different roles for that qubit: [ReadOut, Drive, Flux, Bias].
        channels (ChannelMap): A collection of :class:`qibolab.designs.channels.Channel` connected to the experiment.

        Access dictionaries:
        ro_channel (dict): maps qubits to their readout channel.
        qd_channel (dict): maps qubits to their drive channel.
        qf_channel (dict): maps qubits to their flux (RF) channel.
        qb_channel (dict): maps qubits to their bias (DC) channel.
        qrm (dict): maps qubits to their readout module.
        qdm (dict): maps qubits to their drive module.
        qfm (dict): maps qubits to their flux (RF) module.
        qbm (dict): maps qubits to their bias (DC) module.
        ro_port (dict): maps qubits to their readout port.
        qd_port (dict): maps qubits to their drive port.
        qf_port (dict): maps qubits to their flux (RF) port.
        qb_port (dict): maps qubits to their bias (DC) port.

    """

    def __init__(self, name, runcard):
        # """Initialises the platform with its name and a platform runcard."""
        # self.instruments: dict = {}
        self.channels: ChannelMap = None

        # self.ro_channel = {}
        # self.qd_channel = {}
        # self.qf_channel = {}
        # self.qb_channel = {}
        # self.qrm = {}
        # self.qdm = {}
        # self.qfm = {}
        # self.qbm = {}
        # self.ro_port = {}
        # self.qd_port = {}
        # self.qf_port = {}
        # self.qb_port = {}

        # super().__init__(name, runcard, [], ChannelMap())
        # signal.signal(signal.SIGTERM, self._termination_handler)
        # self.qubit_instrument_map: dict = {}

        # # Instantiate instruments
        # for name in self.settings["instruments"]:
        #     lib = self.settings["instruments"][name]["lib"]
        #     i_class = self.settings["instruments"][name]["class"]
        #     address = self.settings["instruments"][name]["address"]
        #     from importlib import import_module

        #     InstrumentClass = getattr(import_module(f"qibolab.instruments.{lib}"), i_class)
        #     instance = InstrumentClass(name, address)
            
        #     print(name)
        #     print(instance)

        #     self.instruments[name] = instance
        #     # DEBUG: debug folder = report folder
        #     if lib == "qblox":
        #         folder = os.path.dirname(runcard) + "/debug/"
        #         if not os.path.exists(folder):
        #             os.makedirs(folder)
        #         self.instruments[name]._debug_folder = folder

        super().__init__(name, runcard, [], ChannelMap())
        self.instruments = {}
        self.qubit_instrument_map: dict = {}

        # Instantiate instruments
        for name in self.settings["instruments"]:
            lib = self.settings["instruments"][name]["lib"]
            i_class = self.settings["instruments"][name]["class"]
            address = self.settings["instruments"][name]["address"]
            from importlib import import_module

            InstrumentClass = getattr(import_module(f"qibolab.instruments.{lib}"), i_class)
            instance = InstrumentClass(name, address)
            self.instruments[name] = instance

        # Generate qubit_instrument_map from runcard
        for qubit_name in self.qubit_channel_map:
            self.qubit_instrument_map[qubit_name] = [None, None, None, None]  # [ReadOut, Drive, Flux, Bias]
            for name in self.instruments:
                if self.settings["instruments"][name]["class"] in ["ClusterQRM_RF", "ClusterQCM_RF", "ClusterQCM"]:
                    for port in self.settings["instruments"][name]["settings"]["ports"]:
                        channel = self.settings["instruments"][name]["settings"]["ports"][port]["channel"]
                        if channel in self.qubit_channel_map[qubit_name]:
                            self.qubit_instrument_map[qubit_name][
                                self.qubit_channel_map[qubit_name].index(channel)
                            ] = name
                if "s4g_modules" in self.settings["instruments"][name]["settings"]:
                    for channel in self.settings["instruments"][name]["settings"]["s4g_modules"]:
                        if channel in self.qubit_channel_map[qubit_name]:
                            self.qubit_instrument_map[qubit_name][
                                self.qubit_channel_map[qubit_name].index(channel)
                            ] = name

        # Create channel objects
        self.channels = ChannelMap.from_names(*self.settings["channels"])

        # super().__init__(name, runcard, [], ChannelMap())
        # self.instruments = {}
        # # Instantiate instruments
        # for name in self.settings["instruments"]:
        #     lib = self.settings["instruments"][name]["lib"]
        #     i_class = self.settings["instruments"][name]["class"]
        #     address = self.settings["instruments"][name]["address"]
        #     from importlib import import_module

        #     InstrumentClass = getattr(import_module(f"qibolab.instruments.{lib}"), i_class)
        #     instance = InstrumentClass(name, address)
        #     self.instruments[name] = instance

        # # Generate qubit_instrument_map from qubit_channel_map and the instruments' channel_port_maps
        # self.qubit_instrument_map = {}
        # for qubit in self.qubit_channel_map:
        #     print(qubit)
        #     self.qubit_instrument_map[qubit] = [None, None, None, None]
        #     for name in self.instruments:
        #         print("buildin instrument")
        #         if "channel_port_map" in self.settings["instruments"][name]["settings"]:
        #             for channel in self.settings["instruments"][name]["settings"]["channel_port_map"]:
        #                 if channel in self.qubit_channel_map[qubit]:
        #                     self.qubit_instrument_map[qubit][self.qubit_channel_map[qubit].index(channel)] = name
        #         if "s4g_modules" in self.settings["instruments"][name]["settings"]:
        #             for channel in self.settings["instruments"][name]["settings"]["s4g_modules"]:
        #                 if channel in self.qubit_channel_map[qubit]:
        #                     self.qubit_instrument_map[qubit][self.qubit_channel_map[qubit].index(channel)] = name

    def reload_settings(self):
        """Reloads platform settings from runcard and sets all instruments up with them."""
        super().reload_settings()
        self.characterization = self.settings["characterization"]
        self.qubit_channel_map = self.settings["qubit_channel_map"]
        print(self.qubit_channel_map)
        self.nshots = self.settings["settings"]["nshots"]
        self.relaxation_time = self.settings["settings"]["relaxation_time"]

        # if self.is_connected:
        #     self.setup()

        # FIX: Set attenuation again to the original value after sweep attenuation in punchout
        if hasattr(self, "qubit_instrument_map"):
            for qubit_name in self.qubits:
                instrument_name = self.qubit_instrument_map[qubit_name][0]
                port = self.qrm[qubit_name]._channel_port_map[self.qubit_channel_map[qubit_name][0]]
                att = self.settings["instruments"][instrument_name]["settings"]["ports"][port]["attenuation"]
                self.ro_port[qubit_name].attenuation = att

    def update(self, updates: dict):
        r"""Updates platform dependent runcard parameters and set up platform instruments if needed.

        Args:

            updates (dict): Dictionary containing the parameters to update the runcard.
        """
        for par, values in updates.items():
            for qubit, value in values.items():
                # resonator_punchout_attenuation
                if par == "readout_attenuation":
                    attenuation = int(value)
                    # save settings
                    instrument_name = self.qubit_instrument_map[qubit][0]
                    port = self.qrm[qubit]._channel_port_map[self.qubit_channel_map[qubit][0]]
                    self.settings["instruments"][instrument_name]["settings"]["ports"][port][
                        "attenuation"
                    ] = attenuation
                    # configure RO attenuation
                    self.ro_port[qubit].attenuation = attenuation

                # resonator_spectroscopy_flux / qubit_spectroscopy_flux
                if par == "sweetspot":
                    sweetspot = float(value)
                    # save settings
                    instrument_name = self.qubit_instrument_map[qubit][2]
                    port = self.qrm[qubit]._channel_port_map[self.qubit_channel_map[qubit][2]]
                    self.settings["instruments"][instrument_name]["settings"]["ports"][port]["offset"] = sweetspot
                    # configure instrument qcm_bb offset
                    self.qb_port[qubit].current = sweetspot

                # qubit_spectroscopy / qubit_spectroscopy_flux / ramsey
                if par == "drive_frequency":
                    freq = int(value * 1e9)

                    # update Qblox qubit LO drive frequency config
                    instrument_name = self.qubit_instrument_map[qubit][1]
                    port = self.qdm[qubit]._channel_port_map[self.qubit_channel_map[qubit][1]]
                    drive_if = self.qubits[qubit].native_gates.RX.if_frequency
                    self.settings["instruments"][instrument_name]["settings"]["ports"][port]["lo_frequency"] = (
                        freq - drive_if
                    )

                    # set Qblox qubit LO drive frequency
                    self.qd_port[qubit].lo_frequency = freq - drive_if

                # classification
                if par == "threshold":
                    threshold = float(value)
                    # update Qblox qubit classification threshold
                    instrument_name = self.qubit_instrument_map[qubit][0]
                    self.settings["instruments"][instrument_name]["settings"]["classification_parameters"][qubit][
                        "threshold"
                    ] = threshold

                    self.instruments[instrument_name].setup(
                        **self.settings["settings"],
                        **self.settings["instruments"][instrument_name]["settings"],
                    )

                # classification
                if par == "iq_angle":
                    rotation_angle = float(value)
                    rotation_angle = (
                        rotation_angle * 360 / (2 * np.pi)
                    ) % 360  # save rotation angle in degrees for qblox
                    # update Qblox qubit classification iq angle
                    instrument_name = self.qubit_instrument_map[qubit][0]
                    self.settings["instruments"][instrument_name]["settings"]["classification_parameters"][qubit][
                        "rotation_angle"
                    ] = rotation_angle

                    self.instruments[instrument_name].setup(
                        **self.settings["settings"],
                        **self.settings["instruments"][instrument_name]["settings"],
                    )

                super().update(updates)

    def connect(self):
        """Connects to the instruments."""
        if not self.is_connected:
            try:
                for name in self.instruments:
                    self.instruments[name].connect()
                self.is_connected = True
            except Exception as exception:
                raise_error(
                    RuntimeError,
                    "Cannot establish connection to " f"{self.name} instruments. " f"Error captured: '{exception}'",
                )
                # TODO: check for exception 'The instrument qrm_rf0 does not have parameters in0_att' and reboot the cluster

            else:
                log.info(f"All platform instruments connected.")

    def setup(self):
        """Sets all instruments up.

        Each instrument is set up calling its setup method, with the platform instruments and the specific intrument
        settings. Additionally it generates dictionaries for accessing channels, instrument ports and modules.
        """
        if not self.is_connected:
            raise_error(
                RuntimeError,
                "There is no connection to the instruments, the setup cannot be completed",
            )

        for name in self.instruments:
            # Set up every with the platform settings and the instrument settings
            self.instruments[name].setup(
                **self.settings["settings"],
                **self.settings["instruments"][name]["settings"],
            )
        # Generate ro_channel[qubit], qd_channel[qubit], qf_channel[qubit], qrm[qubit], qcm[qubit], lo_qrm[qubit], lo_qcm[qubit]
        self.ro_channel = {}  # readout
        self.qd_channel = {}  # qubit drive
        self.qf_channel = {}  # qubit flux
        self.qb_channel = {}  # qubit flux biassing
        self.qrm = {}  # qubit readout module
        self.qdm = {}  # qubit drive module
        self.qfm = {}  # qubit flux module
        self.qbm = {}  # qubit flux biassing module
        self.ro_port = {}
        self.qd_port = {}
        self.qf_port = {}
        self.qb_port = {}

        # Generate access dictionaries
        for qubit in self.qubit_channel_map:
            
            print(qubit)
            self.ro_channel[qubit] = self.qubit_channel_map[qubit][0]
            self.qd_channel[qubit] = self.qubit_channel_map[qubit][1]
            self.qb_channel[qubit] = self.qubit_channel_map[qubit][2]
            self.qf_channel[qubit] = self.qubit_channel_map[qubit][3]
            print(self.qubit_instrument_map[qubit][0])

            if not self.qubit_instrument_map[qubit][0] is None:
                self.qrm[qubit] = self.instruments[self.qubit_instrument_map[qubit][0]]
                self.ro_port[qubit] = self.qrm[qubit].ports[
                    self.qrm[qubit]._channel_port_map[self.qubit_channel_map[qubit][0]]
                ]
                self.qubits[qubit].readout = self.channels[self.qubit_channel_map[qubit][0]]
            if not self.qubit_instrument_map[qubit][1] is None:
                self.qdm[qubit] = self.instruments[self.qubit_instrument_map[qubit][1]]
                self.qd_port[qubit] = self.qdm[qubit].ports[
                    self.qdm[qubit]._channel_port_map[self.qubit_channel_map[qubit][1]]
                ]
                self.qubits[qubit].drive = self.channels[self.qubit_channel_map[qubit][1]]
            if not self.qubit_instrument_map[qubit][2] is None:
                self.qfm[qubit] = self.instruments[self.qubit_instrument_map[qubit][2]]
                self.qf_port[qubit] = self.qfm[qubit].ports[
                    self.qfm[qubit]._channel_port_map[self.qubit_channel_map[qubit][2]]
                ]
                self.qubits[qubit].flux = self.channels[self.qubit_channel_map[qubit][2]]
            if not self.qubit_instrument_map[qubit][3] is None:
                self.qbm[qubit] = self.instruments[self.qubit_instrument_map[qubit][3]]
                self.qb_port[qubit] = self.qbm[qubit].dacs[self.qubit_channel_map[qubit][3]]

    def start(self):
        """Starts all platform instruments."""

        if self.is_connected:
            for name in self.instruments:
                self.instruments[name].start()

    def stop(self):
        """Stops all platform instruments."""

        if self.is_connected:
            for name in self.instruments:
                self.instruments[name].stop()

    def _termination_handler(self, signum, frame):
        """Calls all instruments to stop if the program receives a termination signal."""

        log.warning("Termination signal received, stopping instruments.")
        if self.is_connected:
            for name in self.instruments:
                self.instruments[name].stop()
        log.warning("All instruments stopped.")
        exit(0)

    def disconnect(self):
        """Disconnects all platform instruments."""

        if self.is_connected:
            for name in self.instruments:
                self.instruments[name].disconnect()
            self.is_connected = False

    def execute_pulse_sequence(
        self,
        sequence: PulseSequence,
        options: ExecutionParameters,
        sweepers: list() = [],  # list(Sweeper) = []
        **kwargs
        # nshots=None,
        # navgs=None,
        # relaxation_time=None,
    ):
        """Executes a sequence of pulses or a sweep.

        Args:
            sequence (:class:`qibolab.pulses.PulseSequence`): The sequence of pulses to execute.
            options (:class:`qibolab.platforms.platform.ExecutionParameters`): Object holding the execution options.
            sweepers (list(Sweeper)): A list of Sweeper objects defining parameter sweeps.
        """
        if not self.is_connected:
            raise_error(RuntimeError, "Execution failed because instruments are not connected.")

        if options.averaging_mode == AveragingMode.SINGLESHOT:
            nshots = options.nshots if options.nshots is not None else self.nshots
            navgs = 1
            self.average = False
        else:
            navgs = options.nshots if options.nshots is not None else self.nshots
            nshots = 1
            self.average = True

        relaxation_time = options.relaxation_time if options.relaxation_time is not None else self.relaxation_time
        repetition_duration = sequence.finish + relaxation_time

        # shots results are stored in separate bins
        # calculate number of shots
        num_bins = nshots
        for sweeper in sweepers:
            num_bins *= len(sweeper.values)

        # DEBUG: Plot Pulse Sequence
        # sequence.plot('plot.png')
        # DEBUG: sync_en
        # from qblox_instruments.qcodes_drivers.cluster import Cluster
        # cluster:Cluster = self.instruments['cluster'].device
        # for module in cluster.modules:
        #     if module.get("present"):
        #         for sequencer in module.sequencers:
        #             if sequencer.get('sync_en'):
        #                 print(f"type: {module.module_type}, sequencer: {sequencer.name}, sync_en: True")

        # Process Pulse Sequence. Assign pulses to instruments and generate waveforms & program
        instrument_pulses = {}
        roles = {}
        data = {}
        for name in self.instruments:
            roles[name] = self.settings["instruments"][name]["roles"]
            if "control" in roles[name] or "readout" in roles[name]:
                # from the pulse sequence, select those pulses to be synthesised by the instrument
                instrument_pulses[name] = sequence.get_channel_pulses(*self.instruments[name].channels)

                # until we have frequency planning use the ifs stored in the runcard to set the los
                if self.instruments[name].__class__.__name__.split(".")[-1] in [
                    "ClusterQRM_RF",
                    "ClusterQCM_RF",
                    "ClusterQCM",
                ]:
                    for port in self.instruments[name].ports:
                        _los = []
                        _ifs = []
                        port_pulses = instrument_pulses[name].get_channel_pulses(
                            self.instruments[name]._port_channel_map[port]
                        )
                        for pulse in port_pulses:
                            if pulse.type == PulseType.READOUT:
                                _if = int(self.native_gates["single_qubit"][pulse.qubit]["MZ"]["if_frequency"])
                                pulse._if = _if
                                _los.append(int(pulse.frequency - _if))
                                _ifs.append(int(_if))
                            elif pulse.type == PulseType.DRIVE:
                                _if = int(self.native_gates["single_qubit"][pulse.qubit]["RX"]["if_frequency"])
                                pulse._if = _if
                                _los.append(int(pulse.frequency - _if))
                                _ifs.append(int(_if))

                        # where multiple qubits share the same lo (for example on a readout line), check lo consistency
                        if len(_los) > 1:
                            for _ in range(1, len(_los)):
                                if _los[0] != _los[_]:
                                    raise ValueError(
                                        f"""Pulses:
                                        {instrument_pulses[name]}
                                        sharing the lo at device: {name} - port: {port}
                                        cannot be synthesised with intermediate frequencies:
                                        {_ifs}"""
                                    )
                        if len(_los) > 0:
                            self.instruments[name].ports[port].lo_frequency = _los[0]

                #  ask each instrument to generate waveforms & program and upload them to the device
                self.instruments[name].process_pulse_sequence(
                    instrument_pulses[name], navgs, nshots, repetition_duration, sweepers
                )

                # log.info(f"{self.instruments[name]}: Uploading pulse sequence")
                self.instruments[name].upload()

        # play the sequence or sweep
        for name in self.instruments:
            if "control" in roles[name] or "readout" in roles[name]:
                self.instruments[name].play_sequence()

        # retrieve the results
        acquisition_results = {}
        for name in self.instruments:
            if "readout" in roles[name]:
                if not instrument_pulses[name].ro_pulses.is_empty:
                    results = self.instruments[name].acquire()
                    existing_keys = set(acquisition_results.keys()) & set(results.keys())
                    for key, value in results.items():
                        if key in existing_keys:
                            acquisition_results[key].update(value)
                        else:
                            acquisition_results[key] = value

        # TODO: move to QRM_RF.acquire()
        for ro_pulse in sequence.ro_pulses:
            if options.acquisition_type is AcquisitionType.DISCRIMINATION:
                acquisition = SampleResults(acquisition_results[ro_pulse.serial][2])
            else:
                ires = acquisition_results[ro_pulse.serial][0]
                qres = acquisition_results[ro_pulse.serial][1]
                if options.acquisition_type is AcquisitionType.RAW:
                    acquisition = RawWaveformResults(ires + 1j * qres)
                if options.acquisition_type is AcquisitionType.INTEGRATION:
                    acquisition = IntegratedResults(ires + 1j * qres)
            if self.average:
                acquisition = acquisition.average
            data[ro_pulse.serial] = data[ro_pulse.serial] = acquisition

            # data[ro_pulse.serial] = ExecutionResults.from_components(*acquisition_results[ro_pulse.serial])
            # data[ro_pulse.serial] = IntegratedResults(acquisition_results[ro_pulse.serial])
            # data[ro_pulse.qubit] = copy.copy(data[ro_pulse.serial])
        return data

    def sweep(self, sequence: PulseSequence, options: ExecutionParameters, *sweepers):
        """Executes a sequence of pulses while sweeping one or more parameters.

        The parameters to be swept are defined in :class:`qibolab.sweeper.Sweeper` object.
        Args:
            sequence (:class:`qibolab.pulses.PulseSequence`): The sequence of pulses to execute.
            options (:class:`qibolab.platforms.platform.ExecutionParameters`): Object holding the execution options.
            sweepers (list(Sweeper)): A list of Sweeper objects defining parameter sweeps.
        """
        id_results = {}
        map_id_serial = {}

        # during the sweep, pulse parameters need to be changed
        # to avoid affecting the user, make a copy of the pulse sequence
        # and the sweepers, as they contain references to pulses
        sequence_copy = sequence.copy()
        sweepers_copy = []
        for sweeper in sweepers:
            if sweeper.pulses:
                ps = []
                for pulse in sweeper.pulses:
                    if pulse in sequence_copy:
                        ps.append(sequence_copy[sequence_copy.index(pulse)])
            else:
                ps = None
            sweepers_copy.append(
                Sweeper(
                    parameter=sweeper.parameter,
                    values=sweeper.values,
                    pulses=ps,
                    qubits=sweeper.qubits,
                )
            )

        # reverse sweepers exept for res punchout att
        contains_attenuation_frequency = any(
            sweepers_copy[i].parameter == Parameter.attenuation
            and sweepers_copy[i + 1].parameter == Parameter.frequency
            for i in range(len(sweepers_copy) - 1)
        )

        if not contains_attenuation_frequency:
            sweepers_copy.reverse()

        # create a map between the pulse id, which never changes, and the original serial
        for pulse in sequence_copy.ro_pulses:
            map_id_serial[pulse.id] = pulse.serial
            id_results[pulse.id] = None
            id_results[pulse.qubit] = None

        # execute the each sweeper recursively
        self._sweep_recursion(
            sequence_copy,
            options,
            sweepers_copy,
            results=id_results,
        )

        # return the results using the original serials
        serial_results = {}
        for pulse in sequence_copy.ro_pulses:
            serial_results[map_id_serial[pulse.id]] = id_results[pulse.id]
            serial_results[pulse.qubit] = id_results[pulse.id]
        return serial_results

    def _sweep_recursion(
        self,
        sequence,
        options: ExecutionParameters,
        sweepers,
        results,
    ):
        """Executes a sweep recursively.

        Args:
            sequence (:class:`qibolab.pulses.PulseSequence`): The sequence of pulses to execute.
            sweepers (list(Sweeper)): A list of Sweeper objects defining parameter sweeps.
            results (:class:`qibolab.results.ExecutionResults`): A results object to update with the reults of the execution.
            nshots (int): The number of times the sequence of pulses should be executed.
            average (bool): A flag to indicate if the results of the shots should be averaged.
            relaxation_time (int): The the time to wait between repetitions to allow the qubit relax to ground state.
        """
        sweeper = sweepers[0]

        initial = {}
        if sweeper.parameter is Parameter.lo_frequency:
            initial = {}
            for pulse in sweeper.pulses:
                if pulse.type == PulseType.READOUT:
                    initial[pulse.id] = self.get_lo_readout_frequency(pulse.qubit)
                elif pulse.type == PulseType.DRIVE:
                    initial[pulse.id] = self.get_lo_readout_frequency(pulse.qubit)

        # until sweeper contains the information to determine whether the sweep should be relative or
        # absolute:

        # elif sweeper.parameter is Parameter.attenuation:
        #     for qubit in sweeper.qubits:
        #         initial[qubit] = self.get_attenuation(qubit)

        # elif sweeper.parameter is Parameter.relative_phase:
        #     initial = {}
        #     for pulse in sweeper.pulses:
        #         initial[pulse.id] = pulse.relative_phase

        # elif sweeper.parameter is Parameter.frequency:
        #     initial = {}
        #     for pulse in sweeper.pulses:
        #         initial[pulse.id] = pulse.frequency
        # elif sweeper.parameter is Parameter.bias:
        #     initial = {}
        #     for qubit in sweeper.qubits:
        #         initial[qubit] = self.get_bias(qubit)

        elif sweeper.parameter is Parameter.gain:
            for pulse in sweeper.pulses:
                # qblox has an external and an internal gains
                # when sweeping the internal, set the external to 1
                self.set_gain(pulse.qubit, 1)
        elif sweeper.parameter is Parameter.amplitude:
            # qblox cannot sweep amplitude in real time, but sweeping gain is quivalent
            for pulse in sweeper.pulses:
                pulse.amplitude = 1

        for_loop_sweepers = [Parameter.attenuation, Parameter.lo_frequency]
        rt_sweepers = [
            Parameter.frequency,
            Parameter.gain,
            Parameter.bias,
            Parameter.amplitude,
            Parameter.start,
            Parameter.duration,
            Parameter.relative_phase,
        ]

        if sweeper.parameter in for_loop_sweepers:
            # perform sweep recursively
            for value in sweeper.values:
                if sweeper.parameter is Parameter.attenuation:
                    for qubit in sweeper.qubits:
                        # self.set_attenuation(qubit, initial[qubit] + value)
                        self.set_attenuation(qubit, value)
                elif sweeper.parameter is Parameter.lo_frequency:
                    for pulse in sweeper.pulses:
                        if pulse.type == PulseType.READOUT:
                            self.set_lo_readout_frequency(initial[pulse.id] + value)
                        elif pulse.type == PulseType.DRIVE:
                            self.set_lo_readout_frequency(initial[pulse.id] + value)

                if len(sweepers) > 1:
                    self._sweep_recursion(
                        sequence,
                        options=options,
                        *sweepers[1:],
                        results=results,
                    )
                else:
                    result = self.execute_pulse_sequence(sequence=sequence, options=options)
                    for pulse in sequence.ro_pulses:
                        results[pulse.id] += result[pulse.serial]
                        results[pulse.qubit] = results[pulse.id]
        else:
            # rt sweeps
            # relative phase sweeps that cross 0 need to be split in two separate sweeps
            split_relative_phase = False
            if sweeper.parameter == Parameter.relative_phase:
                from qibolab.instruments.qblox_q1asm import convert_phase

                c_values = np.array([convert_phase(v) for v in sweeper.values])
                if any(np.diff(c_values) < 0):
                    split_relative_phase = True
                    _from = 0
                    for idx in np.append(np.where(np.diff(c_values) < 0), len(c_values) - 1):
                        _to = idx + 1
                        _values = sweeper.values[_from:_to]
                        split_sweeper = Sweeper(
                            parameter=sweeper.parameter,
                            values=_values,
                            pulses=sweeper.pulses,
                            qubits=sweeper.qubits,
                        )
                        self._sweep_recursion(
                            sequence,
                            options=options,
                            *(tuple([split_sweeper]) + sweepers[1:]),
                            results=results,
                        )
                        _from = _to

            if not split_relative_phase:
                if all(s.parameter in rt_sweepers for s in sweepers):
                    nshots = options.nshots if options.averaging_mode == AveragingMode.SINGLESHOT else 1
                    navgs = options.nshots if options.averaging_mode != AveragingMode.SINGLESHOT else 1
                    num_bins = nshots
                    for sweeper in sweepers:
                        num_bins *= len(sweeper.values)

                    # split the sweep if the number of bins is larget than the memory of the sequencer (2**17)
                    if num_bins < 2**17:
                        repetition_duration = sequence.finish + options.relaxation_time
                        execution_time = navgs * num_bins * ((repetition_duration + 1000 * len(sweepers)) * 1e-9)
                        log.info(
                            f"Real time sweeper execution time: {int(execution_time)//60}m {int(execution_time) % 60}s"
                        )

                        result = self.execute_pulse_sequence(sequence, options, sweepers)
                        for pulse in sequence.ro_pulses:
                            # Dentro del bucle
                            if results[pulse.id] is None:
                                results[pulse.id] = result[pulse.serial]
                            else:
                                results[pulse.id] += result[pulse.serial]
                            # results[pulse.id] += result[pulse.serial]
                            results[pulse.qubit] = results[pulse.id]
                            print(results)
                    else:
                        sweepers_repetitions = 1
                        for sweeper in sweepers:
                            sweepers_repetitions *= len(sweeper.values)
                        if sweepers_repetitions < 2**17:
                            # split nshots
                            max_rt_nshots = (2**17) // sweepers_repetitions
                            num_full_sft_iterations = nshots // max_rt_nshots
                            num_bins = max_rt_nshots * sweepers_repetitions

                            for sft_iteration in range(num_full_sft_iterations + 1):
                                _nshots = min(max_rt_nshots, nshots - sft_iteration * max_rt_nshots)
                                self._sweep_recursion(
                                    sequence,
                                    options,
                                    *sweepers,
                                    results=results,
                                )
                        else:
                            for shot in range(nshots):
                                num_bins = 1
                                for sweeper in sweepers[1:]:
                                    num_bins *= len(sweeper.values)
                                sweeper = sweepers[0]
                                max_rt_iterations = (2**17) // num_bins
                                num_full_sft_iterations = len(sweeper.values) // max_rt_iterations
                                num_bins = nshots * max_rt_iterations
                                for sft_iteration in range(num_full_sft_iterations + 1):
                                    _from = sft_iteration * max_rt_iterations
                                    _to = min((sft_iteration + 1) * max_rt_iterations, len(sweeper.values))
                                    _values = sweeper.values[_from:_to]
                                    split_sweeper = Sweeper(
                                        parameter=sweeper.parameter,
                                        values=_values,
                                        pulses=sweeper.pulses,
                                        qubits=sweeper.qubits,
                                    )

                                    self._sweep_recursion(
                                        sequence,
                                        options,
                                        *(tuple([split_sweeper]) + sweepers[1:]),
                                        results=results,
                                    )
                else:
                    # TODO: reorder the sequence of the sweepers and the results
                    raise Exception("cannot execute a for-loop sweeper nested inside of a rt sweeper")

    # proposed standard interfaces to access and modify instrument parameters

    def set_lo_drive_frequency(self, qubit, freq):
        """Sets the frequency of the local oscillator used to upconvert drive pulses for a qubit."""
        qubit = qubit.name if isinstance(qubit, Qubit) else qubit
        self.qd_port[qubit].lo_frequency = freq

    def get_lo_drive_frequency(self, qubit):
        """Gets the frequency of the local oscillator used to upconvert drive pulses for a qubit."""
        qubit = qubit.name if isinstance(qubit, Qubit) else qubit
        return self.qd_port[qubit].lo_frequency

    def set_lo_readout_frequency(self, qubit, freq):
        """Sets the frequency of the local oscillator used to upconvert readout pulses for a qubit."""
        qubit = qubit.name if isinstance(qubit, Qubit) else qubit
        self.ro_port[qubit].lo_frequency = freq

    def get_lo_readout_frequency(self, qubit):
        """Gets the frequency of the local oscillator used to upconvert readout pulses for a qubit."""
        print(f"entro: {self.ro_port}")
        qubit = qubit.name if isinstance(qubit, Qubit) else qubit
        return self.ro_port[qubit].lo_frequency

    def set_attenuation(self, qubit, att):
        """Sets the attenuation of the readout port for a qubit."""
        qubit = qubit.name if isinstance(qubit, Qubit) else qubit
        self.ro_port[qubit].attenuation = att

    def get_attenuation(self, qubit):
        """Gets the attenuation of the readout port for a qubit."""
        qubit = qubit.name if isinstance(qubit, Qubit) else qubit
        return self.ro_port[qubit].attenuation

    def set_gain(self, qubit, gain):
        """Sets the gain of the drive port for a qubit."""
        qubit = qubit.name if isinstance(qubit, Qubit) else qubit
        self.qd_port[qubit].gain = gain

    def get_gain(self, qubit):
        """Gets the gain of the drive port for a qubit."""
        qubit = qubit.name if isinstance(qubit, Qubit) else qubit
        return self.qd_port[qubit].gain

    def set_bias(self, qubit, bias):
        """Sets the flux bias for a qubit.

        It supports biasing the qubit with a current source (SPI) or with the offset of a QCM module.
        """
        qubit = qubit.name if isinstance(qubit, Qubit) else qubit
        if qubit in self.qbm:
            self.qb_port[qubit].current = bias
        elif qubit in self.qfm:
            self.qf_port[qubit].offset = bias

    def get_bias(self, qubit):
        """Gets flux bias for a qubit."""
        qubit = qubit.name if isinstance(qubit, Qubit) else qubit
        if qubit in self.qbm:
            return self.qb_port[qubit].current
        elif qubit in self.qfm:
            return self.qf_port[qubit].offset

    # TODO: implement a dictionary of qubit - twpas
    def set_lo_twpa_frequency(self, qubit, freq):
        """Sets the frequency of the local oscillator used to pump a qubit parametric amplifier."""
        qubit = qubit.name if isinstance(qubit, Qubit) else qubit
        for instrument in self.instruments:
            if "twpa" in instrument:
                self.instruments[instrument].frequency = freq
                return None
        raise_error(NotImplementedError, "No twpa instrument found in the platform. ")

    def get_lo_twpa_frequency(self, qubit):
        """Gets the frequency of the local oscillator used to pump a qubit parametric amplifier."""
        qubit = qubit.name if isinstance(qubit, Qubit) else qubit
        for instrument in self.instruments:
            if "twpa" in instrument:
                return self.instruments[instrument].frequency
        raise_error(NotImplementedError, "No twpa instrument found in the platform. ")

    def set_lo_twpa_power(self, qubit, power):
        """Sets the power of the local oscillator used to pump a qubit parametric amplifier."""
        qubit = qubit.name if isinstance(qubit, Qubit) else qubit
        for instrument in self.instruments:
            if "twpa" in instrument:
                self.instruments[instrument].power = power
                return None
        raise_error(NotImplementedError, "No twpa instrument found in the platform. ")

    def get_lo_twpa_power(self, qubit):
        """Gets the power of the local oscillator used to pump a qubit parametric amplifier."""
        qubit = qubit.name if isinstance(qubit, Qubit) else qubit
        for instrument in self.instruments:
            if "twpa" in instrument:
                return self.instruments[instrument].power
        raise_error(NotImplementedError, "No twpa instrument found in the platform. ")
