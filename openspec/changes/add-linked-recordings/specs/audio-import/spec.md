## ADDED Requirements

### Requirement: Bursts of voice notes
Echo SHALL recognize WhatsApp voice notes that form one burst: with desktop-export names, each
starting within 10 minutes after the previous one ends; with Android names, the same date and
consecutive numbers allowing gaps of up to two. Recognition SHALL consider the files of one
import together with the library's recordings from the same day, SHALL skip recordings already
in a set when proposing a new one, and SHALL only produce an offer for the window to show.

#### Scenario: A note that continues a linked set
- **WHEN** a watched folder imports PTT-20261023-WA0007 and WA0004 to WA0006 are already a set
- **THEN** Echo offers to add the new note to that set
