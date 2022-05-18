import pathlib
from qibolab.paths import qibolab_folder
import json
import numpy as np
from abc import ABC, abstractmethod
from qibo.config import raise_error
from qibolab.instruments.instrument import Instrument, InstrumentException

import logging
logger = logging.getLogger(__name__)  # TODO: Consider using a global logger

data_folder = qibolab_folder / "instruments" / "data"
data_folder.mkdir(parents=True, exist_ok=True)

class GenericPulsar(Instrument, ABC):

    def __init__(self, label, ip, sequencer, ref_clock, sync_en, is_cluster):
        super().__init__(ip)
        self.label = label
        # TODO When updating to the new firmware, use a sequencer mapping instead of setting a single sequencer
        self.sequencer = sequencer
        self.ref_clock = ref_clock
        self.sync_en = sync_en
        self.is_cluster = is_cluster
        self._connected = False
        self.Device = None
        self.device = None
        # To be defined in each instrument
        self.name = None
        # To be defined during setup
        self.hardware_avg = None
        self.initial_delay = None
        self.repetition_duration = None
        # hardcoded values used in ``generate_program``
        self.delay_before_readout = 4 # same value is used for all readout pulses (?)
        self.wait_loop_step = 1000
        self.duration_base = 16380 # maximum length of a waveform in number of samples (defined by the device memory).
        # hardcoded values used in ``upload``
        # TODO QCM shouldn't have acquisitions
        self.acquisitions = {"single": {"num_bins": 1, "index":0}}
        self.weights = {}

    def connect(self):
        """Connects to the instruments."""
        if not self._connected:
            import socket
            try:
                self.device = self.Device(self.label, self.ip) # pylint: disable=E1102
                logger.info(f"{self.name} connection established.")
                self._connected = True
            except socket.timeout:
                # Use warning instead of exception when instruments are
                # not available so that we can run tests on different devices
                logger.warning("Could not connect to QRM. Skipping...")
            except Exception as exc:  # pragma: no cover
                raise InstrumentException(self, str(exc))
        else:
            raise_error(RuntimeError, "QRM is already connected.")

    @property
    def gain(self):
        return self._gain

    @gain.setter
    def gain(self, gain):
        self._gain = gain
        if self._connected:
            if self.sequencer == 1:
                self.device.sequencer1_gain_awg_path0(gain)
                self.device.sequencer1_gain_awg_path1(gain)
            else:
                self.device.sequencer0_gain_awg_path0(gain)
                self.device.sequencer0_gain_awg_path1(gain)
        else:
            logger.warning("Cannot set gain because device is not connected.")

    def setup(self, gain, initial_delay, repetition_duration):
        """Sets calibration setting to QBlox instruments.

        Args:
            gain (float):
            initial_delay (float):
            repetition_duration (float):
        """
        self.gain = gain
        self.initial_delay = initial_delay
        self.repetition_duration = repetition_duration

    @staticmethod
    def _translate_single_pulse(pulse):
        """Translates a single pulse to the instrument waveform format.

        Helper method for :meth:`qibolab.instruments.qblox.GenericPulsar.generate_waveforms`.

        Args:
            pulse (:class:`qibolab.pulses.Pulse`): Pulse object to translate.

        Returns:
            Dictionary containing the waveform corresponding to the pulse.
        """
        # Use the envelope to modulate a sinusoldal signal of frequency freq_if
        envelope_i = pulse.compile()
        # TODO: if ``envelope_q`` is not always 0 we need to find how to
        # calculate it
        envelope_q  = np.zeros(int(pulse.duration))
        envelopes   = np.array([envelope_i, envelope_q])
        time        = np.arange(pulse.duration) * 1e-9
        cosalpha    = np.cos(2 * np.pi * pulse.frequency * time + pulse.phase)
        sinalpha    = np.sin(2 * np.pi * pulse.frequency * time + pulse.phase)
        mod_matrix  = np.array([[ cosalpha, sinalpha],
                                [-sinalpha, cosalpha]])
        mod_signals = np.einsum("abt,bt->ta", mod_matrix, envelopes)

        # add offsets to compensate mixer leakage
        waveform = {
            "modI": {"data": mod_signals[:, 0] + pulse.offset_i, "index": 0},
            "modQ": {"data": mod_signals[:, 1] + pulse.offset_q, "index": 1}
        }
        return waveform

    def generate_waveforms(self, pulses):
        """Translates a list of pulses to the instrument waveform format.

        Args:
            pulses (list): List of :class:`qibolab.pulses.Pulse` objects.

        Returns:
            Dictionary containing waveforms corresponding to all pulses.
        """
        if not pulses:
            raise_error(ValueError, "Cannot translate empty pulse sequence.")
        name = self.name

        combined_length = max(pulse.start + pulse.duration for pulse in pulses)
        waveforms = {
            f"modI_{name}": {"data": np.zeros(combined_length), "index": 0},
            f"modQ_{name}": {"data": np.zeros(combined_length), "index": 1}
        }
        for pulse in pulses:
            waveform = self._translate_single_pulse(pulse)
            i0, i1 = pulse.start, pulse.start + pulse.duration
            waveforms[f"modI_{name}"]["data"][i0:i1] += waveform["modI"]["data"]
            waveforms[f"modQ_{name}"]["data"][i0:i1] += waveform["modQ"]["data"]

        #Fixing 0s addded to the qrm waveform. Needs to be improved, but working well on TIIq
        for pulse in pulses:
            if(pulse.channel == "qrm"):
                waveforms[f"modI_{name}"]["data"] = waveforms[f"modI_{name}"]["data"][pulse.start:]
                waveforms[f"modQ_{name}"]["data"] = waveforms[f"modQ_{name}"]["data"][pulse.start:] 

        return waveforms

    def generate_program(self, hardware_avg, initial_delay, delay_before_readout, acquire_instruction, wait_time):
        """Generates the program to be uploaded to instruments."""
        extra_duration = self.repetition_duration - self.duration_base
        extra_wait = extra_duration % self.wait_loop_step
        num_wait_loops = (extra_duration - extra_wait) // self. wait_loop_step

        # This calculation was moved to `PulsarQCM` and `PulsarQRM`
        #if ro_pulse is not None:
        #    acquire_instruction = "acquire   0,0,4"
        #    wait_time = self.duration_base - initial_delay - delay_before_readout - 4
        #else:
        #    acquire_instruction = ""
        #    wait_time = self.duration_base - initial_delay - delay_before_readout

        if initial_delay != 0:
            initial_wait_instruction = f"wait      {initial_delay}"
        else:
            initial_wait_instruction = ""

        program = f"""
            move    {hardware_avg},R0
            nop
            wait_sync 4          # Synchronize sequencers over multiple instruments
        loop:
            {initial_wait_instruction}
            play      0,1,{delay_before_readout}
            {acquire_instruction}
            wait      {wait_time}
            move      {num_wait_loops},R1
            nop
            repeatloop:
                wait      {self.wait_loop_step}
                loop      R1,@repeatloop
            wait      {extra_wait}
            loop    R0,@loop
            stop
        """
        return program

    @abstractmethod
    def translate(self, sequence, delay_before_readout, nshots):  # pragma: no cover
        """Translates an abstract pulse sequence to QBlox format.

        Args:
            sequence (:class:`qibolab.pulses.PulseSequence`): Pulse sequence.

        Returns:
            The waveforms (dict) and program (str) required to execute the
            pulse sequence on QBlox instruments.
        """
        raise_error(NotImplementedError)

    def upload(self, waveforms, program, data_f):
        """Uploads waveforms and programs to QBlox sequencer to prepare execution."""
        import os
        # Upload waveforms and program
        # Reformat waveforms to lists
        for name, waveform in waveforms.items():
            if isinstance(waveform["data"], np.ndarray):
                waveforms[name]["data"] = waveforms[name]["data"].tolist()  # JSON only supports lists

        # Add sequence program and waveforms to single dictionary and write to JSON file
        filename = f"{self.name}_sequence.json"
        program_dict = {
            "waveforms": waveforms,
            "weights": self.weights,
            "acquisitions": self.acquisitions,
            "program": program
            }

        with open(data_folder / filename, "w", encoding="utf-8") as file:
            json.dump(program_dict, file, indent=4)

        # Upload json file to the device
        if self.sequencer == 1:
            self.device.sequencer1_waveforms_and_program(str(data_folder / filename))
        else:
            self.device.sequencer0_waveforms_and_program(str(data_folder / filename))

    def play_sequence(self):
        """Executes the uploaded instructions."""
        # arm sequencer and start playing sequence
        self.device.arm_sequencer()
        self.device.start_sequencer()

    def stop(self):
        """Stops the QBlox sequencer from sending pulses."""
        self.device.stop_sequencer()

    def close(self):
        """Disconnects from the instrument."""
        if self._connected:
            self.stop()
            self.device.close()
            self._connected = False

    # TODO: Figure out how to fix this
    #def __del__(self):
    #    self.close()


class PulsarQRM(GenericPulsar):
    """Class for interfacing with Pulsar QRM."""

    def __init__(self, label, ip, ref_clock="external", sequencer=0, sync_en=True,
                 hardware_avg_en=True, acq_trigger_mode="sequencer", is_cluster=True):
        super().__init__(label, ip, sequencer, ref_clock, sync_en, is_cluster)
        # Instantiate base object from qblox library and connect to it
        self.name = "qrm"
        self.sequencer = sequencer
        self.hardware_avg_en = hardware_avg_en

        if self.is_cluster:
            from cluster.cluster import cluster_qrm
            self.Device = cluster_qrm
        else:
            from pulsar_qrm.pulsar_qrm import pulsar_qrm
            self.Device = pulsar_qrm

        self.connect()
        if self._connected:
            # Reset and configure
            self.device.reset()
            self.device.reference_source(ref_clock)
            self.device.scope_acq_sequencer_select(sequencer)
            self.device.scope_acq_avg_mode_en_path0(hardware_avg_en)
            self.device.scope_acq_avg_mode_en_path1(hardware_avg_en)
            self.device.scope_acq_trigger_mode_path0(acq_trigger_mode)
            self.device.scope_acq_trigger_mode_path1(acq_trigger_mode)
            # sync sequencer
            if self.sequencer == 1:
                self.device.sequencer1_sync_en(sync_en)
            else:
                self.device.sequencer0_sync_en(sync_en)

    def setup(self, gain, initial_delay, repetition_duration,
              start_sample, integration_length, sampling_rate, mode):
        super().setup(gain, initial_delay, repetition_duration)
        self.start_sample = start_sample
        self.integration_length = integration_length
        self.sampling_rate = sampling_rate
        self.mode = mode

    def translate(self, sequence, delay_before_readout, nshots):
        # Allocate only readout pulses to PulsarQRM
        waveforms = self.generate_waveforms(sequence.qrm_pulses)

        # Generate program without acquire instruction
        initial_delay = sequence.qrm_pulses[0].start
        # Acquire waveforms over remaining duration of acquisition of input vector of length = 16380 with integration weights 0,0
        acquire_instruction = "acquire   0,0,4"
        wait_time = self.duration_base - initial_delay - delay_before_readout - 4 # FIXME: Not sure why this hardcoded 4 is needed
        program = self.generate_program(nshots, initial_delay, delay_before_readout, acquire_instruction, wait_time)

        return waveforms, program

    def play_sequence_and_acquire(self, ro_pulse):
        """Executes the uploaded instructions and retrieves the readout results.

        Args:
            ro_pulse (:class:`qibolab.pulses.Pulse`): Readout pulse to use for
                retrieving the results.
        """
        #arm sequencer and start playing sequence
        super().play_sequence()
        #start acquisition of data
        #Wait for the sequencer to stop with a timeout period of one minute.
        self.device.get_sequencer_state(0, 1)
        #Wait for the acquisition to finish with a timeout period of one second.
        self.device.get_acquisition_state(self.sequencer, 1)
        #Move acquisition data from temporary memory to acquisition list.
        self.device.store_scope_acquisition(self.sequencer, "single")
        #Get acquisition list from instrument.
        single_acq = self.device.get_acquisitions(self.sequencer)
        i, q = self._demodulate_and_integrate(single_acq, ro_pulse)
        acquisition_results = np.sqrt(i**2 + q**2), np.arctan2(q, i), i, q
        return acquisition_results

    def _demodulate_and_integrate(self, single_acq, ro_pulse):
        #DOWN Conversion
        norm_factor = 1. / (self.integration_length)
        n0 = self.start_sample
        n1 = self.start_sample + self.integration_length
        input_vec_I = np.array(single_acq["single"]["acquisition"]["scope"]["path0"]["data"][n0: n1])
        input_vec_Q = np.array(single_acq["single"]["acquisition"]["scope"]["path1"]["data"][n0: n1])
        input_vec_I -= np.mean(input_vec_I)
        input_vec_Q -= np.mean(input_vec_Q)

        if self.mode == 'ssb':
            modulated_i = input_vec_I
            modulated_q = input_vec_Q
            time = np.arange(modulated_i.shape[0])*1e-9
            cosalpha = np.cos(2 * np.pi * ro_pulse.frequency * time)
            sinalpha = np.sin(2 * np.pi * ro_pulse.frequency * time)
            demod_matrix = 2 * np.array([[cosalpha, -sinalpha], [sinalpha, cosalpha]])
            result = []
            for it, t, ii, qq in zip(np.arange(modulated_i.shape[0]), time,modulated_i, modulated_q):
                result.append(demod_matrix[:,:,it] @ np.array([ii, qq]))
            demodulated_signal = np.array(result)
            integrated_signal = norm_factor*np.sum(demodulated_signal,axis=0)

        elif self.mode == 'optimal':  # pragma: no cover
            raise_error(NotImplementedError, "Optimal Demodulation Mode not coded yet.")
        else:  # pragma: no cover
            raise_error(NotImplementedError, "Demodulation mode not understood.")
        return integrated_signal


class PulsarQCM(GenericPulsar):

    def __init__(self, label, ip, sequencer=0, ref_clock="external", sync_en=True, is_cluster=True):
        super().__init__(label, ip, sequencer, ref_clock, sync_en, is_cluster)
        # Instantiate base object from qblox library and connect to it
        self.name = "qcm"
        self.sequencer = sequencer

        if self.is_cluster:
            from cluster.cluster import cluster_qcm
            self.Device = cluster_qcm
        else:
            from pulsar_qcm.pulsar_qcm import pulsar_qcm
            self.Device = pulsar_qcm

        self.connect()
        if self._connected:
            # Reset and configure
            self.device.reset()
            self.device.reference_source(ref_clock)
            if self.sequencer == 1:
                self.device.sequencer1_sync_en(sync_en)
            else:
                self.device.sequencer0_sync_en(sync_en)

    def translate(self, sequence, delay_before_read_out, nshots=None):
        # Allocate only qubit pulses to PulsarQRM
        waveforms = self.generate_waveforms(sequence.qcm_pulses)

        # Generate program without acquire instruction
        initial_delay = sequence.qcm_pulses[0].start
        acquire_instruction = ""
        wait_time = self.duration_base - initial_delay - delay_before_read_out
        program = self.generate_program(nshots, initial_delay, delay_before_read_out, acquire_instruction, wait_time)

        return waveforms, program
