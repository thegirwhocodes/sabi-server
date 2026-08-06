# Twilio SIP carrier route

Sabi uses Twilio Elastic SIP Trunking only as the telephone transport. Asterisk
still answers the call, records the caller and Sabi channels, and opens the same
full-duplex AudioSocket connection to the production Gemini/lesson/TTS lane.
The old turn-by-turn `voice_twilio.py` webhook is not part of this route.

## Production shape

- Twilio number: `+17153122345`
- Termination domain: `sabi-education-for-equality.pstn.twilio.com`
- Asterisk endpoint: `twilio`
- Audio codec preference: G.711 mu-law, with A-law fallback
- Authentication from Asterisk to Twilio: fixed server IP ACL
- Registration/OPTIONS qualification: disabled (Twilio trunks do not register,
  and the termination URI does not answer Asterisk's bare-URI probe)
- Lesson lane: `AudioSocket(${AS_UUID},sabi:9020)`
- Africa's Talking endpoint remains configured as `africastalking` for rollback

## Firewall prerequisite and August 6 incident

Twilio must not be selected until UDP SIP responses from every documented
Twilio regional signaling `/30` can reach Asterisk on port 5060. The production
firewall source of truth is `ops/apply-docker-firewall.sh`.

During the first controlled test on August 6, one operator request produced
eight PSTN calls. The application logged only one originate and no callback
retries. Asterisk repeatedly transmitted the unanswered SIP `INVITE` because
the old firewall accepted only Africa's Talking as a SIP source. Twilio created
new PSTN legs from those retransmissions, while Asterisk never received the SIP
answer; this is also why answered calls carried no Sabi audio.

Safety state after the incident:

- automatic callback retries default off and are capped at one attempt;
- production outbound routing stays on Africa's Talking until the Twilio
  firewall rules are installed and verified;
- never use a real phone to verify the firewall itself—first prove a Twilio SIP
  response reaches Asterisk, then request one explicit human test call.

After the allowlist was installed, a manual Asterisk SIP `OPTIONS` probe
received `SIP/2.0 200 OK` from Twilio. This verified the bidirectional signaling
path without creating a PSTN call. Production remained on Africa's Talking
pending one explicitly approved end-to-end test.

The server chooses the outbound carrier with:

```dotenv
SABI_SIP_PROVIDER=twilio
SABI_CALLER_ID=+17153122345
```

To roll outbound calling back without changing the lesson system:

```dotenv
SABI_SIP_PROVIDER=africastalking
SABI_CALLER_ID=+2342017001459
```

Then recreate the `sabi` container so it reloads the environment. The Asterisk
container does not need to change because both endpoints remain present.

## Twilio account constraint

The account was still a Trial account when this route was configured on
August 6, 2026. Trial calls may play a Twilio announcement, only verified
destinations can be called, and public use requires upgrading the account.

Official references:

- https://www.twilio.com/docs/sip-trunking
- https://www.twilio.com/docs/sip-trunking/ip-addresses
- https://www.twilio.com/docs/sip-trunking/api
- https://www.twilio.com/docs/usage/tutorials/how-to-use-your-free-trial-account
