frappe.views.calendar["Tour"] = {
	field_map: {
		start: "start_datetime",
		end: "end_datetime",
		id: "name",
		title: "title",
	},
	filters: [
		{ fieldtype: "Link", fieldname: "driver", options: "Employee", label: __("Driver") },
		{ fieldtype: "Link", fieldname: "vehicle", options: "Vehicle", label: __("Vehicle") },
		{ fieldtype: "Link", fieldname: "school", options: "Transport School", label: __("School") },
	],
	get_events_method: "frappe.desk.calendar.get_events",
};
