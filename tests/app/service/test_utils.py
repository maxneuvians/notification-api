from freezegun import freeze_time

from app.dao.date_util import get_current_financial_year_start_year


# see get_financial_year for conversion of financial years.
@freeze_time("2017-03-31 22:59:59.999999")
def test_get_current_financial_year_start_year_before_march():
    current_fy = get_current_financial_year_start_year()
    assert current_fy == 2016


@freeze_time("2017-04-01 4:00:00.000000")
# This test assumes the local timezone is EST
def test_get_current_financial_year_start_year_after_april():
    current_fy = get_current_financial_year_start_year()
    assert current_fy == 2017
