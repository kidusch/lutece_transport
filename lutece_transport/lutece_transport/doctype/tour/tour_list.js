frappe.listview_settings["Tour"] = {
	add_fields: ["status", "has_issues", "driver"],
	get_indicator(doc) {
		if (doc.status === "Cancelled") return [__("Cancelled"), "gray", "status,=,Cancelled"];
		if (doc.status === "Completed") return [__("Completed"), "green", "status,=,Completed"];
		if (!doc.driver) return [__("No Driver"), "red", "driver,is,not set"];
		if (doc.has_issues) return [__("Needs Attention"), "orange", "has_issues,=,1"];
		return [__("Planned"), "blue", "status,=,Planned"];
	},
};
