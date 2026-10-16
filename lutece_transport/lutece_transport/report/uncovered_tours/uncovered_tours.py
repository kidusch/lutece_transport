from frappe import _

from lutece_transport.coverage import uncovered_tours


def execute(filters=None):
	filters = filters or {}
	data = uncovered_tours(filters.get("from_date"), filters.get("to_date"),
						   include_warnings=bool(filters.get("include_warnings")))
	columns = [
		{"fieldname": "tour_date", "label": _("Date"), "fieldtype": "Date", "width": 100},
		{"fieldname": "start_time", "label": _("Start"), "fieldtype": "Data", "width": 70},
		{"fieldname": "tour", "label": _("Tour"), "fieldtype": "Link", "options": "Tour", "width": 140},
		{"fieldname": "tour_template", "label": _("Tour Template"), "fieldtype": "Link", "options": "Tour Template", "width": 200},
		{"fieldname": "direction", "label": _("Direction"), "fieldtype": "Data", "width": 100},
		{"fieldname": "driver_name", "label": _("Driver"), "fieldtype": "Data", "width": 140},
		{"fieldname": "vehicle", "label": _("Vehicle"), "fieldtype": "Link", "options": "Vehicle", "width": 110},
		{"fieldname": "passengers", "label": _("Passengers"), "fieldtype": "Int", "width": 90},
		{"fieldname": "level", "label": _("Level"), "fieldtype": "Data", "width": 80},
		{"fieldname": "issue", "label": _("Issue"), "fieldtype": "Data", "width": 380},
	]
	summary = [{
		"value": len({r["tour"] for r in data if r["level"] in ("error", "gap")}),
		"indicator": "Red" if data else "Green",
		"label": _("Tours needing attention"), "datatype": "Int",
	}]
	return columns, data, None, None, summary
