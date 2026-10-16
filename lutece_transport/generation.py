"""Create the daily Tour records from active Tour Templates."""

import frappe
from frappe.utils import add_days, getdate, nowdate

from lutece_transport import logic as L
from lutece_transport.coverage import get_holidays, resolve_holiday_list


def scheduled_generate():
	generate_tours()


def template_rows_for_date(tpl, on_date):
	"""Template passengers whose transport contract covers the date."""
	contracts = {
		p.name: p
		for p in frappe.get_all(
			"Passenger",
			filters={"name": ["in", [r.passenger for r in tpl.passengers] or [""]]},
			fields=["name", "contract_start", "contract_end"],
		)
	}
	out = []
	for r in tpl.passengers:
		c = contracts.get(r.passenger)
		if c and L.covers(c.contract_start, c.contract_end, on_date):
			out.append({
				"passenger": r.passenger, "passenger_name": r.passenger_name,
				"pickup_time": r.pickup_time, "pickup_address": r.pickup_address,
				"dropoff_address": r.dropoff_address, "status": "Planned", "from_template": 1,
			})
	return out


def generate_tours(days=None, template=None):
	"""Create missing tours for the next `days` days and keep planned ones in step with their template.

	Safe to run any number of times. Tours are saved even when they have problems
	(no driver, driver on leave, too many passengers...) so that the gaps appear in the
	coverage reports and the daily email rather than the tour silently not existing.
	"""
	settings = frappe.get_cached_doc("Transport Settings")
	start = getdate(nowdate())
	end = getdate(add_days(start, int(days or settings.horizon_days or 14)))

	filters = {"is_active": 1}
	if template:
		filters["name"] = template

	created, updated, failed = 0, 0, []
	for name in frappe.get_all("Tour Template", filters=filters, pluck="name"):
		tpl = frappe.get_doc("Tour Template", name)
		holidays = get_holidays(resolve_holiday_list(tpl.holiday_list, tpl.school), start, end)
		flags = {d: tpl.get(d) for d in L.WEEKDAYS}

		for day in L.daterange(start, end):
			if not L.template_runs_on(flags, tpl.valid_from, tpl.valid_to, holidays, day):
				continue
			try:
				existing = frappe.db.get_value("Tour", {"tour_template": name, "tour_date": day},
											   ["name", "status"], as_dict=True)
				if not existing:
					_create(tpl, day)
					created += 1
				elif existing.status == "Planned" and _sync(frappe.get_doc("Tour", existing.name), tpl, day):
					updated += 1
			except Exception:
				failed.append(f"{name} {day}")
				frappe.log_error(title=f"Tour generation failed: {name} {day}")

	return {"created": created, "updated": updated, "failed": failed}


def _create(tpl, day):
	doc = frappe.new_doc("Tour")
	doc.update({
		"tour_date": day, "tour_template": tpl.name, "school": tpl.school, "direction": tpl.direction,
		"start_time": tpl.start_time, "end_time": tpl.end_time,
		"driver": tpl.default_driver, "vehicle": tpl.default_vehicle, "status": "Planned",
	})
	for row in template_rows_for_date(tpl, day):
		doc.append("passengers", row)
	doc.flags.ignore_coverage_errors = True
	doc.insert(ignore_permissions=True)


def _sync(doc, tpl, day):
	"""Add passengers newly put on the template; drop template rows for passengers who left it.

	Rows added by hand (from_template = 0) and rows whose status was changed are left alone.
	"""
	wanted = {r["passenger"]: r for r in template_rows_for_date(tpl, day)}
	present = {r.passenger for r in doc.passengers}
	changed = False

	for row in list(doc.passengers):
		if row.from_template and row.status == "Planned" and row.passenger not in wanted:
			doc.remove(row)
			changed = True
	for pid, row in wanted.items():
		if pid not in present:
			doc.append("passengers", row)
			changed = True

	if changed:
		doc.flags.ignore_coverage_errors = True
		doc.save(ignore_permissions=True)
	return changed
