import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, nowdate

from lutece_transport import logic as L
from lutece_transport.coverage import vehicle_info


class TourTemplate(Document):
	def validate(self):
		if L.to_minutes(self.end_time) <= L.to_minutes(self.start_time):
			frappe.throw(_("End time must be after start time."))
		if not any(self.get(d) for d in L.WEEKDAYS):
			frappe.throw(_("Tick at least one weekday."))
		if self.valid_from and self.valid_to and getdate(self.valid_to) < getdate(self.valid_from):
			frappe.throw(_("Valid To is before Valid From."))

		seen = set()
		for row in self.passengers:
			if row.passenger in seen:
				frappe.throw(_("Row {0}: {1} is already on this tour.").format(row.idx, row.passenger_name or row.passenger))
			seen.add(row.passenger)
			self.fill_addresses(row)

		self.warn_about_vehicle()

	def fill_addresses(self, row):
		"""Default the home address on the home side of the trip, the school address on the other."""
		home = frappe.db.get_value("Passenger", row.passenger, "home_address")
		school = self.school and frappe.db.get_value("Transport School", self.school, "address")
		if self.direction == "To School":
			row.pickup_address = row.pickup_address or home
			row.dropoff_address = row.dropoff_address or school
		else:
			row.pickup_address = row.pickup_address or school
			row.dropoff_address = row.dropoff_address or home

	def warn_about_vehicle(self):
		v = vehicle_info(self.default_vehicle)
		if not v:
			return
		if v.get("seats") and len(self.passengers) > v["seats"]:
			frappe.msgprint(
				_("{0} passengers but {1} has {2} seats. Days where everyone rides will be flagged.").format(
					len(self.passengers), v["name"], v["seats"]),
				indicator="orange",
			)
		if not v.get("wheelchair_accessible"):
			needs = [r.passenger_name or r.passenger for r in self.passengers
					 if frappe.db.get_value("Passenger", r.passenger, "wheelchair")]
			if needs:
				frappe.msgprint(
					_("{0} need a wheelchair-accessible vehicle; {1} is not.").format(", ".join(needs), v["name"]),
					indicator="red",
				)


def _require_dispatcher():
	frappe.only_for(["Transport Dispatcher", "System Manager"])


@frappe.whitelist()
def generate_now(tour_template):
	_require_dispatcher()
	from lutece_transport.generation import generate_tours

	return generate_tours(template=tour_template)


@frappe.whitelist()
def apply_defaults_to_future(tour_template, from_date=None, driver=1, vehicle=1, times=1):
	"""Copy the template's driver, vehicle and times onto its planned tours from a date on."""
	_require_dispatcher()
	tpl = frappe.get_doc("Tour Template", tour_template)
	from_date = getdate(from_date or nowdate())
	updated, failed = [], []
	for name in frappe.get_all("Tour", filters={"tour_template": tour_template, "status": "Planned",
												 "tour_date": [">=", from_date]}, pluck="name"):
		doc = frappe.get_doc("Tour", name)
		if int(driver):
			doc.driver = tpl.default_driver
		if int(vehicle):
			doc.vehicle = tpl.default_vehicle
		if int(times):
			doc.start_time, doc.end_time = tpl.start_time, tpl.end_time
		doc.flags.ignore_coverage_errors = True
		try:
			doc.save()
			updated.append(name)
		except Exception:
			failed.append(name)
			frappe.log_error(title=f"Could not update {name} from {tour_template}")
	return {"updated": len(updated), "failed": failed}
