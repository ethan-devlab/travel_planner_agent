"""Risk and action aggregation for route review evidence."""


def risk(code, message):
    return {"code": code, "message": message}


def dedupe_risks(risks):
    unique = []
    seen = set()
    for route_risk in risks:
        key = (route_risk["code"], route_risk["message"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(route_risk)
    return unique


def route_actions(risks):
    codes = {route_risk["code"] for route_risk in risks}
    actions = []
    if codes & {"route_interval_insufficient", "route_interval_tight", "route_chronological_conflict"}:
        actions.append("Adjust saved stop start times to leave enough time between adjacent stops.")
    if codes & {"route_service_unavailable", "route_coordinate_far_from_road"}:
        actions.append("Confirm stop coordinates and retry the driving route check.")
    if "route_detour" in codes:
        actions.append("Compare the current route order with the suggested same-day order.")
    if codes & {"transport_verification_required", "short_plane_leg", "long_walking_leg"}:
        actions.append("Confirm unverified transport legs with an appropriate timetable or operator.")
    return actions
