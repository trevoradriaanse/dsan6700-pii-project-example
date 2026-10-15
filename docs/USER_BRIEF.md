# Need to Know: user brief

*The worked example, in the shape of Homework 3. Current URL: http://149.165.170.89:8000 (the address changes when the
instance is unshelved; this line is updated each time.)*

**Who is the user?** Someone about to share one of their own documents (a lease, a bank statement, a tax form, a
resume) who wants to remove the personal information the reader does not need. Not technical; uses it a few times a
year; cares most about not leaking an account number.

**Where should the user go?** The application at the URL above. The README in this repository.

**How should you get started, and what should you test?** Use only the synthetic PDFs from pdf-pii-bench
(`data/pdfs/` in https://github.com/callixdev/pdf-pii-bench), never a real document.
- Redact a lease so that it could be sent to a new employer: they need the dates and the rent, nothing else.
- Redact a bank statement so that it could be sent to a landlord as proof of income.
- Try the things a real user would: a file that is not a PDF, a long PDF, unchecking a finding you want to keep.

**What can the skeleton do, and what can it not do?** It reads PDFs with a text layer, finds personal information of a
fixed shape (emails, phone numbers, ID and account numbers, dates, street addresses), and removes what you select so it
cannot be copied back out. It does **not** find names yet, does not read scanned PDFs or Word files, and does not keep
your file: if you reload the page, you start over. It counts how many documents were checked and how many items
were found, and nothing else about them.

**What feedback are we seeking?** Where did you hesitate? What did it miss that you would have removed, and what did it
remove that you needed to keep? Would you trust the downloaded file enough to send it?
