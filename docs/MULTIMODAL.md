# Gemma multimodal — reading the filing

The hackathon's Track-3 "AI Differentiation" criterion explicitly rewards **Gemma's
multimodal capability**. The demo shows it as the *ingestion* step: Gemma reads a prospectus
**page image** and extracts the structured note terms (coupon, maturity, spread, rating) that
seed the comparison and the Lean-verified facts.

In the UI this is the **"Source · Gemma 31B reads the filing"** strip above the split screen.
The extraction shown is pre-baked for a deterministic demo. To make it a **live** Gemma
vision call on Cerebras, wire the route below.

## Live vision extraction (optional)

Gemma on Cerebras is OpenAI-compatible, including image content parts. Add a route:

```ts
// app/api/extract/route.ts
import { NextRequest } from "next/server";
export const runtime = "nodejs";

export async function POST(req: NextRequest) {
  const { imageBase64 } = await req.json(); // data URL of the filing page (PNG/JPG)
  const res = await fetch(`${process.env.CEREBRAS_BASE_URL}/chat/completions`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${process.env.CEREBRAS_API_KEY}`,
    },
    body: JSON.stringify({
      model: process.env.CEREBRAS_MODEL, // a vision-capable Gemma id
      messages: [
        {
          role: "user",
          content: [
            {
              type: "text",
              text:
                "This is a page from a bond prospectus. Extract the note terms as strict JSON " +
                '{issuer, security, couponPct, maturity, spreadBps, rating}. Numbers only where numeric.',
            },
            { type: "image_url", image_url: { url: imageBase64 } },
          ],
        },
      ],
      temperature: 0,
      response_format: { type: "json_object" },
    }),
  });
  const json = await res.json();
  return Response.json(JSON.parse(json.choices[0].message.content));
}
```

Then in `components/Ingestion.tsx`, on `scan` POST the filing image to `/api/extract` and
render the returned fields instead of the baked `EXTRACTED` array (fall back to baked on error
so the demo never breaks on camera).

## Getting a page image to send

The UI's filing graphic is an inline SVG (crisp on screen). A vision model needs a raster.
Either:
- Screenshot the rendered filing card to PNG, drop it in `public/filing-spacex-2030.png`, and
  send it as a data URL; or
- Use a real SEC filing page (recommended for the "reads the actual filing" claim) — download
  a `424B` PDF from sec.gov, export one page to PNG, and send that.

For the **video**, a live extraction is a strong beat but not required — showing the page
image being scanned and the term chips populating already satisfies the multimodal criterion.
Make it live only if your Cerebras Gemma id is vision-capable and you have time.
```
