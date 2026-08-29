# Browser automation

Browser actions are isolated behind `BrowserActionService` and typed browser
contracts. The dependency-free local adapter supports URL sessions, bounded
HTML reads, text extraction, links, headings, accessibility-shaped metadata,
find, back, and session listing. URL schemes are restricted to HTTP and
HTTPS, response bodies are bounded, and no arbitrary JavaScript or shell
execution is exposed.

`PlaywrightBrowserController` is an injected adapter seam for a configured
Playwright or Playwright MCP client. It is deliberately unavailable in the
default offline runtime, so composition and tests do not require a browser
download. Click/type/select, upload/download, and screenshots report the
missing adapter explicitly. Browser reads require the matching device
capability; interaction actions are consequential and remain approval-bound.
