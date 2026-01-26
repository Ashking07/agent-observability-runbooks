import { randomUUID } from "crypto";

const OBS_BASE_URL = (process.env.OBS_BASE_URL || "http://localhost:8000").replace(/\/+$/, "");
const OBS_API_KEY = process.env.OBS_API_KEY || "dev-key";
const OBS_PROJECT_ID = process.env.OBS_PROJECT_ID || "shortify";

function nowIsoZ() {
  return new Date().toISOString();
}

function truncateStr(s, n = 512) {
  return s.length > n ? s.slice(0, n) + "…" : s;
}

// Conservative redaction: never ship secrets-like keys; truncate strings.
function safeObj(obj) {
  if (!obj || typeof obj !== "object") return {};
  const out = {};
  for (const [k, v] of Object.entries(obj)) {
    if (/(authorization|cookie|token|secret|password)/i.test(k)) continue;
    if (typeof v === "string") out[k] = truncateStr(v, 512);
    else out[k] = v;
  }
  return out;
}

export class ObsEmitter {
  constructor({ baseUrl = OBS_BASE_URL, apiKey = OBS_API_KEY, projectId = OBS_PROJECT_ID } = {}) {
    this.baseUrl = baseUrl;
    this.apiKey = apiKey;
    this.projectId = projectId;
    this.buffer = [];
  }

  newRunId() { return randomUUID(); }
  newStepId() { return randomUUID(); }

  enqueue(evt) { this.buffer.push(evt); }

  async flush() {
    if (this.buffer.length === 0) return;
    const events = this.buffer;
    this.buffer = [];

    try {
      const resp = await fetch(`${this.baseUrl}/v1/events`, {
        method: "POST",
        headers: { "x-api-key": this.apiKey, "content-type": "application/json" },
        body: JSON.stringify({ events }),
      });

      if (!resp.ok) {
        const txt = await resp.text();
        console.warn("[veriops] ingest failed", resp.status, txt.slice(0, 300));
      }
    } catch (e) {
      console.warn("[veriops] ingest error", e?.message || e);
    }
  }

  runStart({ runId, runbook }) {
    this.enqueue({ type: "run.start", run_id: runId, project_id: this.projectId, runbook, ts: nowIsoZ() });
  }

  runEnd({ runId, totals }) {
    this.enqueue({ type: "run.end", run_id: runId, totals, ts: nowIsoZ() });
  }

  stepStart({ runId, stepId, index, name, tool, input }) {
    this.enqueue({
      type: "step.start",
      run_id: runId,
      step_id: stepId,
      index,
      name,
      tool,
      input: safeObj(input),
      ts: nowIsoZ(),
    });
  }

  stepEnd({ runId, stepId, status = "ok", output, latencyMs, tokens, costUsd }) {
    const evt = {
      type: "step.end",
      run_id: runId,
      step_id: stepId,
      output: safeObj(output || {}),
      status,
      ts: nowIsoZ(),
    };
    if (latencyMs != null) evt.latency_ms = Math.max(0, Math.floor(latencyMs));
    if (tokens != null) evt.tokens = tokens;
    if (costUsd != null) evt.cost_usd = costUsd;
    this.enqueue(evt);
  }
}
