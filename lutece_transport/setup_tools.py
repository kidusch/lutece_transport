"""One-off setup helpers, run from the server shell with `bench execute`.

Example (school holidays, zone C, with French public holidays):

    bench --site default execute lutece_transport.setup_tools.make_holiday_list --kwargs "{
        'name': 'Vacances scolaires Zone C 2026-2027',
        'from_date': '2026-09-01', 'to_date': '2027-08-31',
        'ranges': [['2026-10-17', '2026-11-01', 'Vacances de la Toussaint']],
        'country': 'FR'}"
"""

from datetime import date

import frappe
from frappe.utils import getdate

from lutece_transport import logic as L

WEEKDAY_NAMES = {name.lower(): i for i, name in enumerate(L.WEEKDAY_LABELS)}


def repair_scheduler(apply=0):
	"""Diagnose (and with apply=1, fix) scheduled jobs that never run because their
	creation / last_execution timestamps are in the future (clock or time zone changed
	after install). Prints what it finds."""
	from frappe.utils import add_to_date, now_datetime

	now = now_datetime()
	tz = frappe.db.get_single_value("System Settings", "time_zone")
	db_now = frappe.db.sql("select now()")[0][0]
	jobs = frappe.get_all("Scheduled Job Type", filters={"stopped": 0},
						  fields=["name", "creation", "last_execution", "frequency", "cron_format"])
	future = [j for j in jobs if (j.last_execution or j.creation) > now]
	never = [j for j in jobs if not j.last_execution]
	print(f"System time zone: {tz} | Frappe now: {now} | database now: {db_now}")
	print(f"Active job types: {len(jobs)} | never run: {len(never)} | timestamp in the future: {len(future)}")
	for j in future[:5]:
		print(f"  e.g. {j.name}: creation {j.creation}, last run {j.last_execution}")
	if future:
		print(f"  latest future timestamp: {max((j.last_execution or j.creation) for j in future)}")

	if int(apply):
		reset_to = add_to_date(now, minutes=-10)
		for j in future + [j for j in never if j not in future]:
			frappe.db.set_value("Scheduled Job Type", j.name, "last_execution", reset_to, update_modified=False)
		frappe.db.commit()
		print(f"Reset {len(set(j.name for j in future + never))} job(s) to last run {reset_to}. "
			  "Frequent jobs will start within a few minutes; daily ones at their normal time.")
	elif future or never:
		print("Run again with --kwargs \"{'apply': 1}\" to fix.")


def make_holiday_list(name, from_date, to_date, ranges=None, country=None, weekly_off=None, replace=0):
	"""Create (or add to) a Holiday List.

	ranges:     [[start, end, description], ...] — every day in each range becomes a holiday
	country:    ISO code (e.g. "FR") to add that country's public holidays in the period
	weekly_off: e.g. ["Saturday", "Sunday"]
	replace:    1 to clear the existing holidays first
	"""
	from_date, to_date = getdate(from_date), getdate(to_date)
	if frappe.db.exists("Holiday List", name):
		doc = frappe.get_doc("Holiday List", name)
		doc.from_date, doc.to_date = from_date, to_date
		if int(replace):
			doc.holidays = []
	else:
		doc = frappe.new_doc("Holiday List")
		doc.holiday_list_name = name
		doc.from_date, doc.to_date = from_date, to_date

	wanted: dict[date, str] = {}

	def put(d, description):
		d = getdate(d)
		if from_date <= d <= to_date and d not in wanted:
			wanted[d] = description

	if country:
		import holidays

		for d, description in sorted(
			holidays.country_holidays(country, years=range(from_date.year, to_date.year + 1), language="fr").items()
		):
			put(d, description)

	for start, end, description in ranges or []:
		for d in L.daterange(start, end):
			put(d, description)

	off = {WEEKDAY_NAMES[w.lower()] for w in (weekly_off or [])}
	if off:
		for d in L.daterange(from_date, to_date):
			if d.weekday() in off:
				put(d, L.WEEKDAY_LABELS[d.weekday()])

	existing = {getdate(h.holiday_date) for h in doc.holidays}
	added = 0
	for d in sorted(wanted):
		if d not in existing:
			doc.append("holidays", {"holiday_date": d, "description": wanted[d],
									"weekly_off": 1 if d.weekday() in off and wanted[d] == L.WEEKDAY_LABELS[d.weekday()] else 0})
			added += 1

	doc.save(ignore_permissions=True)
	frappe.db.commit()
	print(f"{doc.name}: {added} day(s) added, {len(doc.holidays)} in total "
		  f"({from_date} – {to_date})")
	return doc.name
