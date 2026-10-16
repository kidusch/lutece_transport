import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_datetime, getdate

from lutece_transport import logic as L
from lutece_transport.coverage import check_tour, format_issues


class Tour(Document):
	def validate(self):
		self.fill_from_template()
		self.validate_one_tour_per_template_and_day()
		self.set_title_and_datetimes()
		self.run_checks()

	def fill_from_template(self):
		if not self.tour_template:
			return
		tpl = frappe.db.get_value(
			"Tour Template", self.tour_template, ["school", "direction", "start_time", "end_time"], as_dict=True
		)
		if not tpl:
			return
		for field in ("school", "direction", "start_time", "end_time"):
			if not self.get(field):
				self.set(field, tpl.get(field))

	def validate_one_tour_per_template_and_day(self):
		if not self.tour_template:
			return
		other = frappe.db.get_value(
			"Tour",
			{"tour_template": self.tour_template, "tour_date": self.tour_date, "name": ["!=", self.name]},
			"name",
		)
		if other:
			frappe.throw(
				_("Tour {0} already exists for {1} on {2}.").format(other, self.tour_template, self.tour_date)
			)

	def set_title_and_datetimes(self):
		label = self.tour_template or self.direction
		self.title = f"{L.fmt_time(self.start_time)} {label}" + (f" – {self.driver_name}" if self.driver_name else "")
		d = getdate(self.tour_date)
		self.start_datetime = get_datetime(f"{d} {L.fmt_time(self.start_time)}")
		self.end_datetime = get_datetime(f"{d} {L.fmt_time(self.end_time)}")

	def run_checks(self):
		issues = check_tour(self)
		self.has_issues = 1 if any(i.flags_tour for i in issues) else 0
		self.coverage_issues = format_issues(issues)

		errors = [i for i in issues if i.level == L.ERROR]
		# The generator saves tours even when they have problems, so they show up in the
		# coverage reports instead of silently not being created.
		if errors and not self.flags.ignore_coverage_errors:
			frappe.throw(
				"<br>".join(i.message for i in errors), title=_("This tour can't be saved as is")
			)
		if not self.flags.ignore_coverage_errors:
			notes = [i for i in issues if i.level != L.ERROR]
			if notes:
				frappe.msgprint("<br>".join(i.message for i in notes), indicator="orange", alert=True)


@frappe.whitelist()
def get_template_passengers(tour_template, tour_date):
	"""Passengers of a template whose transport contract covers the date (used by the Tour form)."""
	frappe.has_permission("Tour Template", "read", tour_template, throw=True)
	from lutece_transport.generation import template_rows_for_date

	tpl = frappe.get_doc("Tour Template", tour_template)
	return template_rows_for_date(tpl, getdate(tour_date))
