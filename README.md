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

## Driver page (/mes-tournees)

- Phone-friendly page for users with the **Transport Driver** role; it is their home page after login.
- Shows the driver's own tours for a day (today, tomorrow or a chosen date) and the tours of the next 7 days still to accept.
- Three actions, nothing else, each only on the driver's own tours:
    - **Accept** a tour. There is no refusal: drivers call the planner.
    - **Picked up / Absent** for each passenger (today only). An absence emails the planners and adds a comment on the tour.
    - **End the tour**, only once every passenger has a status. The tour becomes *Completed*.
- From the day before, a tour its driver has not accepted is reported as not covered (reports and 15:00 email).
- Changing a tour's driver or date resets the acceptance.
- Setup per driver: user with the Transport Driver role, linked in the Employee's *User* field.

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

## Language

- French translation in `lutece_transport/translations/fr.csv`; each user sees French when their language is set to Français.
- Check messages are built as translatable templates in `logic.py` and translated in `coverage.issue_text`.

## Tests

The assignment and coverage rules live in `lutece_transport/logic.py` with no Frappe dependency. Run `python -m pytest`.
