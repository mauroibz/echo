# Design

## Reading ICS without a dependency

`icalendar` plus `recurring-ical-events` would add two packages and their pins to a lean,
hash-locked install. What the two feeds Studio targets write is small: VEVENTs in UTC, with an
IANA TZID or a Windows name with its VTIMEZONE (Outlook), whole days, RRULE with FREQ, INTERVAL,
COUNT, UNTIL, BYDAY (with ordinals), BYMONTHDAY, BYMONTH, EXDATE and RECURRENCE-ID. `ics.py`
reads that with the standard library (`zoneinfo` for zones). A Windows zone takes the
VTIMEZONE's standard offset: daylight saving there is not followed, which is right for the
user's zone (no DST) and an hour off for others half the year. Endless rules stop at 2000
occurrences.

## Secrets

A private ICS address is a read token: it is kept in the keyring next to the API key (entry
"calendar"), `$ECHO_CALENDAR_URLS` wins over it, and it is never written to `studio.toml`.

## The calendar without a model

The calendar is read once an address is set, whether or not a summaries server is: titles,
attendees and recording meetings need no model and send nothing anywhere.

## Matching

A recording is a meeting's when it started from 10 minutes before the event to its end; the
latest-starting event wins. Whole-day events never match. The event is saved in the recording's
folder, so later calendar changes do not rewrite what a recording was.

## Decisions made while implementing

- Outlook writes "Last, First" as an attendee's name; it is turned into "First Last".
- Emails are learned only when exactly one attendee has the speaker's name (full name, or first
  name for a one-word speaker name), the person has no email yet and nobody else has it.
- The invitation text given to the summary drops lines with links and phone numbers (the
  video call's boilerplate) and is cut at 1,500 characters.
