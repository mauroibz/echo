## ADDED Requirements

### Requirement: Collections
The window SHALL let the user file recordings in collections, one per recording at most. While
any collection exists, a bar above the list SHALL show Recordings (those in no collection) and
each collection with how many recordings it holds, as done/total while some are not transcribed;
without one the bar SHALL be hidden. The list SHALL show the recordings of the row chosen, a
search SHALL look in all of them, the recording being made SHALL always show, and selecting a
recording filed elsewhere SHALL open the place it is in. Files coming in SHALL go into the open
collection; otherwise two or more SHALL ask for a collection (a new name, an existing one, or the
day-to-day list) and one SHALL be imported unasked. The user SHALL be able to move the selected
recordings to a collection, to a new one or back from the list's menu, by dragging them onto a
row, and to drop files on a row; and to bundle, rename (onto an existing name: join) and empty a
collection from its own menu. Emptying SHALL delete nothing.

#### Scenario: A round of interviews
- **WHEN** the user drops a folder "Entrevistas" with 12 files and accepts the name offered
- **THEN** the 12 recordings are in the collection Entrevistas, which opens with them, its row reads 0/12 and counts up as they are transcribed, and Recordings lists what it listed before

#### Scenario: Found from a search
- **WHEN** the user, on Recordings, searches for a sentence said in a filed interview and opens the result
- **THEN** the interview shows, and with the search cleared the list is its collection

#### Scenario: No collections
- **WHEN** no recording is in a collection
- **THEN** the window has no bar and one dropped file is imported as before
