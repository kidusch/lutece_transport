frappe.ui.form.on("Tour", {
	refresh(frm) {
		if (frm.doc.has_issues && frm.doc.coverage_issues) {
			frm.dashboard.set_headline_alert(
				`<div class="text-danger">${frappe.utils.escape_html(frm.doc.coverage_issues).replace(/\n/g, "<br>")}</div>`
			);
		}
		if (frm.doc.tour_template && frm.doc.status === "Planned") {
			frm.add_custom_button(__("Reload Passengers from Template"), () => load_passengers(frm, true));
		}
	},
	tour_template(frm) {
		if (frm.doc.tour_template && !(frm.doc.passengers || []).length) load_passengers(frm, false);
	},
	tour_date(frm) {
		if (frm.doc.tour_template && !(frm.doc.passengers || []).length) load_passengers(frm, false);
	},
});

function load_passengers(frm, replace) {
	if (!frm.doc.tour_date) {
		frappe.msgprint(__("Set the date first."));
		return;
	}
	frappe.call({
		method: "lutece_transport.lutece_transport.doctype.tour.tour.get_template_passengers",
		args: { tour_template: frm.doc.tour_template, tour_date: frm.doc.tour_date },
		callback(r) {
			if (replace) frm.clear_table("passengers");
			const present = new Set((frm.doc.passengers || []).map((p) => p.passenger));
			(r.message || []).forEach((row) => {
				if (!present.has(row.passenger)) frm.add_child("passengers", row);
			});
			frm.refresh_field("passengers");
		},
	});
}
