# Bosch Local for Home Assistant

Local dishwasher scheduling and completed-wash history using the existing HCPY
MQTT bridge. Includes a standalone dashboard card with **Clear schedule**.

## Docker / Dockge

`compose.yaml` mirrors the `bosch-local` stack read from Dockge at
`192.168.4.136:5001` on 23 October 2026. It preserves the image, exact upstream
commit, inline build, MQTT settings, restart policy and read-only configuration
mount. The MQTT password is moved to an environment variable.

1. Copy `.env.example` to `.env` and enter the existing MQTT password.
2. Copy the existing Dockge stack's `config` directory beside `compose.yaml`.
   It must contain the original `devices.json`, including the appliance keys.
   `.env` and `config/` are excluded from Git.
3. Use Docker Compose 2.17 or newer. Run `docker compose config --quiet` to
   validate, then `docker compose up -d --build` to deploy when ready.

Do not run a second copy alongside the existing stack: it would use the same
MQTT client ID and appliance connection. No running containers were changed.

## Install the Home Assistant integration

Requires Home Assistant **2026.10.0 or newer**.

### HACS (recommended)

1. In **HACS → menu → Custom repositories**, add
   `https://github.com/hjennerway/bosch-local-ha` with type **Integration**.
2. Find **Bosch Local** in HACS and download it, then restart Home Assistant.
3. Continue with configuration below.

This is a HACS custom repository; it is not listed in the default HACS catalog.
The repository must be public and these files must be pushed to GitHub before
HACS can download them. Releases are optional for custom-repository installation;
without releases HACS uses the default branch. For versioned updates, publish a
GitHub release whose tag matches `manifest.json` (currently `v0.2.1`).
See [HACS integration requirements](https://www.hacs.dev/docs/publish/integration/).

### Manual installation

Copy `custom_components/bosch_local` into Home Assistant's
`/config/custom_components/bosch_local` directory and restart Home Assistant.

### Configuration

1. Ensure the standard MQTT integration is connected to your existing broker.
2. Open **Settings → Devices & services → Add integration → Bosch Local**.
3. Your current setup is pre-filled:

   | Setting | Value |
   | --- | --- |
   | Appliance MQTT base topic | `bosch_local/dishwasher` |
   | Programs | `{"NightWash": 8202}` |
   | Operation state | `sensor.bosch_schedule_operation` |
   | Door | `sensor.bosch_schedule_door` |
   | Existing last-run helper | `input_datetime.dishwasher_last_run_reference` |

Add other program names and **device-specific positive integer IDs** to the
programs JSON if needed. Only configured programs can be selected; `0` and
arbitrary program states are rejected. Existing HCPY sensors are reused.

The **Bosch Local Dishwasher** device contains Scheduled program, Scheduled
start, Schedule armed, Automatic NightWash, Clear schedule, Last completed wash,
and Schedule status (with an `error` attribute).

### Automation diagnostics

Open **Settings → Devices & services → Bosch Local → Bosch Local Dishwasher**.
The device's diagnostic sensors explain the inputs used by automatic scheduling:

| Diagnostic sensor | Expected state | Information in its attributes |
| --- | --- | --- |
| Door check | `Closed` | Source entity ID, current state, expected states, match and availability |
| Operation check | `Ready`, `Inactive` or `Finished` | Source entity ID, current state, expected states, match and availability |
| Automation readiness | All prerequisites pass | Every check's current/expected value, blocking reasons, last completion age and 48-hour eligibility time |

Click a sensor and expand its attributes (or inspect it in Developer Tools →
States). For example, Door check shows `Blocked` with `current: Open` and
`expected: [Closed]`. Missing entities, `unknown` and `unavailable` states are
reported explicitly. Automation readiness also checks whether automatic mode is
on, no schedule is already armed, no start is pending, and NightWash is configured.
`Blocked` can therefore be normal when a schedule is already armed; it means a
**new automatic schedule** cannot be created, not that the existing one failed.

Diagnostics refresh on door/operation changes, local schedule changes, startup
and each half-hour check. Completion age uses the stored/imported completion,
not the current value of the old helper. These checks describe the scheduling
rules; they do not test MQTT connectivity or the appliance's remote-start setting.

## Behaviour and migration

The existing `Dishwasher Auto On` checks every half-hour and on operation changes.
It requires a closed door, operation state `Ready`, `Inactive` or `Finished`, no
armed schedule, and 48 hours since the last completion. It sends NightWash `8202`
with delay option `558` to start at the next local 01:00. `Dishwasher Record Wash`
records `Finished` and disarms the schedule.

This integration preserves those rules, checks on both door and operation
changes, and records completion on a transition to `Finished`. It imports the
old last-run helper once when its own history is empty; it does not update the
legacy helper. Restoring an unavailable-to-Finished state is not a new wash.

**Before enabling Automatic NightWash**, disable `Dishwasher Auto On` and
`Dishwasher Record Wash` to avoid two schedulers. Allow any existing appliance
`DelayedStart` to finish, or cancel it using the appliance's normal controls.
The integration does not import or cancel existing appliance-side delayed
starts. Automatic NightWash starts **off**; enable it after checking the imported
completion timestamp.

Schedules are stored in Home Assistant, **not sent to HCPY in advance**. At the
scheduled time, the integration rechecks the door and idle state and publishes
only `[{"program":8202}]` to `bosch_local/dishwasher/activeProgram`, retain off.
HA, MQTT, HCPY and appliance remote start must be available then. A published
request is not proof the appliance started; `Run` confirms it. Start requests
are not automatically retried; pending requests block automatic rescheduling.
Check the appliance before manually re-arming an unconfirmed request.

**Clear schedule** cancels the local timer, removes the time, disarms it, and
turns Automatic NightWash off so the next check cannot recreate it. It publishes
nothing: no program `0`, delay-option reset or abort command. It does not stop
a wash or withdraw an already-sent start request. Turning Schedule armed off
also pauses automatic scheduling but keeps the time. Turn Automatic NightWash
back on to resume the 48-hour rule.

Future armed schedules survive HA restarts. Expired schedules are disarmed with
an error instead of running on startup. A missed start, open door or unavailable
operation requires manual attention. The first 01:00 is used once on the autumn
clock-change day.

The old automation's Telegram messages are not sent. Status and errors are
entities for your preferred notifications. Live automations, helpers and
dashboards were not modified during development.

## Dashboard card

1. Set up Bosch Local as above. HACS installs the bundled card with the
   integration, so it needs no separate frontend repository or file copy.
2. Add dashboard resource `/bosch_local/bosch-local-card.js?v=0.2.0` with type
   **JavaScript module**, then reload your browser. If upgrading from the earlier
   manually copied card, replace its `/local/bosch-local-card.js` resource instead
   of loading both. Update the query version after future card upgrades.
3. Add a manual card using [examples/dashboard.yaml](examples/dashboard.yaml).
   Match entity IDs to the integration's device; HA may append name suffixes.

The card provides program selection, schedule toggle, start time (opens HA's
date/time editor), automatic scheduling, completion date, errors and Clear
schedule. It uses HA's timezone and needs no Mushroom or Bubble dependency.

## Validation

```text
python -m unittest discover -s tests
node --test tests/card.test.cjs
node --check custom_components/bosch_local/frontend/bosch-local-card.js
python -m compileall -q custom_components
docker compose --env-file .env.example config --no-interpolate --quiet
```

Python scheduler tests use HA API doubles; they do not replace loading this in
your HA runtime. No physical wash was started for testing.

The GitHub validation workflow runs HACS's official integration validator and
the local tests on pushes and pull requests. The HACS check requires the files
to exist on GitHub; it has not been run against an unpublished working tree.

Protocol reference: [pinned HCPY source](https://github.com/hcpy2-0/hcpy/tree/590f1e71a75c91b36ea77eab7b5698c42ace4451).
