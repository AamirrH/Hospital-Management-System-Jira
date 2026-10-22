# SCRUM-7 Patient Registration Bug Report Drafts

All 29 automated tests passed in the final pytest run. No application bugs were observed, so no bug report drafts were created.

The five manual UI test cases in the test-case workbook remain pending manual execution.

---

# SCRUM-9 Patient Search Bug Report Drafts

## BUG-S9-01: Patient ID 0 is accepted as a valid search criterion

- **Severity:** Major
- **Priority:** High
- **Description:** Server-side search validation accepts Patient ID `0`, although valid IDs must be whole numbers greater than or equal to 1. The request proceeds to a search and displays the no-match message instead of a validation error.
- **Steps to reproduce:**
  1. Start the HMS application with the seeded patient database.
  2. Open `/patients/search?patient_id=0&name=`.
  3. Observe the Patient ID field and response beneath the form.
- **Expected result:** Patient ID `0` is rejected with a clear message stating that the ID must be 1 or greater; no search is performed.
- **Actual result:** Patient ID `0` is retained, no validation error is shown, and the page displays `No patients found.`
- **Related test case ID:** TC-S12
- **Story:** SCRUM-9
- **Screenshot:** `docs/screenshots/BUG_TC-S12_zero-id-accepted.png`

## BUG-S9-02: A 51-character name is accepted by server-side validation

- **Severity:** Minor
- **Priority:** Medium
- **Description:** Server-side name validation permits 51 characters even though the allowed maximum after trimming is 50 characters.
- **Steps to reproduce:**
  1. Start the HMS application with the seeded patient database.
  2. Open `/patients/search?patient_id=&name=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA` (51 `A` characters).
  3. Observe the Name field and response beneath the form.
- **Expected result:** The name is rejected with `Name must be between 2 and 50 characters.` and no search is performed.
- **Actual result:** The 51-character value is retained, no validation error is shown, and the page displays `No patients found.`
- **Related test case ID:** TC-S18
- **Story:** SCRUM-9
- **Screenshot:** `docs/screenshots/BUG_TC-S18_name-51-accepted.png`

## BUG-S9-03: Empty search criteria return every patient

- **Severity:** Major
- **Priority:** High
- **Description:** When both search fields are empty after trimming, validation does not require at least one criterion. The unfiltered query returns all six patient records.
- **Steps to reproduce:**
  1. Start the HMS application with the seeded patient database.
  2. Open `/patients/search`.
  3. Leave Patient ID and Name empty and select **Search**.
  4. Repeat with Patient ID empty and Name containing three spaces by opening `/patients/search?patient_id=&name=%20%20%20`.
- **Expected result:** Both requests show a clear error asking for at least one search field, and no patient records are displayed.
- **Actual result:** Both requests display all six seeded patient records and show no validation error.
- **Related test case IDs:** TC-S19, TC-S20
- **Story:** SCRUM-9
- **Screenshots:** `docs/screenshots/BUG_TC-S19_empty-search-returns-all.png`, `docs/screenshots/BUG_TC-S20_whitespace-search-returns-all.png`

## BUG-S9-04: Name search is case-sensitive

- **Severity:** Major
- **Priority:** High
- **Description:** Partial-name search compares case exactly, so differently cased queries do not return every matching record. With seeded records `Ravi Kumar` and `ravi singh`, all casing variants should return both rows.
- **Steps to reproduce:**
  1. Start the HMS application with the seeded patient database.
  2. Open `/patients/search` and search by Name `ravi`; observe the rows.
  3. Repeat with Name `RAVI`.
  4. Repeat with Name `Ravi`.
- **Expected result:** Each query returns both `Ravi Kumar` and `ravi singh`.
- **Actual result:** `ravi` returns only `ravi singh`; `RAVI` returns no patients; `Ravi` returns only `Ravi Kumar`.
- **Related test case IDs:** TC-S22, TC-S23, TC-S24
- **Story:** SCRUM-9
- **Screenshots:** `docs/screenshots/BUG_TC-S22_lowercase-search-case-sensitive.png`, `docs/screenshots/BUG_TC-S23_uppercase-search-case-sensitive.png`, `docs/screenshots/BUG_TC-S24_titlecase-search-case-sensitive.png`
