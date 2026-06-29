// Sampling params held IDENTICAL across both providers. The comparison varies
// only the inference engine — not the prompt, the model, or how it decodes —
// so this lives in one place and is both sent to the API and shown in the UI.
export const SAMPLING = { temperature: 0.3, maxTokens: 1500 } as const;
