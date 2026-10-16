import frappe
from frappe import _

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/mes-tournees"
		raise frappe.Redirect
	context.no_cache = 1
	context.show_sidebar = False
	context.title = _("My Tours")
	labels = {
		"today": _("Today"), "tomorrow": _("Tomorrow"), "to_accept": _("Tours to accept"),
		"accept": _("Accept"), "accepted": _("Accepted"), "picked": _("Picked Up"), "absent": _("Absent (not picked up)"),
		"undo": _("Undo"), "complete": _("End the tour"), "completed": _("Tour completed"),
		"none": _("No tour on this day."), "vehicle": _("Vehicle"), "pickup": _("Pickup"), "dropoff": _("Drop-off"),
		"confirm_complete": _("End this tour? Every passenger has a status."),
		"confirm_absent": _("Mark {0} as absent? The planner will be notified."),
		"accept_first": _("Accept this tour before starting it."), "error": _("Something went wrong. Try again."),
		"pending": _("To accept"),
	}
	context.lt_config = frappe.as_json({"labels": labels, "csrf": frappe.sessions.get_csrf_token()}, indent=None)
	return context
