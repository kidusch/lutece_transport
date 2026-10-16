# Lutece Transport

Frappe app that brings the Lutece transport system into ERPNext/HRMS. Its main job is to make sure every tour has a driver and vehicle, and that no passenger is left without a run.

## How it works

- **Passenger**: the student or client, with their school, transport contract dates, wheelchair need and guardians.
  - **Required Trips** lists one row per trip the passenger needs (weekday + To School / From School).
  - A child who goes home at noon and back at 13:30 has two rows of each direction for that day.
  - This is what the coverage check compares against.
- **Tour Template**: a recurring run, for example "Morning Lancy – École X".
  - Holds the weekdays, times, default driver (Employee), default vehicle (Vehicle) and the ordered passenger list.
- **Tour**: one run on one day. Tours are created automatically every morning, 14 days ahead, from the active templates.
  - School holidays come from the school's Holiday List.
  - Passengers are only added on days their contract covers.
  - When a template's passenger list changes, planned tours follow.
  - Rows added by hand on a single tour are left alone.
  - "Apply Driver/Vehicle/Times to Future Tours" on the template pushes a new default driver or vehicle onto already-planned tours.

## Checks

- **Blocking when a tour is saved by hand**
  - Driver inactive, left, or on approved leave that day
  - Driver or vehicle on two overlapping tours
  - Passenger on two overlapping tours, or listed twice
  - More riding passengers than vehicle seats (Absent and Cancelled rows don't count)
  - Wheelchair passenger in a non-accessible vehicle
  - End time before start time
- **Flagged but not blocking:** no driver, or no vehicle.
- **Warnings**
  - Driver licence expired or medical check overdue
  - Vehicle inspection overdue or insurance ended
  - Passenger contract not covering the date
- **Generated tours are always saved, even with problems**, so a gap shows up in the reports instead of the tour quietly not existing.

## Where problems show up

- **Uncovered Tours** report: planned tours with errors or no driver/vehicle, for any date range (default: next 7 days).
- **Passengers Without Transport** report: passengers with fewer planned runs than their Required Trips, per day and direction.
  - It also lists passengers who have no Required Trips entered.
- **Tour list**: red "No Driver" and orange "Needs Attention" indicators. A calendar view can be filtered by driver, vehicle or school.
- **Daily email at 15:00** to users with the Transport Dispatcher role, covering the next 3 days.
  - By default it's sent even when everything is covered, so silence never means "the check didn't run".
- **Immediate email** when a driver's leave is approved, their status stops being Active, or a relieving date is set.
  - It lists the planned tours to reassign and flags each of them.

## Setup

- Tested on ERPNext + HRMS v15 and v16.
- `bench get-app <repo-url>` then `bench --site <site> install-app lutece_transport`
  - Requires ERPNext and HRMS.
  - Fixtures add the custom fields and the two roles.
- **Employee:** tick *Is Driver*, and fill *Licence Valid Until* and *Next Medical Check*.
- **Vehicle:** fill *Passenger Seats*, *Wheelchair Accessible* and *Next Technical Inspection*. The insurance end date uses the standard field.
- Give each school a Holiday List, or set a default in **Transport Settings**.
- **On v16:** HRMS also needs a submitted **Holiday List Assignment** (Applicable For: Company) before any leave can be approved. That leave is what tells the app a driver is unavailable.
- Give dispatchers the **Transport Dispatcher** role.
- For drivers:
  - Give them **Transport Driver**.
  - Add a User Permission on their own Employee so they only see their tours.
- Scheduled jobs:
  - Tour generation runs at 05:00; the coverage email runs at 15:00 (site time zone).
  - Make sure the scheduler is enabled: `bench --site <site> enable-scheduler`.

## Mapping from Lutece

- Client → Passenger (billing through a linked Customer)
- Parent/Guardian → Passenger Guardian rows
- School → Transport School
- Driver (User with ROLE_DRIVER) → Employee with Is Driver
- Vehicule → Vehicle with custom fields
- Schedule → Tour, with Tour Template for the recurring pattern
- Invoice → Sales Invoice
- Payslip → HRMS Salary Slip
- ROLE_ADMIN / ROLE_SECRETORY → Transport Dispatcher; ROLE_DRIVER → Transport Driver

## Tests

The assignment and coverage rules live in `lutece_transport/logic.py` with no Frappe dependency. Run `python -m pytest`.
