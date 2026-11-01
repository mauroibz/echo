## MODIFIED Requirements

### Requirement: A person's part in each meeting
After a recording with named speakers is summarized, Studio SHALL save, in `parts.json` and from
one request for all of them, for each named person:
- a line on what they contributed;
- up to five points on what they reported, proposed, asked, objected to or took on.

A file from the first version (a line per person) SHALL still be read. A failure SHALL leave the
summary and the action items saved.

#### Scenario: Three people in a sync
- **WHEN** a meeting where Sofía, Diego and Carla are named is summarized
- **THEN** one request returns a part for each, and Sofía's points include that she took on the test plan

### Requirement: A person's page
Studio's People SHALL list everyone Echo knows, filtered by name or email. A person's page SHALL
show:
- their email, editable, one person per email;
- their meetings, newest first, each with its minutes card, their part and its points, a star
  and the recording's tags, filtered by All, Starred or one tag;
- the action items assigned to them, to polish, without any done state;
- their notes.

Opening a speaker's profile SHALL open this page while Studio's rail is shown. A meeting's star
SHALL be kept in `marks.json` in its folder.

#### Scenario: Before talking to Sofía
- **WHEN** the user opens Sofía's page and picks Starred
- **THEN** it shows the meetings with her the user starred, what she did in each, and the items assigned to her
