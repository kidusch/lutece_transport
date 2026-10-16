"""What a driver can do from the "Mes tournées" page.

Drivers have read-only access to tours. These methods are the only way they change
anything, and each one checks that the tour belongs to the driver calling it:
accept a tour, mark each passenger picked up or absent, and complete the tour.
"""

import frappe
from frappe import _
from frappe.utils import add_days, escape_html, format_date, get_url_to_form, getdate, now_datetime, nowdate

from lutece_transport import logic as L

DRIVER_STATUSES = ("Planned", "Picked Up", "Absent")


def _my_employee():
	if frappe.session.user in ("Guest", None):
		frappe.throw(_("Please log in."), frappe.PermissionError)
	emp = frappe.db.get_value("Employee", {"user_id": frappe.session.user, "status": "Active"}, ["name", "employee_name"], as_dict=True)
	if not emp:
		frappe.throw(_("Your user account is not linked to an active driver (Employee)."), frappe.PermissionError)
	return emp


def _my_tour(tour):
	emp = _my_employee()
	doc = frappe.get_doc("Tour", tour)
	if doc.driver != emp.name:
		frappe.throw(_("This tour is not assigned to you."), frappe.PermissionError)
	if doc.status == "Cancelled":
		frappe.throw(_("This tour has been cancelled."))
	return emp, doc


def _save(doc):
	doc.flags.ignore_permissions = True
	doc.flags.ignore_coverage_errors = True  # the driver's action must never be blocked by a planning issue
	doc.save()
	frappe.db.commit()


def _tour_payload(doc):
	return {
		"name": doc.name, "title": doc.tour_template or _(doc.direction), "date": str(doc.tour_date),
		"date_label": format_date(doc.tour_date), "direction": _(doc.direction),
		"start": L.fmt_time(doc.start_time), "end": L.fmt_time(doc.end_time),
		"vehicle": doc.vehicle, "school": doc.school, "status": doc.status,
		"accepted": bool(doc.accepted), "completed": doc.status == "Completed",
		"passengers": [
			{"row": p.name, "name": p.passenger_name or p.passenger, "time": L.fmt_time(p.pickup_time),
			 "pickup": p.pickup_address or "", "dropoff": p.dropoff_address or "", "status": p.status}
			for p in sorted(doc.passengers, key=lambda r: (L.to_minutes(r.pickup_time) or 0, r.idx))
			if p.status != "Cancelled"
		],
	}


@frappe.whitelist()
def get_my_tours(date=None):
	"""The driver's tours for one day, plus upcoming tours still waiting for acceptance."""
	emp = _my_employee()
	day = getdate(date or nowdate())
	names = frappe.get_all("Tour", filters={"driver": emp.name, "tour_date": day, "status": ["!=", "Cancelled"]},
						   order_by="start_time asc", pluck="name")
	pending = frappe.get_all(
		"Tour",
		filters={"driver": emp.name, "status": "Planned", "accepted": 0,
				 "tour_date": ["between", [getdate(nowdate()), getdate(add_days(nowdate(), 7))]]},
		fields=["name", "tour_date", "start_time", "tour_template", "direction"], order_by="tour_date asc, start_time asc",
	)
	return {
		"driver": emp.employee_name, "date": str(day), "date_label": format_date(day),
		"tours": [_tour_payload(frappe.get_doc("Tour", n)) for n in names],
		"to_accept": [{"name": t.name, "label": f"{format_date(t.tour_date)} · {L.fmt_time(t.start_time)} · {t.tour_template or _(t.direction)}"} for t in pending],
	}


@frappe.whitelist(methods=["POST"])
def accept_tour(tour):
	_emp, doc = _my_tour(tour)
	if doc.status != "Planned":
		frappe.throw(_("Only a planned tour can be accepted."))
	if not doc.accepted:
		doc.accepted, doc.accepted_on = 1, now_datetime()
		_save(doc)
	return _tour_payload(doc)


@frappe.whitelist(methods=["POST"])
def set_passenger_status(tour, row, status):
	emp, doc = _my_tour(tour)
	if status not in DRIVER_STATUSES:
		frappe.throw(_("Invalid status."))
	if doc.status != "Planned":
		frappe.throw(_("This tour is already completed."))
	if getdate(doc.tour_date) > getdate(nowdate()):
		frappe.throw(_("You can only update today's tours."))
	line = next((p for p in doc.passengers if p.name == row), None)
	if not line or line.status == "Cancelled":
		frappe.throw(_("This passenger is not on the tour."))
	previous = line.status
	line.status, line.status_time = status, now_datetime()
	if not doc.accepted:
		doc.accepted, doc.accepted_on = 1, now_datetime()  # working the tour means it was accepted
	_save(doc)
	if status == "Absent" and previous != "Absent":
		_notify_absence(doc, line, emp)
	return _tour_payload(doc)


@frappe.whitelist(methods=["POST"])
def complete_tour(tour):
	_emp, doc = _my_tour(tour)
	if doc.status == "Completed":
		return _tour_payload(doc)
	if getdate(doc.tour_date) > getdate(nowdate()):
		frappe.throw(_("You can only complete today's tours."))
	waiting = [p.passenger_name or p.passenger for p in doc.passengers if p.status == "Planned"]
	if waiting:
		frappe.throw(_("Mark every passenger as picked up or absent first: {0}").format(", ".join(waiting)))
	doc.status, doc.completed_on = "Completed", now_datetime()
	if not doc.accepted:
		doc.accepted, doc.accepted_on = 1, now_datetime()
	_save(doc)
	return _tour_payload(doc)


def _notify_absence(doc, line, emp):
	from lutece_transport.notifications import _send, dispatcher_emails

	who = line.passenger_name or line.passenger
	when = now_datetime().strftime("%H:%M")
	msg = _("{0} was not picked up (absent) – reported by {1} at {2}.").format(who, emp.employee_name, when)
	doc.add_comment("Comment", msg)
	recipients = dispatcher_emails()
	if recipients:
		_send(
			recipients=recipients,
			subject=_("Absence: {0} – {1} {2}").format(who, format_date(doc.tour_date), L.fmt_time(doc.start_time)),
			message=f"<p>{escape_html(msg)}</p><p>{escape_html(doc.tour_template or '')} · "
					f'<a href="{get_url_to_form("Tour", doc.name)}">{doc.name}</a></p>',
			reference_doctype="Tour", reference_name=doc.name,
		)
