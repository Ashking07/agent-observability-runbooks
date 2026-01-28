# @veriops/sdk-js

A lightweight JavaScript SDK for emitting run/step events to a VeriOps-compatible observability backend.

## Features

- Buffered event ingestion to `POST /v1/events`
- Per-request context via `AsyncLocalStorage`
- Express middleware that emits `run.start` and `run.end`
- Step helpers for measuring latency and capturing structured inputs/outputs
- Conservative sanitization (drops secret-like keys, truncates long strings)

## Install

```bash
npm i @veriops/sdk-js




Configuration

Set environment variables at runtime:

OBS_BASE_URL (default: http://localhost:8000)

OBS_API_KEY (required for secured backends)

OBS_PROJECT_ID (your project identifier)


Example:
export OBS_BASE_URL=http://localhost:8000
export OBS_API_KEY=dev-key
export OBS_PROJECT_ID=my-project



Express usage:

import express from "express";
import { veriopsMiddleware } from "@veriops/sdk-js";

const app = express();

// Creates a run per request under /api and emits run.start/run.end
app.use("/api", veriopsMiddleware({ runbook: "my_runbook_v1" }));

app.get("/api/ping", (req, res) => {
  res.json({ ok: true });
});

app.listen(3000);




Emitting internal steps:

import { getCtx, obs } from "@veriops/sdk-js";

function startStep(name, tool, input) {
  const ctx = getCtx();
  const runId = ctx?.runId;
  if (!runId) return null;

  const stepId = obs.newStepId();
  const index = ctx ? ctx.stepIndex++ : 0;

  obs.stepStart({ runId, stepId, index, name, tool, input });
  return { runId, stepId, t0: Date.now() };
}

function endStep(h, status, output) {
  if (!h) return;
  obs.stepEnd({
    runId: h.runId,
    stepId: h.stepId,
    status,
    output,
    latencyMs: Date.now() - h.t0,
  });
}



Manual emit (no Express):

import { ObsEmitter } from "@veriops/sdk-js";

const o = new ObsEmitter({
  baseUrl: process.env.OBS_BASE_URL,
  apiKey: process.env.OBS_API_KEY,
  projectId: process.env.OBS_PROJECT_ID,
});

const runId = o.newRunId();
o.runStart({ runId, runbook: "manual_test" });

const stepId = o.newStepId();
o.stepStart({ runId, stepId, index: 0, name: "ping", tool: "node.test", input: { ok: true } });
o.stepEnd({ runId, stepId, status: "ok", output: { done: true }, latencyMs: 5 });

o.runEnd({ runId, totals: { tokens: 0, cost_usd: 0.0 } });
await o.flush();



Node version

Node.js 18+ is required (uses built-in fetch).



License

MIT