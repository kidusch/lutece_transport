"""Frappe glue: load ERPNext/HRMS data and run the rules in logic.py."""

from collections import Counter
from datetime import date

import frappe
from frappe import _
from frappe.utils import add_days, format_date, getdate, nowdate

from lutece_transport import logic as L

ACTIVE_TOUR = ["!=", "Cancelled"]


# ---------------------------------------------------------------- holidays

def get_holidays(holiday_list, from_date, to_date) -> set:
    if not holiday_list:
        return set()
    return {
        getdate(d)
        for d in frappe.get_all(
            "Holiday",
            filters={"parent": holiday_list, "parenttype": "Holiday List",
                     "holiday_date": ["between", [from_date, to_date]]},
            pluck="holiday_date",
        )
    }


def resolve_holiday_list(template_holiday_list=None, school=None):
    if template_holiday_list:
        return template_holiday_list
    if school:
        hl = frappe.db.get_value("Transport School", school, "holiday_list")
        if hl:
            return hl
    return frappe.db.get_single_value("Transport Settings", "default_holiday_list")


# ---------------------------------------------------------------- driver / vehicle

def _has_field(doctype, fieldname):
    return frappe.get_meta(doctype).has_field(fieldname)


def driver_info(employee, on_date):
    if not employee:
        return None
    fields = ["name", "employee_name", "status", "relieving_date"]
    for extra in ("custom_licence_valid_until", "custom_next_medical_check"):
        if _has_field("Employee", extra):
            fields.append(extra)
    row = frappe.db.get_value("Employee", employee, fields, as_dict=True)
    if not row:
        return None
    row["licence_valid_until"] = row.pop("custom_licence_valid_until", None)
    row["next_medical_check"] = row.pop("custom_next_medical_check", None)
    row["on_leave"] = driver_on_leave(employee, on_date)
    return row


def driver_on_leave(employee, on_date) -> bool:
    if not frappe.db.exists("DocType", "Leave Application"):
        return False
    return bool(frappe.db.exists("Leave Application", {
        "employee": employee, "docstatus": 1, "status": "Approved",
        "from_date": ["<=", on_date], "to_date": [">=", on_date],
    }))


def vehicle_info(vehicle):
    if not vehicle:
        return None
    mapping = {"custom_seats": "seats", "custom_wheelchair_accessible": "wheelchair_accessible",
               "custom_next_inspection": "next_inspection", "end_date": "insurance_valid_until"}
    fields = ["name"] + [k for k in mapping if _has_field("Vehicle", k)]
    row = frappe.db.get_value("Vehicle", vehicle, fields, as_dict=True)
    if not row:
        return None
    return {mapping.get(k, k): v for k, v in row.items()}


# ---------------------------------------------------------------- conflicts

def _other_tours(field, value, on_date, exclude):
    if not value:
        return []
    return frappe.get_all(
        "Tour",
        filters={field: value, "tour_date": on_date, "status": ACTIVE_TOUR, "name": ["!=", exclude or ""]},
        fields=["name", "start_time", "end_time"],
    )


def _passenger_conflicts(passenger_ids, on_date, exclude):
    if not passenger_ids:
        return {}
    rows = frappe.db.sql(
        """
        select tp.passenger, t.name, t.start_time, t.end_time
        from `tabTour Passenger` tp
        join `tabTour` t on t.name = tp.parent and tp.parenttype = 'Tour'
        where t.tour_date = %(d)s and t.status != 'Cancelled' and t.name != %(ex)s
          and tp.status != 'Cancelled' and tp.passenger in %(pids)s
        """,
        {"d": on_date, "ex": exclude or "", "pids": tuple(passenger_ids)},
        as_dict=True,
    )
    out = {}
    for r in rows:
        out.setdefault(r.passenger, []).append(r)
    return out


def _passenger_info(passenger_ids):
    if not passenger_ids:
        return {}
    rows = frappe.get_all(
        "Passenger", filters={"name": ["in", list(passenger_ids)]},
        fields=["name", "full_name", "wheelchair", "contract_start", "contract_end"],
    )
    return {r.name: r for r in rows}


# ---------------------------------------------------------------- tour checks

def tour_as_dict(doc):
    d = doc if isinstance(doc, dict) else doc.as_dict()
    return {
        "name": d.get("name"), "tour_date": getdate(d.get("tour_date")),
        "start_time": d.get("start_time"), "end_time": d.get("end_time"),
        "driver": d.get("driver"), "vehicle": d.get("vehicle"), "status": d.get("status"),
        "passengers": [{"passenger": p.get("passenger"), "status": p.get("status")}
                       for p in d.get("passengers") or []],
    }


def check_tour(doc):
    """Return the list of logic.Issue for a Tour document or dict."""
    t = tour_as_dict(doc)
    pids = {p["passenger"] for p in t["passengers"] if p["passenger"] and p["status"] != "Cancelled"}
    ctx = {
        "driver": driver_info(t["driver"], t["tour_date"]),
        "vehicle": vehicle_info(t["vehicle"]),
        "driver_conflicts": _other_tours("driver", t["driver"], t["tour_date"], t["name"]),
        "vehicle_conflicts": _other_tours("vehicle", t["vehicle"], t["tour_date"], t["name"]),
        "passengers": _passenger_info(pids),
        "passenger_conflicts": _passenger_conflicts(pids, t["tour_date"], t["name"]),
    }
    return L.tour_issues(t, ctx)


def issue_text(issue):
    """The issue in the user's language, with dates in their date format."""
    args = [format_date(a) if isinstance(a, date) else a for a in issue.args]
    return _(issue.template).format(*args)


def format_issues(issues):
    return "\n".join(f"• {issue_text(i)}" for i in issues)


# ---------------------------------------------------------------- reports

def default_range(from_date=None, to_date=None, days=7):
    from_date = getdate(from_date or nowdate())
    to_date = getdate(to_date or add_days(from_date, days))
    return from_date, to_date


def uncovered_tours(from_date=None, to_date=None, include_warnings=False):
    """Planned tours in the range that have errors or gaps (no driver / no vehicle)."""
    from_date, to_date = default_range(from_date, to_date)
    names = frappe.get_all(
        "Tour", filters={"tour_date": ["between", [from_date, to_date]], "status": "Planned"},
        order_by="tour_date asc, start_time asc", pluck="name",
    )
    out = []
    for name in names:
        doc = frappe.get_doc("Tour", name)
        for issue in check_tour(doc):
            if issue.flags_tour or include_warnings:
                out.append({
                    "tour_date": doc.tour_date, "tour": doc.name, "tour_template": doc.tour_template,
                    "direction": doc.direction, "start_time": L.fmt_time(doc.start_time),
                    "driver": doc.driver, "driver_name": doc.driver_name, "vehicle": doc.vehicle,
                    "passengers": sum(1 for p in doc.passengers if p.status not in L.SEATLESS_STATUSES),
                    "level": issue.level, "issue": issue_text(issue),
                })
    return out


def passengers_without_transport(from_date=None, to_date=None):
    """Active passengers who have fewer trips planned than their Required Trips say."""
    from_date, to_date = default_range(from_date, to_date)
    dates = list(L.daterange(from_date, to_date))

    passengers = frappe.get_all(
        "Passenger",
        filters={"contract_start": ["<=", to_date]},
        or_filters=[["contract_end", "is", "not set"], ["contract_end", ">=", from_date]],
        fields=["name", "full_name", "school", "contract_start", "contract_end"],
    )
    if not passengers:
        return []

    schedules = {}
    for r in frappe.get_all("Passenger Schedule",
                            filters={"parenttype": "Passenger", "parent": ["in", [p.name for p in passengers]]},
                            fields=["parent", "weekday", "direction"]):
        schedules.setdefault(r.parent, []).append(r)

    actual = Counter()
    for r in frappe.db.sql(
        """
        select tp.passenger, t.tour_date, t.direction, count(*) as n
        from `tabTour Passenger` tp
        join `tabTour` t on t.name = tp.parent and tp.parenttype = 'Tour'
        where t.tour_date between %(a)s and %(b)s and t.status != 'Cancelled' and tp.status != 'Cancelled'
        group by tp.passenger, t.tour_date, t.direction
        """, {"a": from_date, "b": to_date}, as_dict=True,
    ):
        actual[(r.passenger, getdate(r.tour_date), r.direction)] += r.n

    holiday_cache = {}
    out = []
    for p in passengers:
        rows = schedules.get(p.name)
        if not rows:
            out.append({"passenger": p.name, "passenger_name": p.full_name, "school": p.school,
                        "date": None, "direction": None, "expected": None, "planned": None, "missing": None,
                        "note": _("No required trips entered on the passenger")})
            continue
        hl = resolve_holiday_list(None, p.school)
        if hl not in holiday_cache:
            holiday_cache[hl] = get_holidays(hl, from_date, to_date)
        expected = L.expected_trips(rows, p.contract_start, p.contract_end, holiday_cache[hl], dates)
        mine = Counter({(d, direction): n for (pid, d, direction), n in actual.items() if pid == p.name})
        for m in L.missing_trips(expected, mine):
            out.append({"passenger": p.name, "passenger_name": p.full_name, "school": p.school,
                        "note": _("No driver run planned") if m["planned"] == 0 else _("Fewer runs than required"),
                        **m})
    out.sort(key=lambda r: (r["date"] or getdate("1900-01-01"), r["passenger_name"] or ""))
    return out


def refresh_issue_flags(from_date=None, to_date=None):
    """Recompute has_issues / coverage_issues on planned tours (things change after saving: leave, a driver leaving)."""
    from_date, to_date = default_range(from_date, to_date)
    for name in frappe.get_all("Tour", filters={"tour_date": ["between", [from_date, to_date]],
                                                "status": "Planned"}, pluck="name"):
        doc = frappe.get_doc("Tour", name)
        issues = check_tour(doc)
        flagged = [i for i in issues if i.flags_tour]
        text = format_issues(issues)
        if (doc.has_issues or 0) != (1 if flagged else 0) or (doc.coverage_issues or "") != text:
            doc.db_set({"has_issues": 1 if flagged else 0, "coverage_issues": text}, update_modified=False)
