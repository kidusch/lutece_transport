from collections import Counter
from datetime import date, timedelta

from lutece_transport import logic as L

MON = date(2026, 10, 19)  # a Monday


def codes(issues):
    return sorted(i.code for i in issues)


def base_tour(**kw):
    t = {"tour_date": MON, "start_time": "07:30", "end_time": "08:15", "driver": "EMP-1",
         "vehicle": "VD-1", "status": "Planned",
         "passengers": [{"passenger": "P1", "status": "Planned"}, {"passenger": "P2", "status": "Planned"}]}
    t.update(kw)
    return t


def base_ctx(**kw):
    c = {"driver": {"name": "EMP-1", "employee_name": "Abebe", "status": "Active"},
         "vehicle": {"name": "VD-1", "seats": 8, "wheelchair_accessible": 0},
         "passengers": {"P1": {"full_name": "Lea", "contract_start": "2026-09-01"},
                        "P2": {"full_name": "Noah", "contract_start": "2026-09-01"}}}
    c.update(kw)
    return c


def test_clean_tour_has_no_issues():
    assert L.tour_issues(base_tour(), base_ctx()) == []


def test_missing_driver_and_vehicle_are_gaps_not_errors():
    issues = L.tour_issues(base_tour(driver=None, vehicle=None), base_ctx(driver=None, vehicle=None))
    assert codes(issues) == ["NO_DRIVER", "NO_VEHICLE"]
    assert all(i.level == L.GAP and i.flags_tour for i in issues)


def test_driver_double_booking_only_when_times_overlap():
    ctx = base_ctx(driver_conflicts=[{"name": "TOUR-2", "start_time": "08:00", "end_time": "08:40"}])
    assert codes(L.tour_issues(base_tour(), ctx)) == ["DRIVER_DOUBLE_BOOKED"]
    ctx = base_ctx(driver_conflicts=[{"name": "TOUR-2", "start_time": "08:15", "end_time": "09:00"}])
    assert L.tour_issues(base_tour(), ctx) == []  # back-to-back is fine


def test_timedelta_times_from_database():
    ctx = base_ctx(vehicle_conflicts=[{"name": "TOUR-3", "start_time": timedelta(hours=7, minutes=45),
                                       "end_time": timedelta(hours=8, minutes=30)}])
    assert codes(L.tour_issues(base_tour(), ctx)) == ["VEHICLE_DOUBLE_BOOKED"]


def test_driver_on_leave_and_inactive():
    ctx = base_ctx(driver={"name": "EMP-1", "status": "Active", "on_leave": True})
    assert codes(L.tour_issues(base_tour(), ctx)) == ["DRIVER_ON_LEAVE"]
    ctx = base_ctx(driver={"name": "EMP-1", "status": "Left"})
    assert codes(L.tour_issues(base_tour(), ctx)) == ["DRIVER_INACTIVE"]
    ctx = base_ctx(driver={"name": "EMP-1", "status": "Active", "relieving_date": "2026-10-10"})
    assert codes(L.tour_issues(base_tour(), ctx)) == ["DRIVER_LEFT"]


def test_seats_ignore_absent_and_cancelled():
    pax = [{"passenger": f"P{i}", "status": "Planned"} for i in range(3)]
    ctx = base_ctx(vehicle={"name": "VD-1", "seats": 2}, passengers={})
    assert codes(L.tour_issues(base_tour(passengers=pax), ctx)) == ["SEATS_EXCEEDED"]
    pax[0]["status"] = "Absent"
    assert L.tour_issues(base_tour(passengers=pax), ctx) == []


def test_wheelchair_needs_accessible_vehicle():
    ctx = base_ctx()
    ctx["passengers"]["P1"]["wheelchair"] = 1
    assert codes(L.tour_issues(base_tour(), ctx)) == ["WHEELCHAIR"]
    ctx["vehicle"]["wheelchair_accessible"] = 1
    assert L.tour_issues(base_tour(), ctx) == []


def test_passenger_on_two_overlapping_tours_and_duplicates():
    ctx = base_ctx(passenger_conflicts={"P2": [{"name": "TOUR-9", "start_time": "07:00", "end_time": "07:45"}]})
    assert codes(L.tour_issues(base_tour(), ctx)) == ["PASSENGER_DOUBLE_BOOKED"]
    pax = [{"passenger": "P1", "status": "Planned"}, {"passenger": "P1", "status": "Planned"}]
    assert "PASSENGER_DUPLICATE" in codes(L.tour_issues(base_tour(passengers=pax), base_ctx()))


def test_warnings_for_expired_documents_and_contract():
    ctx = base_ctx(driver={"name": "EMP-1", "status": "Active", "licence_valid_until": "2026-10-01",
                           "next_medical_check": "2026-10-18"},
                   vehicle={"name": "VD-1", "seats": 8, "next_inspection": "2026-01-01"})
    ctx["passengers"]["P1"]["contract_end"] = "2026-10-16"
    issues = L.tour_issues(base_tour(), ctx)
    assert codes(issues) == ["CONTRACT", "INSPECTION_OVERDUE", "LICENCE_EXPIRED", "MEDICAL_OVERDUE"]
    assert all(i.level == L.WARNING for i in issues)


def test_cancelled_tour_skips_checks_but_not_time_order():
    assert L.tour_issues(base_tour(status="Cancelled", driver=None), base_ctx()) == []
    assert codes(L.tour_issues(base_tour(end_time="07:00"), base_ctx())) == ["TIME_ORDER"]


def test_template_runs_on():
    flags = {"monday": 1, "wednesday": 1}
    assert L.template_runs_on(flags, None, None, set(), MON)
    assert not L.template_runs_on(flags, None, None, set(), MON + timedelta(days=1))
    assert not L.template_runs_on(flags, None, None, {MON}, MON)
    assert not L.template_runs_on(flags, "2026-10-20", None, set(), MON)
    assert not L.template_runs_on(flags, None, "2026-10-18", set(), MON)


def test_expected_and_missing_trips_handles_midday_and_holidays():
    sched = [{"weekday": "Monday", "direction": "To School"},
             {"weekday": "Monday", "direction": "From School"},   # noon
             {"weekday": "Monday", "direction": "To School"},     # 13:30
             {"weekday": "Monday", "direction": "From School"},   # 16:00
             {"weekday": "Wednesday", "direction": "To School"},
             {"weekday": "Wednesday", "direction": "From School"}]
    days = list(L.daterange(MON, MON + timedelta(days=9)))  # Mon 19 .. Wed 28
    holidays = {MON + timedelta(days=7)}                    # Mon 26 off
    exp = L.expected_trips(sched, "2026-09-01", None, holidays, days)
    assert exp[(MON, "To School")] == 2
    assert (MON + timedelta(days=7), "To School") not in exp
    assert exp[(MON + timedelta(days=2), "From School")] == 1

    actual = Counter({(MON, "To School"): 2, (MON, "From School"): 1})
    missing = L.missing_trips(exp, actual)
    assert missing[0] == {"date": MON, "direction": "From School", "expected": 2, "planned": 1, "missing": 1}
    assert len(missing) == 1 + 2 + 2  # Mon from-school, Wed 21 both, Wed 28 both


def test_contract_window_limits_expectations():
    sched = [{"weekday": "Monday", "direction": "To School"}]
    assert L.expected_trips(sched, "2026-10-20", None, set(), [MON]) == Counter()
    assert L.expected_trips(sched, "2026-09-01", "2026-10-18", set(), [MON]) == Counter()


def test_unaccepted_tour_is_a_gap_only_when_due():
    t = base_tour(accepted=0)
    assert L.tour_issues(t, base_ctx()) == []                       # not due yet
    issues = L.tour_issues(t, base_ctx(acceptance_due=True))
    assert codes(issues) == ["NOT_ACCEPTED"] and issues[0].level == L.GAP
    assert L.tour_issues(base_tour(accepted=1), base_ctx(acceptance_due=True)) == []
    # no driver: only the NO_DRIVER gap, not an acceptance gap
    assert codes(L.tour_issues(base_tour(driver=None, accepted=0), base_ctx(driver=None, acceptance_due=True))) == ["NO_DRIVER"]
