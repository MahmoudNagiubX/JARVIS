# Communications Adapters

The deterministic local channel is the Phase 08 baseline. External IMAP/SMTP,
Telegram, or Discord adapters may implement the existing channel/provider
contracts later. Credentials remain outside Git, no paid provider is required,
and no unofficial WhatsApp scraping is supported.

Without configured credentials and a live acceptance run, external messaging
status is `DEFERRED`; a draft is never reported as sent.
