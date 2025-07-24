import pathlib

import pytest

from openstudio_hpxml_calibration.hpxml import HpxmlDoc

repo_root = pathlib.Path(__file__).resolve().parent.parent
ira_rebate_hpxmls = list((repo_root / "test_hpxmls" / "ira_rebates").glob("*.xml"))
real_home_hpxmls = list((repo_root / "test_hpxmls" / "real_homes").glob("*.xml"))
ihmh_home_hpxmls = list((repo_root / "test_hpxmls" / "ihmh_homes").glob("*.xml"))


@pytest.mark.parametrize(
    "filename", ira_rebate_hpxmls + real_home_hpxmls + ihmh_home_hpxmls, ids=lambda x: x.stem
)
def test_hpxml_valid(filename):
    HpxmlDoc(filename)
