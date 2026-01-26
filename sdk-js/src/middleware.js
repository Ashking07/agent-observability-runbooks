import { als, obs } from "./context.js";

export function veriopsMiddleware({ runbook = "shortify_v1" } = {}) {
  return (req, res, next) => {
    const runId = obs.newRunId();
    const store = { runId, stepIndex: 0, runbook };

    als.run(store, () => {
      obs.runStart({ runId, runbook });

      res.on("finish", async () => {
        obs.runEnd({
          runId,
          totals: { tokens: 0, cost_usd: 0.0, http_status: res.statusCode },
        });
        await obs.flush();
      });

      next();
    });
  };
}
