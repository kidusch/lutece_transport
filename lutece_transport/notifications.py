"""Daily coverage email and alerts when a driver becomes unavailable."""

import frappe
from frappe.utils import add_days, escape_html, format_date, get_url_to_form, getdate, nowdate

from lutece_transport.coverage import passengers_without_transport, refresh_issue_flags, uncovered_tours


def dispatcher_emails():
	users = frappe.get_all("Has Role", filters={"role": "Transport Dispatcher", "parenttype": "User"},
						   pluck="parent")
	if not users:
		return []
	return frappe.get_all("User", filters=[["name", "in", users], ["enabled", "=", 1],
										   ["name", "not in", ["Administrator", "Guest"]]], pluck="email")


def _send(**kwargs):
	"""Queue an email without ever breaking the action that triggered it (e.g. a leave approval)."""
	try:
		frappe.sendmail(**kwargs)
	except Exception:
		frappe.log_error(title="Lutece Transport: could not queue email")
		frappe.clear_last_message()


# ---------------------------------------------------------------- daily digest

def send_daily_digest():
	settings = frappe.get_cached_doc("Transport Settings")
	start = getdate(nowdate())
	end = getdate(add_days(start, int(settings.digest_days or 3)))

	refresh_issue_flags(start, end)
	tours = uncovered_tours(start, end)
	passengers = passengers_without_transport(start, end)

	if not tours and not passengers and not settings.send_all_clear:
		return
	recipients = dispatcher_emails()
	if not recipients:
		return

	period = f"{format_date(start)} – {format_date(end)}"
	if not tours and not passengers:
		subject = f"Transport: everything covered ({period})"
		body = f"<p>All planned tours have a driver and a vehicle, and every passenger is on a tour, for {period}.</p>"
	else:
		subject = (f"Transport: {len({t['tour'] for t in tours})} tour(s) and "
				   f"{len({(p['passenger'], p['date']) for p in passengers})} passenger-day(s) need attention ({period})")
		body = _digest_html(tours, passengers, period)

	_send(recipients=recipients, subject=subject, message=body, reference_doctype="Transport Settings",
					reference_name="Transport Settings")


def _digest_html(tours, passengers, period):
	parts = [f"<p>Coverage check for {period}.</p>"]
	if tours:
		parts.append("<h3>Tours with problems</h3><ul>")
		for t in tours:
			link = f'<a href="{get_url_to_form("Tour", t["tour"])}">{t["tour"]}</a>'
			parts.append(
				f"<li><b>{format_date(t['tour_date'])} {t['start_time']}</b> – "
				f"{escape_html(t['tour_template'] or t['direction'] or '')} ({link}): {escape_html(t['issue'])}</li>"
			)
		parts.append("</ul>")
	if passengers:
		parts.append("<h3>Passengers not on any tour</h3><ul>")
		for p in passengers:
			when = f"{format_date(p['date'])} {p['direction']}" if p.get("date") else ""
			link = f'<a href="{get_url_to_form("Passenger", p["passenger"])}">{escape_html(p["passenger_name"] or p["passenger"])}</a>'
			parts.append(f"<li>{link} {when}: {escape_html(p['note'])}"
						 + (f" ({p['planned']} of {p['expected']})" if p.get("expected") else "") + "</li>")
		parts.append("</ul>")
	return "".join(parts)


# ---------------------------------------------------------------- driver becomes unavailable

def _alert_for_tours(employee, employee_name, reason, filters):
	tours = frappe.get_all("Tour", filters={"driver": employee, "status": "Planned", **filters},
						   fields=["name", "tour_date", "start_time", "tour_template"], order_by="tour_date, start_time")
	if not tours:
		return
	for t in tours:
		doc = frappe.get_doc("Tour", t.name)
		doc.add_comment("Comment", f"Driver {employee_name} unavailable: {reason}. Please reassign.")
		doc.db_set({"has_issues": 1,
					"coverage_issues": ((doc.coverage_issues or "") + f"\n• Driver unavailable: {reason}").strip()},
				   update_modified=False)

	recipients = dispatcher_emails()
	if recipients:
		items = "".join(
			f'<li>{format_date(t.tour_date)} {str(t.start_time)[:5]} – {escape_html(t.tour_template or "")} '
			f'(<a href="{get_url_to_form("Tour", t.name)}">{t.name}</a>)</li>'
			for t in tours
		)
		_send(
			recipients=recipients,
			subject=f"Reassign {len(tours)} tour(s): {employee_name} unavailable",
			message=f"<p>{escape_html(employee_name)} is unavailable ({escape_html(reason)}). "
					f"These planned tours need another driver:</p><ul>{items}</ul>",
		)


def on_leave_approved(doc, method=None):
	if doc.docstatus != 1 or doc.status != "Approved":
		return
	_alert_for_tours(doc.employee, doc.employee_name or doc.employee,
					 f"leave {format_date(doc.from_date)} – {format_date(doc.to_date)}",
					 {"tour_date": ["between", [doc.from_date, doc.to_date]]})


def on_employee_update(doc, method=None):
	before = doc.get_doc_before_save()
	if not before:
		return
	became_inactive = before.status == "Active" and doc.status != "Active"
	new_relieving = doc.relieving_date and doc.relieving_date != before.relieving_date
	if became_inactive:
		_alert_for_tours(doc.name, doc.employee_name, f"status changed to {doc.status}",
						 {"tour_date": [">=", nowdate()]})
	elif new_relieving:
		_alert_for_tours(doc.name, doc.employee_name, f"leaving on {format_date(doc.relieving_date)}",
						 {"tour_date": [">=", doc.relieving_date]})
