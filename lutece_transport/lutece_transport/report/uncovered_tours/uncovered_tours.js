frappe.query_reports["Uncovered Tours"] = {
	filters: [
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date", default: frappe.datetime.add_days(frappe.datetime.get_today(), 7), reqd: 1 },
		{ fieldname: "include_warnings", label: __("Include Warnings"), fieldtype: "Check" },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "level" && data) {
			const color = { error: "red", gap: "orange", warning: "gray" }[data.level] || "gray";
			value = `<span class="indicator-pill ${color}">${__(data.level)}</span>`;
		}
		return value;
	},
};
