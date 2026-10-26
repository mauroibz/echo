## ADDED Requirements

### Requirement: Tag categories in the window
The tag bar SHALL show one chip per category, whose menu lists the category's values with their
counts and an entry for any value, beside the plain tags. Choosing an entry SHALL add the tag to
the search box, which stays the one place the filter lives. The tag editor SHALL show a
categorized tag with its category set apart, and typing `category:` SHALL complete that
category's values.

#### Scenario: Filter by a client from the bar
- **WHEN** recordings are tagged `client:Acme` and `client:Globex` and the user opens the "client" chip and picks Globex
- **THEN** the search box holds `#client:Globex` and only Globex's recordings are listed
