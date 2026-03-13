# ChatGPT Actions Setup

Use this integration with ChatGPT through a `Custom GPT` plus `Custom Actions`.

## What You Need

- a public HTTPS Home Assistant URL
- the `Discord Chat Bridge` integration installed and configured
- at least one channel with `include_in_api` enabled
- your bridge API key

## Schema

This repo includes an OpenAPI schema at:

- [openapi.yaml](/Users/scottobryan/Source/ha-discord-bridge/openapi.yaml#L1)

If you want to import it directly from GitHub, use the raw file URL:

- `https://raw.githubusercontent.com/darkarena1/ha-discord-bridge/main/openapi.yaml`

Before using it, replace:

- `https://YOUR_HOME_ASSISTANT_URL`

with your real Home Assistant external HTTPS URL.

Example:

- `https://your-home-assistant.example.com`

## Custom GPT Setup

1. Open the GPT builder.
2. Create a new GPT.
3. Add a new `Action`.
4. Import or paste the OpenAPI schema.
5. Set authentication to `API Key`.
6. Use:
   - header name: `X-API-Key`
   - value: your bridge API key

If the builder does not preserve the header from the schema automatically, enter it manually in the Action authentication UI.

## Recommended GPT Instructions

Suggested behavior for the GPT:

- use `/channels` first to discover the allowed channels
- use `/channels/{channel_id}` to inspect channel status and recent cache state
- use `/messages` when you need recent history
- use `/pins` when you need stable channel guidance or setup information
- use `refresh=true` when freshness matters more than latency
- only use `POST /messages` for channels where `allow_posting` is true

## Important Limits

- ChatGPT Actions cannot call `localhost`; the Home Assistant URL must be publicly reachable over HTTPS
- if you publish the GPT publicly, OpenAI requires domain verification and a privacy policy for GPTs that call external APIs
- this integration uses a shared API key, so anyone with that key can call the bridge endpoints exposed to that key

## Operator Recommendation

For a first rollout:

1. expose only a small allowlist of Discord channels
2. keep posting enabled only where necessary
3. verify the GPT using read-only channels first
4. expand posting access after you confirm prompts and behavior are safe
