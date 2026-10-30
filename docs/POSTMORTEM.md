# Postmortems

When something goes wrong for our users, we write down what happened, while it is fresh, so the next person
(often one of us) has less to rediscover. A postmortem looks for what in the system let the problem happen and
what would catch it sooner. It doesn't look for someone to blame: the person who ran the command knows the most
about what happened, and we want them to keep telling us.

Copy the template, fill it in within a few days, and link it from the issue.

## Template

```
# <What users saw, in one line>  (YYYY-MM-DD)

What happened:     what users saw or didn't get, from when to when
How we found out:  a user, a check, a log line, luck
Timeline:          times in UTC, from the first sign to fully back
Why it happened:   the conditions that lined up (usually more than one)
What went well:    what limited the damage
What we'll change: each action with an owner and an issue number
```

## Example: documents were not counted after a rollback (from our continuous delivery demo)

We rolled back too far on purpose in that demo; this is the postmortem we would have written had it been real.

```
# Uploads worked, but documents were not counted  (2026-10-28)

What happened:     after a rollback to v0.4.0, documents checked on the demo copy were left out of the
                   counts on the page. Finding and removing personal information kept working.
How we found out:  scripts/smoke.sh after the rollback said "stats: the document was not counted".
                   deploy.sh had printed "deployed", and /ready answered "ready".
Timeline (UTC):    12:55:41 deploy.sh v0.6.0 (its migration drops the old usage table)
                   12:55:47 deploy.sh v0.4.0 (a rollback; v0.4.0 still writes the old table)
                   right after: the smoke test fails; the log shows "no such table: usage"
                   12:55:53 deploy.sh v0.6.0; the smoke test passes
Why it happened:   v0.4.0 writes a table that v0.6.0's migration removed; counting failures are only
                   logged, by design, so users keep their results; /ready checks the schema version
                   but not that this version can write to it.
What went well:    users never saw an error; the smoke test checks the count, not only the status code.
What we'll change: the CHANGELOG says how far back is safe after each migration (done in 0.6.0);
                   run the smoke test after every deploy and every rollback (owner: whoever deploys).
```
