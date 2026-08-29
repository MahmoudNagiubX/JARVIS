# Room Voice Setup

Register a trusted `VoiceEndpoint` with an owner, device, room, input/output
flags, and online state through `VoiceRoutingService`. Presence may use that
endpoint's explicit activity and TTL. Keep endpoints loopback/local until a
deployment adapter is independently reviewed.

Physical microphones, speakers, AEC, far-field capture, and satellite
transport remain deployment adapters. This repository does not claim physical
voice acceptance or clone a person's voice.
