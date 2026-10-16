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
