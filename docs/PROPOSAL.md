# Need to Know: proposal

*The worked example for DSAN 6700, written in the shape of Final Project Deliverable 1.*

## The problem
People are asked to share documents that hold far more about them than the reader needs: a lease sent to a new
employer, a bank statement sent to a landlord, a tax form sent to a scholarship office, a resume posted online. Each
one carries names, addresses, phone numbers, account and Social Security numbers, and dates of birth. Removing them
by hand is slow, easy to get wrong, and often done badly: a black box drawn over the text in a PDF viewer hides it
from the eye but leaves it in the file, where anyone can copy it out.

**Problem statement.** Someone about to share a PDF should be able to remove the personal information the reader
does not need, in under a minute, and be confident it is really gone.

## Who the users are
The person sharing their own document: a renter, a job seeker, a student applying for aid. They are not technical,
they will use it a few times a year, and they care more about not leaking an account number than about a perfect
layout. A second user, not served by this version: an office that redacts documents for others as part of its work.

## Stakeholders
- **The user**, who needs it to be fast, to catch everything that matters, and to be trustworthy with their file.
- **Legal and compliance**, who care most about what happens to a sensitive document once it reaches our server.
- **Product**, who cares whether people finish the task and come back.
- **The engineers (us)**, who need a problem we can measure and a scope we can build in a semester.

## Data
We have no users yet, and we must never collect real personal information to build this. We use pdf-pii-bench
(Catherine Nelson, CC BY 4.0): 50 realistic synthetic PDFs in eight categories (tax forms, bank statements, leases,
invoices, medical intake, resumes, contracts, email footers) with 1,121 hand-checked spans of personal information.

## Baseline and improvements
- **Baseline:** regular expressions for information with a fixed shape (emails, phone numbers, ID and account numbers,
  dates, street addresses). Quick to build, easy to explain, and blind to names.
- **Improvements:** an off-the-shelf analyzer (Presidio), then a small transformer that finds named entities (GLiNER),
  then combinations.

## Evaluation
- **Effectiveness:** the share of personal-information characters we cover (recall: a miss is a leak) and the share of
  what we cover that really is personal information (precision: over-redaction makes the document useless), on the
  benchmark, by type and by document category.
- **For the user and the business:** the time to redact one document, how often a user has to fix something by hand,
  how many people finish and download, and whether they come back.

## Risks
- A miss leaks someone's information, so recall matters more than anything else, and the user must always review.
- People may upload real documents to a demo, so the demo stores nothing and says so.
- Scanned PDFs have no text to read; out of scope for now.
- Users may trust the tool more than they should: "nothing found" is not "nothing there".

## Goals
- **Certain:** upload one PDF, see what was found, choose what to remove, download a copy with the text truly removed;
  deployed on Jetstream2; measured on the benchmark.
- **Likely:** a model-based detector that finds names, with recall above the baseline and a precision users accept.
- **Stretch:** scanned PDFs (OCR), Word documents, a confidence score per finding, and a study with real users.
