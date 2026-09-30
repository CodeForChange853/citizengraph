"""Working-day arithmetic and suspension checks. Test calendars only: the dates below are
invented fixtures, not real Philippine holidays."""

from datetime import date, datetime

import pytest

from citizengraph.core2.calendar import (
    PHT,
    Calendar,
    check_work_suspension,
    working_days_elapsed,
)

# 2026-03-02 is a Monday.
MON, TUE, WED, THU, FRI, SAT, SUN = (date(2026, 3, d) for d in range(2, 9))
NEXT_MON = date(2026, 3, 9)


def cal(holidays=(), suspensions=()):
    return Calendar(
        holidays={d: "TEST-HOLIDAY" for d in holidays},
        suspensions={d: "TEST-SUSPENSION" for d in suspensions},
    )


class TestWorkingDays:
    def test_same_day_is_zero(self):
        assert working_days_elapsed(MON, MON, cal()) == 0

    def test_counts_days_after_start_up_to_and_including_end(self):
        assert working_days_elapsed(MON, TUE, cal()) == 1
        assert working_days_elapsed(MON, FRI, cal()) == 4

    def test_weekends_are_skipped(self):
        assert working_days_elapsed(FRI, NEXT_MON, cal()) == 1
        assert working_days_elapsed(MON, NEXT_MON, cal()) == 5

    def test_holidays_are_skipped(self):
        assert working_days_elapsed(MON, FRI, cal(holidays=[WED])) == 3

    def test_suspensions_are_skipped(self):
        assert working_days_elapsed(MON, FRI, cal(suspensions=[TUE, WED])) == 2

    def test_a_holiday_and_a_suspension_on_the_same_day_count_once(self):
        assert working_days_elapsed(MON, FRI, cal(holidays=[WED], suspensions=[WED])) == 3

    def test_suspension_on_a_weekend_changes_nothing(self):
        assert working_days_elapsed(MON, NEXT_MON, cal(suspensions=[SAT])) == 5

    def test_start_day_itself_is_never_counted(self):
        assert working_days_elapsed(WED, THU, cal(holidays=[WED])) == 1

    def test_datetimes_are_reduced_to_dates(self):
        a = datetime(2026, 3, 2, 23, 59, tzinfo=PHT)
        b = datetime(2026, 3, 3, 0, 1, tzinfo=PHT)
        assert working_days_elapsed(a, b, cal()) == 1

    def test_end_before_start_is_an_error(self):
        with pytest.raises(ValueError):
            working_days_elapsed(TUE, MON, cal())

    def test_non_dates_are_rejected(self):
        with pytest.raises(TypeError):
            working_days_elapsed("2026-03-02", MON, cal())  # type: ignore[arg-type]

    def test_long_span_is_exact(self):
        # 10 weeks = 50 working days
        assert working_days_elapsed(MON, date(2026, 5, 11), cal()) == 50


class TestSuspensionCheck:
    def test_declared_suspension(self):
        r = check_work_suspension(TUE, cal(suspensions=[TUE]))
        assert r.suspended is True
        assert r.working_day is False
        assert r.reason == "TEST-SUSPENSION"

    def test_ordinary_working_day(self):
        r = check_work_suspension(TUE, cal())
        assert (r.suspended, r.working_day, r.reason) == (False, True, None)

    def test_weekend_is_not_a_suspension(self):
        r = check_work_suspension(SAT, cal())
        assert r.suspended is False
        assert r.working_day is False
        assert r.non_working_reason == "weekend"

    def test_holiday_is_not_a_suspension(self):
        r = check_work_suspension(WED, cal(holidays=[WED]))
        assert r.suspended is False
        assert r.non_working_reason == "holiday"

    def test_suspension_wins_over_holiday_in_the_reason(self):
        r = check_work_suspension(WED, cal(holidays=[WED], suspensions=[WED]))
        assert r.suspended is True
        assert r.non_working_reason == "suspension"

    def test_datetime_input(self):
        assert check_work_suspension(
            datetime(2026, 3, 3, 9, 0, tzinfo=PHT), cal(suspensions=[TUE])
        ).suspended


class TestCalendarObject:
    def test_add_working_days_skips_non_working_days(self):
        c = cal(holidays=[TUE])
        assert c.add_working_days(MON, 1) == WED
        assert c.add_working_days(FRI, 1) == NEXT_MON
        assert c.add_working_days(MON, 0) == MON

    def test_add_working_days_is_inverse_of_working_days_elapsed(self):
        c = cal(holidays=[WED], suspensions=[THU])
        for n in range(12):
            assert working_days_elapsed(MON, c.add_working_days(MON, n), c) == n

    def test_default_calendar_is_empty_apart_from_weekends(self):
        c = Calendar()
        assert c.is_working_day(MON) and not c.is_working_day(SAT)

    def test_from_config_reads_calendar_yaml(self, tmp_path):
        p = tmp_path / "calendar.yaml"
        p.write_text(
            "holidays: ['2026-03-04']\nwork_suspensions:\n  - date: '2026-03-05'\n    reason: t\n",
            encoding="utf-8",
        )
        c = Calendar.from_yaml(p)
        assert c.is_working_day(WED) is False
        assert check_work_suspension(THU, c).suspended

    def test_repo_calendar_is_empty(self):
        """We never invent holidays: the shipped calendar has none until the LGU supplies them."""
        c = Calendar.from_yaml()
        assert c.holidays == {} and c.suspensions == {}

    def test_bad_date_in_yaml_is_an_error(self, tmp_path):
        p = tmp_path / "c.yaml"
        p.write_text("holidays: ['03/04/2026']\n", encoding="utf-8")
        with pytest.raises(ValueError):
            Calendar.from_yaml(p)


class TestSubtract:
    def test_is_the_inverse_of_working_days_elapsed(self):
        c = cal(holidays=[WED], suspensions=[THU])
        for n in range(1, 10):
            start = c.subtract_working_days(NEXT_MON, n)
            assert c.is_working_day(start)
            assert working_days_elapsed(start, NEXT_MON, c) == n

    def test_zero(self):
        assert cal().subtract_working_days(TUE, 0) == TUE
