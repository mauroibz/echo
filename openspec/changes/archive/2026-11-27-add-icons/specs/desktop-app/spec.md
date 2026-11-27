## ADDED Requirements

### Requirement: Icons for recordings and collections
The user SHALL be able to give a recording, several at once, or a collection an optional icon: one
of the symbols offered, in the text's color or one of the colors offered, chosen in a picker
(the color, then the symbol) that also removes it. A recording's icon SHALL show before its title
in the list; a collection's SHALL replace its folder in the bar and in the line under Record. A
collection's icon SHALL follow a rename and go when the collection is emptied. Without an icon
everything SHALL look as it did.

#### Scenario: Finding a client's collection
- **WHEN** the user right-clicks the collection IHSA, chooses Icon…, the green color and the hospital
- **THEN** IHSA's row and the line under Record show a green hospital, now and after restarting Echo
