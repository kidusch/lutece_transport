"""Pure assignment and coverage rules.

Nothing in this module imports frappe, so the rules can be unit-tested
without a bench. The Frappe glue lives in ``coverage.py``.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Iterable

WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
WEEKDAY_LABELS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
DIRECTIONS = ("To School", "From School")

# Passenger rows with these statuses don't occupy a seat.
SEATLESS_STATUSES = ("Cancelled", "Absent")
# Passenger rows with this status don't count as transported.
UNCOVERED_STATUSES = ("Cancelled",)

# Issue levels
ERROR = "error"      # blocks saving a tour
GAP = "gap"          # does not block, but the tour is not covered (no driver / vehicle)
WARNING = "warning"  # informational


@dataclass(frozen=True)
class Issue:
    """A problem found on a tour.

    `template` is a literal English sentence with {0}, {1}... placeholders so the
    Frappe layer can translate it (``_(issue.template).format(*issue.args)``).
    """
    level: str
    code: str
    template: str
    args: tuple = ()

    @property
    def message(self) -> str:
        return self.template.format(*self.args)

    @property
    def flags_tour(self) -> bool:
        return self.level in (ERROR, GAP)


# ---------------------------------------------------------------- helpers

def to_minutes(value) -> int | None:
    """Accept time, timedelta (what MariaDB returns for Time), or 'HH:MM[:SS]'."""
    if value is None or value == "":
        return None
    if isinstance(value, timedelta):
        return int(value.total_seconds() // 60)
    if isinstance(value, datetime):
        return value.hour * 60 + value.minute
    if isinstance(value, time):
        return value.hour * 60 + value.minute
    parts = str(value).split(":")
    return int(parts[0]) * 60 + int(parts[1])


def fmt_time(value) -> str:
    m = to_minutes(value)
    return "" if m is None else f"{m // 60:02d}:{m % 60:02d}"


def to_date(value) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def overlaps(a_start, a_end, b_start, b_end) -> bool:
    """True when two time ranges share at least one minute. Touching ends don't overlap."""
    a0, a1, b0, b1 = map(to_minutes, (a_start, a_end, b_start, b_end))
    if None in (a0, a1, b0, b1):
        return False
    return a0 < b1 and b0 < a1


def daterange(start, end) -> Iterable[date]:
    d, end = to_date(start), to_date(end)
    while d <= end:
        yield d
        d += timedelta(days=1)


def weekday_key(d) -> str:
    return WEEKDAYS[to_date(d).weekday()]


def covers(start, end, d) -> bool:
    """Is day d inside [start, end]? A missing end means open-ended; a missing start means not started."""
    d, start, end = to_date(d), to_date(start), to_date(end)
    if start is None or d < start:
        return False
    return end is None or d <= end


def template_runs_on(weekday_flags: dict, valid_from, valid_to, holidays: set, d) -> bool:
    d = to_date(d)
    if not weekday_flags.get(weekday_key(d)):
        return False
    if valid_from and d < to_date(valid_from):
        return False
    if valid_to and d > to_date(valid_to):
        return False
    return d not in holidays


# ---------------------------------------------------------------- tour checks

def tour_issues(tour: dict, ctx: dict) -> list[Issue]:
    """Check one tour.

    tour: tour_date, start_time, end_time, driver, vehicle, status,
          passengers=[{passenger, status}]
    ctx:  driver           {name, status, relieving_date, on_leave, licence_valid_until, next_medical_check} | None
          vehicle          {name, seats, wheelchair_accessible, next_inspection, insurance_valid_until} | None
          driver_conflicts [{name, start_time, end_time}]  other tours of the same driver that day
          vehicle_conflicts  same for the vehicle
          passengers       {passenger_id: {full_name, wheelchair, contract_start, contract_end}}
          passenger_conflicts {passenger_id: [{name, start_time, end_time}]}
    """
    issues: list[Issue] = []
    add = lambda level, code, template, *args: issues.append(Issue(level, code, template, tuple(args)))
    d = to_date(tour["tour_date"])
    start, end = tour.get("start_time"), tour.get("end_time")

    def span(c):
        return f"{fmt_time(c['start_time'])}–{fmt_time(c['end_time'])}"

    s, e = to_minutes(start), to_minutes(end)
    if s is not None and e is not None and e <= s:
        add(ERROR, "TIME_ORDER", "End time must be after start time.")

    if tour.get("status") in ("Cancelled", "Completed"):
        return issues

    rows = [r for r in tour.get("passengers") or [] if r.get("passenger")]
    riding = [r for r in rows if r.get("status") not in SEATLESS_STATUSES]
    pinfo = ctx.get("passengers") or {}

    # Duplicate passenger rows in the same tour
    seen = Counter(r["passenger"] for r in rows if r.get("status") not in UNCOVERED_STATUSES)
    for pid, n in seen.items():
        if n > 1:
            add(ERROR, "PASSENGER_DUPLICATE", "{0} is listed {1} times on this tour.", _pname(pinfo, pid), n)

    # --- driver
    driver = ctx.get("driver")
    if not tour.get("driver"):
        add(GAP, "NO_DRIVER", "No driver assigned.")
    elif driver:
        name = driver.get("employee_name") or driver.get("name")
        if driver.get("status") and driver["status"] != "Active":
            add(ERROR, "DRIVER_INACTIVE", "Driver {0} is not active ({1}).", name, driver["status"])
        elif driver.get("relieving_date") and to_date(driver["relieving_date"]) <= d:
            add(ERROR, "DRIVER_LEFT", "Driver {0} has left on {1}.", name, to_date(driver["relieving_date"]))
        if driver.get("on_leave"):
            add(ERROR, "DRIVER_ON_LEAVE", "Driver {0} is on approved leave on {1}.", name, d)
        for c in ctx.get("driver_conflicts") or []:
            if overlaps(start, end, c["start_time"], c["end_time"]):
                add(ERROR, "DRIVER_DOUBLE_BOOKED", "Driver {0} is already on {1} ({2}).", name, c["name"], span(c))
        lic = to_date(driver.get("licence_valid_until"))
        if lic and lic < d:
            add(WARNING, "LICENCE_EXPIRED", "Driver {0}'s licence expired on {1}.", name, lic)
        med = to_date(driver.get("next_medical_check"))
        if med and med < d:
            add(WARNING, "MEDICAL_OVERDUE", "Driver {0}'s medical check was due on {1}.", name, med)
        # The driver must accept the tour; from the day before it runs, an unaccepted tour is a gap.
        if not tour.get("accepted") and ctx.get("acceptance_due"):
            add(GAP, "NOT_ACCEPTED", "Driver {0} has not accepted this tour yet.", name)

    # --- vehicle
    vehicle = ctx.get("vehicle")
    if not tour.get("vehicle"):
        add(GAP, "NO_VEHICLE", "No vehicle assigned.")
    elif vehicle:
        vname = vehicle.get("name")
        for c in ctx.get("vehicle_conflicts") or []:
            if overlaps(start, end, c["start_time"], c["end_time"]):
                add(ERROR, "VEHICLE_DOUBLE_BOOKED", "Vehicle {0} is already on {1} ({2}).", vname, c["name"], span(c))
        seats = vehicle.get("seats") or 0
        if seats and len(riding) > seats:
            add(ERROR, "SEATS_EXCEEDED", "{0} passengers but vehicle {1} has {2} seats.", len(riding), vname, seats)
        if not vehicle.get("wheelchair_accessible"):
            for r in riding:
                if (pinfo.get(r["passenger"]) or {}).get("wheelchair"):
                    add(ERROR, "WHEELCHAIR", "{0} needs a wheelchair-accessible vehicle; {1} is not.",
                        _pname(pinfo, r["passenger"]), vname)
        insp = to_date(vehicle.get("next_inspection"))
        if insp and insp < d:
            add(WARNING, "INSPECTION_OVERDUE", "Vehicle {0}'s inspection was due on {1}.", vname, insp)
        ins = to_date(vehicle.get("insurance_valid_until"))
        if ins and ins < d:
            add(WARNING, "INSURANCE_EXPIRED", "Vehicle {0}'s insurance ended on {1}.", vname, ins)

    # --- passengers
    if not riding:
        add(WARNING, "NO_PASSENGERS", "No passengers on this tour.")
    for r in riding:
        pid = r["passenger"]
        info = pinfo.get(pid) or {}
        if info and not covers(info.get("contract_start"), info.get("contract_end"), d):
            add(WARNING, "CONTRACT", "{0}'s contract does not cover {1}.", _pname(pinfo, pid), d)
        for c in (ctx.get("passenger_conflicts") or {}).get(pid, []):
            if overlaps(start, end, c["start_time"], c["end_time"]):
                add(ERROR, "PASSENGER_DOUBLE_BOOKED", "{0} is already on {1} ({2}).", _pname(pinfo, pid), c["name"], span(c))
    return issues


def _pname(pinfo, pid):
    return (pinfo.get(pid) or {}).get("full_name") or pid


# ---------------------------------------------------------------- passenger coverage

def expected_trips(schedule_rows, contract_start, contract_end, holidays: set, dates) -> Counter:
    """How many trips a passenger needs per (date, direction).

    schedule_rows: [{weekday: 'Monday', direction: 'To School'}] — one row per required trip,
    so a child going home at noon and back to school at 13:30 has two rows for that weekday.
    """
    per_weekday = Counter()
    for r in schedule_rows:
        wd = (r.get("weekday") or "").lower()
        if wd in WEEKDAYS and r.get("direction") in DIRECTIONS:
            per_weekday[(wd, r["direction"])] += 1
    out = Counter()
    for d in dates:
        d = to_date(d)
        if d in holidays or not covers(contract_start, contract_end, d):
            continue
        wd = weekday_key(d)
        for direction in DIRECTIONS:
            n = per_weekday.get((wd, direction), 0)
            if n:
                out[(d, direction)] = n
    return out


def missing_trips(expected: Counter, actual: Counter) -> list[dict]:
    """Rows where a passenger has fewer trips than required."""
    rows = []
    for (d, direction), need in sorted(expected.items()):
        have = actual.get((d, direction), 0)
        if have < need:
            rows.append({"date": d, "direction": direction, "expected": need, "planned": have,
                         "missing": need - have})
    return rows
