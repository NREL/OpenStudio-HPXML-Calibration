import pathlib

import pytest

from openstudio_hpxml_calibration.hpxml import HpxmlDoc

sample_files = list((pathlib.Path(__file__).resolve().parent.parent / "sample_files").glob("*.xml"))


@pytest.mark.parametrize("filename", sample_files, ids=lambda x: x.stem)
def test_hpxml_valid(filename):
    HpxmlDoc(filename)
