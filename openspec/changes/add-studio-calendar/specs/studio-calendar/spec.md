## ADDED Requirements

### Requirement: Reading the calendar
Studio SHALL read the calendars at the private ICS addresses set in Settings → Calendar, kept in
the keyring, every 10 minutes, and SHALL keep the last copy so it works offline. It SHALL expand
recurring events, leave out cancelled ones, and never write to a calendar.

#### Scenario: A weekly meeting moved once
- **WHEN** a weekly meeting is cancelled one Wednesday and moved to 15:00 one Monday
- **THEN** Studio's next meetings leave that Wednesday out and show the Monday at 15:00

### Requirement: A recording's event
A recording started from 10 minutes before an event to its end SHALL get the event saved in its
folder. An unnamed recording SHALL take the event's title; the summary SHALL be told the event's
title, who was invited and the invitation's text; a person named in the recording SHALL get the
email of the one attendee with their name when they have none.

#### Scenario: Recording a call
- **WHEN** the user records at 11:03 during "Product sync" with Carla Méndez invited, and names speaker 1 "Carla"
- **THEN** the recording is titled "Product sync", its minutes know Carla was invited, and Carla's profile has her email
