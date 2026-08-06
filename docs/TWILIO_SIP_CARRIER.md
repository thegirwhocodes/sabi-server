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
- https://www.twilio.com/docs/sip-trunking/api
- https://www.twilio.com/docs/usage/tutorials/how-to-use-your-free-trial-account
