# Briefings

`BriefingService` creates concise morning, work-start, project, system,
deadline, end-of-day, and weekly views from durable goals, missions, approved
workspace metadata, findings, and pending approvals. Each line carries an
evidence identifier. No useful facts means no briefing, and duplicate content
within the cooldown is suppressed.

Briefings are read-only projections of existing services. Delivery and
dismissal are explicit records; generation does not send communications or
change goals.
