from frappe import _

from lutece_transport.coverage import passengers_without_transport


def execute(filters=None):
	filters = filters or {}
	data = passengers_without_transport(filters.get("from_date"), filters.get("to_date"))
	for row in data:
		if row.get("direction"):
			row["direction"] = _(row["direction"])
	columns = [
		{"fieldname": "date", "label": _("Date"), "fieldtype": "Date", "width": 100},
		{"fieldname": "direction", "label": _("Direction"), "fieldtype": "Data", "width": 110},
		{"fieldname": "passenger", "label": _("Passenger"), "fieldtype": "Link", "options": "Passenger", "width": 110},
		{"fieldname": "passenger_name", "label": _("Passenger Name"), "fieldtype": "Data", "width": 180},
		{"fieldname": "school", "label": _("School"), "fieldtype": "Link", "options": "Transport School", "width": 180},
		{"fieldname": "expected", "label": _("Required"), "fieldtype": "Int", "width": 85},
		{"fieldname": "planned", "label": _("Planned"), "fieldtype": "Int", "width": 80},
		{"fieldname": "note", "label": _("Problem"), "fieldtype": "Data", "width": 260},
	]
	summary = [{
		"value": len({r["passenger"] for r in data}),
		"indicator": "Red" if data else "Green",
		"label": _("Passengers affected"), "datatype": "Int",
	}]
	return columns, data, None, None, summary
