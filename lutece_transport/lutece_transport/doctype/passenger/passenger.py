import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate


class Passenger(Document):
	def validate(self):
		self.full_name = " ".join(x for x in (self.first_name, self.last_name) if x).strip()
		if self.contract_end and getdate(self.contract_end) < getdate(self.contract_start):
			frappe.throw(_("Transport End is before Transport Start."))
		if not self.schedule:
			frappe.msgprint(
				_("No Required Trips entered. Without them the system can't tell when {0} is missing from a tour.").format(
					self.full_name),
				indicator="orange", alert=True,
			)
