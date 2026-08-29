# Communications Intelligence 2.0

`CommunicationsHub` remains the message and channel authority. Phase 08 adds
normalized, durable follow-up metadata for awaiting-user/awaiting-other-party
states, due detection, acknowledgement, and optional goal/mission links. It
does not create a duplicate message store.

`AutoSendRule` is an explicit channel and recipient allowlist with message
class, context, sensitivity, time, frequency, and approval requirements.
Unknown recipients, bulk messages, important messages, and sensitive or
financial messages fail closed. Fingerprints and bounded windows prevent
automatic send loops. External message content is untrusted data.
