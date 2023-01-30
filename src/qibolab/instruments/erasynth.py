"""ERAsynth drivers.

Supports the ERAsynth ++.

https://qcodes.github.io/Qcodes_contrib_drivers/_modules/qcodes_contrib_drivers/drivers/ERAInstruments/erasynth.html#ERASynthBase.clear_read_buffer
"""

from qcodes_contrib_drivers.drivers.ERAInstruments import ERASynthPlusPlus
from qibolab.instruments.abstract import AbstractInstrument, InstrumentException


class ERA(AbstractInstrument):
    def __init__(self, name, address):
        super().__init__(name, address)
        self.device: ERASynthPlusPlus = None
        self.power: int
        self.frequency: int
        self._device_parameters = {}

    rw_property_wrapper = lambda parameter: property(
        lambda self: self.device.get(parameter),
        lambda self, x: self._set_device_parameter(parameter, x),
    )
    power = rw_property_wrapper("power")
    frequency = rw_property_wrapper("frequency")

    def connect(self):
        """
        Connects to the instrument using the IP address set in the runcard.
        """
        if not self.is_connected:
            for attempt in range(3):
                try:
                    self.device = ERASynthPlusPlus(f'{self.name}', f"ASRL{self.address}")
                    self.is_connected = True
                    break
                except KeyError as exc:
                    print(f"Unable to connect:\n{str(exc)}\nRetrying...")
                    self.name += "_" + str(attempt)
                except Exception as exc:
                    print(f"Unable to connect:\n{str(exc)}\nRetrying...")
            if not self.is_connected:
                raise InstrumentException(self, f"Unable to connect to {self.name}")
        else:
            raise Exception("There is an open connection to the instrument already")

    def _set_device_parameter(self, parameter: str, value):
        """Sets a parameter of the instrument, if it changed from the last stored in the cache.

        Args:
            parameter: str = The parameter to be cached and set.
            value = The value to set the paramter.
        Raises:
            Exception = If attempting to set a parameter without a connection to the instrument.
        """
        if not (parameter in self._device_parameters and self._device_parameters[parameter] == value):
            if self.is_connected:
                if not parameter in self._device_parameters:
                    if not hasattr(self.device, parameter):
                        raise Exception(f"The instrument {self.name} does not have parameter {parameter}")
                    self.device.set(parameter, value)
                else:
                    self.device.set(parameter, value)
                self._device_parameters[parameter] = value
            else:
                raise Exception(f"Attempting to set {parameter} without a connection to the instrument")

    def _erase_device_parameters_cache(self):
        """Erases the cache of the instrument parameters."""
        self._device_parameters = {}

    def setup(self, **kwargs):
        """Configures the instrument.

        A connection to the instrument needs to be established beforehand.
        Args:
            **kwargs: dict = A dictionary of settings loaded from the runcard:
                kwargs["power"]
                kwargs["frequency"]
        Raises:
            Exception = If attempting to set a parameter without a connection to the instrument.
        """

        if self.is_connected:
            # Load settings
            self.power = kwargs["power"]
            self.frequency = kwargs["frequency"]
            if kwargs["reference_clock_source"] == "internal":
                self.device.ref_osc_source("int")
            elif kwargs["reference_clock_source"] == "external":
                self.device.ref_osc_source("ext")
            else:
                raise Exception("Invalid reference clock source")
        else:
            raise Exception("There is no connection to the instrument")

    def start(self):
        self.device.on()

    def stop(self):
        self.device.off()

    def disconnect(self):
        if self.is_connected:
            self.device.close()
            self.is_connected = False

    def __del__(self):
        self.disconnect()

    def on(self):
        self.device.on()

    def off(self):
        self.device.off()

    def close(self):
        if self.is_connected:
            self.device.close()
            self.is_connected = False
