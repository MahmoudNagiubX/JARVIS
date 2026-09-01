# Phase 15 Browser Capability Architecture

The existing `BrowserActionService` is the browser authority. It applies
identity/device authorization, risk classification, approval, audit, and event
emission before calling either the deterministic `LocalBrowserController` or an
injected Playwright adapter.

The local controller is the automated test and offline fallback path. It uses
bounded URL fetches and HTML parsing for navigation, page/DOM reads, structured
links/headings, element lookup, and simple click/type/select interactions. It
does not expose browser credentials or raw typed values in result payloads.

Reads use the existing read capability set. Click, type, select, upload,
download, and other mutations stay consequential and require the existing
approval engine. Malicious page text is returned as page data only. No visual
browser agent or second browser authority is introduced.
