frappe.ui.form.on("Tour Template", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Generate Tours Now"), () => {
			frappe.call({
				method: "lutece_transport.lutece_transport.doctype.tour_template.tour_template.generate_now",
				args: { tour_template: frm.doc.name },
				freeze: true,
				callback(r) {
					const m = r.message || {};
					frappe.msgprint(
						__("{0} tour(s) created, {1} updated.", [m.created || 0, m.updated || 0]) +
							((m.failed || []).length ? "<br>" + __("Failed: {0}", [m.failed.join(", ")]) : "")
					);
				},
			});
		}, __("Tours"));

		frm.add_custom_button(__("Apply Driver/Vehicle/Times to Future Tours"), () => {
			frappe.prompt(
				[
					{ fieldname: "from_date", fieldtype: "Date", label: __("From"), default: frappe.datetime.get_today(), reqd: 1 },
					{ fieldname: "driver", fieldtype: "Check", label: __("Driver"), default: 1 },
					{ fieldname: "vehicle", fieldtype: "Check", label: __("Vehicle"), default: 1 },
					{ fieldname: "times", fieldtype: "Check", label: __("Start/End Times"), default: 1 },
				],
				(v) => {
					frappe.call({
						method: "lutece_transport.lutece_transport.doctype.tour_template.tour_template.apply_defaults_to_future",
						args: { tour_template: frm.doc.name, ...v },
						freeze: true,
						callback(r) {
							const m = r.message || {};
							frappe.msgprint(__("{0} planned tour(s) updated.", [m.updated || 0]));
						},
					});
				},
				__("Update planned tours")
			);
		}, __("Tours"));

		frm.add_custom_button(__("View Tours"), () => {
			frappe.set_route("List", "Tour", { tour_template: frm.doc.name });
		});
	},
});
