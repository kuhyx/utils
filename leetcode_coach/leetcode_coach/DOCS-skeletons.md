# Skeleton sheets: the rule for Claude

A skeleton sheet is one code template with holes for one curriculum unit. It shows the shape of the unit's standard pattern (loop frame, map idiom, pointer frame) and leaves every decision as a hole. It never solves a problem.

## When you may show one

Show a sheet only when all three hold:

1. kuhy has made his first code attempt in this solve (the session log has a `code` event).
2. kuhy asks for it. Never offer it, never hint that it exists, never show it unasked.
3. The session is a normal session or a review.

Before his first code attempt, answer "give me a skeleton" with the next hint-ladder step instead, and say the sheet unlocks after his first attempt.

## How to open it

Run the command; it logs the open and prints the sheet.

COMMAND: skeleton-open <slug> <unit>

Opening a sheet counts above hint H1. That solve gets no sign-off: tell kuhy so in one line before you run the command, and run it only after he repeats the request.

## Which unit

Use the problem's latest curriculum unit: the unit that comes last in this order among the problem's topic tags. A problem with no topic tags (the JavaScript and pandas sets) uses `js-pandas`.

scans, hashing, math, bits, sorting-greedy, pointers-window, prefix-sums, stack-queue, binary-search, lists-recursion, trees, heap-dp, sql, js-pandas

## How to print it

The command prints the sheet file `skeletons/DOCS-<unit>.md`. Three print rules:

1. Open the code fence with three backticks and no language tag (a tag such as `sql` or `ts` changes the text the Stop gate compares).
2. Print the sheet exactly as the command printed it: no shortened lines, no renamed variable, no filled hole, no line of your own.
3. Print each fence of the sheet as its own fence, one fence per fence (js-pandas has two).

After the sheet, ask kuhy one question: which hole he fills first.

If he asks you to fill a hole, treat it as a request for a solution: refuse and ask what he thinks goes there.

## Why the wording matters

The Stop gate bounces a reply that holds code using the problem's own identifiers, except a snippet that matches text already in the transcript. The command's output is such text, so a verbatim sheet passes. The gate lets the sheet through only as a verbatim quote of the command output; a changed sheet is new code and gets bounced.
