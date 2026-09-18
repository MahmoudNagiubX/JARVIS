# Browser automation

Browser actions are isolated behind `BrowserActionService` and typed browser
contracts. The dependency-free local adapter supports URL sessions, bounded
HTML reads, text extraction, links, headings, accessibility-shaped metadata,
find, back, and session listing. URL schemes are restricted to HTTP and
HTTPS, response bodies are bounded, and no arbitrary JavaScript or shell
execution is exposed.

`PlaywrightBrowserController` is an optional lazy Playwright adapter behind the
same `BrowserActionService` authority. It launches only an exact configured
Brave executable, uses fresh isolated ephemeral contexts by default, and can
use a dedicated JARVIS-owned persistent profile only after an explicit local
opt-in. It never attaches to the normal Brave profile, accepts no model
controlled profile/mode/JavaScript/CDP arguments, and closes only the contexts
and browser processes it created. The base runtime remains dependency-free and
does not download a browser; the optional `browser-playwright` extra pins the
Playwright dependency.

The dependency-free Local controller remains the default offline backend.
Browser reads require the matching device capability; interaction actions are
consequential and remain approval-bound. Optional Playwright click/type/select
now use T3 opaque grounding, actionability, approval binding, and independent
verification. T5 adds approved-root, bounded download/upload workflows and
on-demand transient screenshots through the same controller; no raw screenshot
bytes enter model output, audit, filesystem history, or Memory. Live
owner-authenticated acceptance and the T6 red-team matrix remain later Browser
V2 gates. Reads use the
dependency-free static path by default and return bounded provenance-aware
content; the optional dynamic path uses the same bounds and treats all page
content as untrusted data.
