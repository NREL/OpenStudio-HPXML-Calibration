import pathlib

import pytest

from openstudio_hpxml_calibration.hpxml import HpxmlDoc

real_home_hpxmls = list((pathlib.Path(__file__).resolve().parent.parent / "test_hpxmls" / "real_homes").glob("*.xml"))


@pytest.mark.parametrize("filename", real_home_hpxmls, ids=lambda x: x.stem)
def test_hpxml_valid(filename):
    HpxmlDoc(filename)
