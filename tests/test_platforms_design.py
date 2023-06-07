import pytest

from qibolab import create_platform
from qibolab.instruments.qblox.controller import QbloxController
from qibolab.platform import Platform

qubit = 0


@pytest.fixture
def platform(platform_name):
    _platform = create_platform(platform_name)
    if isinstance(_platform, QbloxController):
        pytest.skip(f"Skipping Platform test for {_platform.name}")
    return _platform


def test_platform_lo_drive_frequency(platform):
    platform.set_lo_drive_frequency(qubit, 1e9)
    assert platform.get_lo_drive_frequency(qubit) == 1e9


def test_platform_lo_readout_frequency(platform):
    platform.set_lo_readout_frequency(qubit, 1e9)
    assert platform.get_lo_readout_frequency(qubit) == 1e9


def test_platform_attenuation(platform):
    with pytest.raises(NotImplementedError):
        platform.set_attenuation(qubit, 10)
    with pytest.raises(NotImplementedError):
        platform.get_attenuation(qubit)


def test_platform_gain(platform):
    with pytest.raises(NotImplementedError):
        platform.set_gain(qubit, 0)
    with pytest.raises(NotImplementedError):
        platform.get_gain(qubit)


def test_platform_bias(platform):
    platform.set_bias(qubit, 0)
    assert platform.get_bias(qubit) == 0
