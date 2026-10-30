## ADDED Requirements

### Requirement: Follow-up draft
For a summarized recording, the Summary view SHALL offer "Follow-up", which drafts an email
(subject and body) from the summary and the open action items and shows it to edit, with Copy
and Open in mail. Studio SHALL not send email. `echo-app summarize ID --follow-up` SHALL print
the draft.

#### Scenario: After a client meeting
- **WHEN** the user presses Follow-up on a summarized meeting and then Open in mail
- **THEN** the mail program opens a new message with the subject and the body, and no recipient
