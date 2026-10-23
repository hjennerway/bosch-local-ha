"""Plain-language explanations for automatic scheduling conditions."""


def source_explanation(key, check):
    label = "Door" if key == "door" else "Dishwasher"
    availability = check["availability"]
    if availability == "missing":
        return f"{label} sensor not found"
    if availability == "unavailable":
        return f"{label} sensor is unavailable"
    if availability == "unknown":
        return f"{label} state is unknown"
    current = check["current"]
    if key == "door":
        if check["matches"]:
            return "Door closed"
        if current == "Open":
            return "Close the dishwasher door"
        return f"Door reports {str(current)[:60]}; expected Closed"
    if check["matches"]:
        return f"Dishwasher idle ({current})"
    if current == "Run":
        return "Wash in progress"
    if current == "DelayedStart":
        return "Dishwasher already has a delayed start"
    if current == "Pause":
        return "Wash is paused"
    return f"Dishwasher reports {str(current)[:60]}; expected Ready, Inactive or Finished"


def explain_automation(checks):
    """Summarize normal waiting separately from conditions needing attention."""
    reasons = []
    if not checks["automatic_enabled"]["matches"]:
        reasons.append("Automatic NightWash is off; turn it on to schedule automatically")
    if not checks["schedule_armed"]["matches"]:
        reasons.append("A wash is already scheduled; no second schedule is needed")
    if not checks["start_pending"]["matches"]:
        reasons.append("Start requested; waiting for the dishwasher to report a running wash")
    for key in ("door", "operation"):
        if not checks[key]["matches"]:
            reasons.append(source_explanation(key, checks[key]))
    history = checks["last_completed_wash"]
    if not history["matches"]:
        reasons.append("No completed wash date recorded; waiting for a wash to finish or a valid imported date"
                       if history["current"] is None else
                       "Waiting until 48 hours after the last completed wash")
    if not checks["nightwash_configured"]["matches"]:
        reasons.append("NightWash is missing from the configured programs")
    if not checks["start_pending"]["matches"]:
        summary = "Waiting for dishwasher to start"
    elif not checks["schedule_armed"]["matches"]:
        summary = "A wash is already scheduled"
    elif not checks["automatic_enabled"]["matches"]:
        summary = "Automatic NightWash is off"
    else:
        summary = reasons[0] if reasons else "Ready to schedule the next 01:00 wash"
    return summary, reasons
