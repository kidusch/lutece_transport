app_name = "lutece_transport"
app_title = "Lutece Transport"
app_publisher = "Kidus Dejen Yirgu"
app_description = "School and special transport planning for ERPNext: tours, driver assignment and coverage checks"
app_email = "kidus.dejen@gmail.com"
app_license = "mit"

required_apps = ["erpnext", "hrms"]

fixtures = [
	{"dt": "Custom Field", "filters": [["module", "=", "Lutece Transport"]]},
	{"dt": "Role", "filters": [["name", "in", ["Transport Dispatcher", "Transport Driver"]]]},
]

doc_events = {
	"Leave Application": {
		"on_submit": "lutece_transport.notifications.on_leave_approved",
		"on_update_after_submit": "lutece_transport.notifications.on_leave_approved",
	},
	"Employee": {
		"on_update": "lutece_transport.notifications.on_employee_update",
	},
}

scheduler_events = {
	# Generate tours early so the afternoon check already sees tomorrow's tours.
	"cron": {
		"0 5 * * *": ["lutece_transport.generation.scheduled_generate"],
		"0 15 * * *": ["lutece_transport.notifications.send_daily_digest"],
	},
}
