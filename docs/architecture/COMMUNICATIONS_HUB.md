# Communications hub

`CommunicationsHub` normalizes configured channels into list, sync, read,
search, draft, and send operations. The default runtime registers only the
local in-memory channel, which makes offline development deterministic and
does not imply an external account connection.

Drafts are local and do not send. Sends require the authenticated device's
`communication.send` capability, pass permission and autonomy policy, and are
audited with communication events. Important or policy-sensitive messages
produce a durable approval request and can be resumed explicitly.

Email, Telegram, Discord, and other network providers are adapter candidates,
not hidden dependencies. They remain deferred until an explicitly configured
free/self-hosted provider and credential path is available.
