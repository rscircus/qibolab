from abc import abstractmethod
from dataclasses import dataclass, fields
from typing import Optional

from qibolab.instruments.abstract import Instrument, InstrumentSettings

RECONNECTION_ATTEMPTS = 3
"""Number of times to attempt connecting to instrument in case of failure."""


@dataclass
class LocalOscillatorSettings(InstrumentSettings):
    """Local oscillator parameters that are saved in the platform runcard."""

    power: Optional[float] = None
    frequency: Optional[float] = None
    ref_osc_source: Optional[str] = None

    def dump(self):
        """Dictionary containing local oscillator settings.

        The reference clock is excluded as it is not a calibrated
        parameter. None values are also excluded.
        """
        data = super().dump()
        return {
            k: v for k, v in data.items() if k != "ref_osc_source" and v is not None
        }


def _setter(instrument, parameter, value):
    """Set value of a setting.

    The value of each parameter is cached in the :class:`qibolab.instruments.oscillator.LocalOscillator`.
    If we are connected to the instrument when the setter is called, the new value is also
    automatically uploaded to the instruments. If we are not connected, the new value is cached
    and it is automatically uploaded after we connect.
    If the new value is the same with the cached value, it is not updated.
    """
    if getattr(instrument, parameter) != value:
        setattr(instrument.settings, parameter, value)
        if instrument.is_connected:
            instrument.device.set(parameter, value)


def _property(parameter):
    """Creates an instrument property."""
    getter = lambda self: getattr(self.settings, parameter)
    setter = lambda self, value: _setter(self, parameter, value)
    return property(getter, setter)


class LocalOscillator(Instrument):
    """Abstraction for local oscillator instruments.

    Local oscillators are used to upconvert signals, when the
    controllers cannot send sufficiently high frequencies to address the
    qubits and resonators. They cannot be used to play or sweep pulses.
    """

    frequency = _property("frequency")
    power = _property("power")
    ref_osc_source = _property("ref_osc_source")

    def __init__(self, name, address, ref_osc_source=None):
        super().__init__(name, address)
        self.device = None
        self.settings = LocalOscillatorSettings(ref_osc_source=ref_osc_source)

    @abstractmethod
    def create(self):
        """Create instance of physical device."""

    def connect(self):
        """Connects to the instrument using the IP address set in the
        runcard."""
        if not self.is_connected:
            self.device = self.create()
            self.is_connected = True
            if not self.is_connected:
                raise RuntimeError(f"Unable to connect to {self.name}.")
        else:
            raise RuntimeError(
                f"There is an open connection to the instrument {self.name}."
            )

        for fld in fields(self.settings):
            self.sync(fld.name)

        self.device.on()

    def disconnect(self):
        if self.is_connected:
            self.device.off()
            self.device.close()
            self.is_connected = False

    def sync(self, parameter):
        """Sync parameter value between our cache and the instrument.

        If the parameter value exists in our cache, it is uploaded to the instrument.
        If the value does not exist in our cache, it is downloaded

        Args:
            parameter (str): Parameter name to be synced.
        """
        value = getattr(self, parameter)
        if value is None:
            setattr(self.settings, parameter, self.device.get(parameter))
        else:
            self.device.set(parameter, value)

    def setup(self, **kwargs):
        """Update instrument settings.

        If the instrument is connected the value is automatically uploaded to the instrument.
        Otherwise the value is cached and will be uploaded when connection is established.

        Args:
            **kwargs: Instrument settings loaded from the runcard.
        """
        type_ = self.__class__
        _fields = {fld.name for fld in fields(self.settings)}
        for name, value in kwargs.items():
            if name not in _fields:
                raise KeyError(
                    f"Cannot set {name} to instrument {self.name} of type {type_.__name__}"
                )
            setattr(self, name, value)
