# Ideas

**Keep this repo private.** Every idea for every project lands here, word for word, and gets sorted
onto that project's page. The lanes plugin files them (`/lanes:ideas`) and puts each project's ideas
in front of the next session that works on it.

## Writing one down

Type a line into [`DUMP.md`](DUMP.md), from anywhere, including GitHub on a phone:

```
[project; part] the idea
```

Only the project is required. Several ideas: one line each. No brackets at all is fine too; the
session asks which project only if it cannot tell. An open issue on this repo works the same way,
with the bracket line as its title.

## Project names

List the short names you will actually type, so filing never has to guess.

| Project | Also accepted |
| --- | --- |
| **Example project** | `example`, `ex` |

## Headings on a page

Ideas are filed by **what they do**, not what they touch. Headings appear when needed and go when empty.

| Heading | What goes there |
| --- | --- |
| **Features** | what it can do |
| **Look & feel** | anything that only changes how it looks or sounds |
| **Controls** | what your hands do |
| **Parked** | not now, with the reason |

## The two tags on every idea

**Wanted?** `[raw]` written down · `[considered]` talked about · `[settled]` yes · `[killed]` no, kept so it is not re-proposed.

**Buildable?** `[not judged]` · `[already works]` · `[looks doable]` · `[hard]` · `[needs something we don't have]` · `[can't see how]`.

Only you settle or kill an idea.

## Layout

| Path | Holds |
| --- | --- |
| `DUMP.md` | where you write; emptied after each filing |
| `inbox/` | your words, verbatim, one dated file per filing; never edited |
| `pages/` | one page per project, ideas under headings |
| `decisions.md` | what was kept or dropped, and when |
| `repos.tsv` | which project repo each page feeds (`*` every active project, `-` none yet) |
