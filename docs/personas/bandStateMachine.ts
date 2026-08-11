/**
 * Continuity Architect v1.1.0 — Expanded Band State Machine
 *
 * Pure core preserved. Projection + in-memory event bus as optional layers.
 * Aegis product runtime: Python `aegis.budget_aware` + `aegis.burn`.
 *
 * Band mapping: normal↔ok · caution · adaptive↔warn · emergency↔critical
 */

export type Band = "normal" | "caution" | "adaptive" | "emergency";

export interface BandConfig {
  cautionEnter: number;
  cautionExit: number;
  adaptiveEnter: number;
  adaptiveExit: number;
  emergencyEnter: number;
  emergencyExit: number;
  /** Optional projection horizon in milliseconds (default 60_000) */
  projectionHorizonMs?: number;
}

export interface BandState {
  current: Band;
  enteredAt: number;
  usageRatio: number;
  /** Linear projection of usage ratio at the end of the horizon */
  projectedEndOfWindow?: number;
}

export interface BudgetDecisionEvent {
  ts: number;
  previousBand: Band;
  currentBand: Band;
  usageRatio: number;
  projectedEndOfWindow?: number;
  reason: string;
}

export type EventHandler = (event: BudgetDecisionEvent) => void;

export const DEFAULT_CONFIG: BandConfig = {
  cautionEnter: 0.8,
  cautionExit: 0.72,
  adaptiveEnter: 1.0,
  adaptiveExit: 0.9,
  emergencyEnter: 1.25,
  emergencyExit: 1.1,
  projectionHorizonMs: 60_000,
};

/** Simple linear projection based on recent rate of change */
export function projectUsage(
  currentRatio: number,
  previousRatio: number,
  elapsedMs: number,
  horizonMs: number
): number {
  if (elapsedMs <= 0) return currentRatio;
  const ratePerMs = (currentRatio - previousRatio) / elapsedMs;
  return currentRatio + ratePerMs * horizonMs;
}

/**
 * Pure transition. Optional previous sample enables projection-based early enter.
 */
export function transitionBand(
  prev: BandState,
  usageRatio: number,
  now: number = Date.now(),
  config: BandConfig = DEFAULT_CONFIG,
  previousUsageRatio?: number,
  previousTimestamp?: number
): { state: BandState; event?: BudgetDecisionEvent } {
  let projected: number | undefined;
  if (
    previousUsageRatio !== undefined &&
    previousTimestamp !== undefined &&
    config.projectionHorizonMs
  ) {
    const elapsed = now - previousTimestamp;
    projected = projectUsage(
      usageRatio,
      previousUsageRatio,
      elapsed,
      config.projectionHorizonMs
    );
  }

  const effective = Math.max(usageRatio, projected ?? usageRatio);
  let next: Band = prev.current;

  // Enter paths: current OR projected (proactive)
  if (effective >= config.emergencyEnter) {
    next = "emergency";
  } else if (effective >= config.adaptiveEnter) {
    next = "adaptive";
  } else if (effective >= config.cautionEnter) {
    next = "caution";
  } else {
    // Exit with hysteresis (use current ratio only — not projection)
    switch (prev.current) {
      case "emergency":
        if (usageRatio < config.emergencyExit) {
          next =
            usageRatio >= config.adaptiveEnter
              ? "adaptive"
              : usageRatio >= config.cautionEnter
                ? "caution"
                : "normal";
        }
        break;
      case "adaptive":
        if (usageRatio < config.adaptiveExit) {
          next = usageRatio >= config.cautionEnter ? "caution" : "normal";
        }
        break;
      case "caution":
        if (usageRatio < config.cautionExit) next = "normal";
        break;
    }
  }

  const state: BandState = {
    current: next,
    enteredAt: next === prev.current ? prev.enteredAt : now,
    usageRatio,
    projectedEndOfWindow: projected,
  };

  if (next === prev.current) {
    return { state };
  }

  const event: BudgetDecisionEvent = {
    ts: now,
    previousBand: prev.current,
    currentBand: next,
    usageRatio,
    projectedEndOfWindow: projected,
    reason: projected
      ? `Threshold crossed (current or projected). Projected=${projected.toFixed(3)}`
      : `Threshold crossed under config`,
  };

  return { state, event };
}

export function createInitialBandState(usageRatio = 0): BandState {
  return {
    current: "normal",
    enteredAt: Date.now(),
    usageRatio,
  };
}

/** Minimal in-memory event bus — sync, ordered, fail-soft */
export class BandEventBus {
  private handlers: EventHandler[] = [];

  subscribe(handler: EventHandler): () => void {
    this.handlers.push(handler);
    return () => {
      this.handlers = this.handlers.filter((h) => h !== handler);
    };
  }

  publish(event: BudgetDecisionEvent): void {
    const snapshot = [...this.handlers];
    for (const handler of snapshot) {
      try {
        handler(event);
      } catch (err) {
        console.error("[BandEventBus] handler error", err);
      }
    }
  }
}

/** Façade: projection samples + auto-publish */
export class BandController {
  private state: BandState;
  private lastUsageRatio: number;
  private lastTimestamp: number;
  private bus: BandEventBus;
  private config: BandConfig;

  constructor(config: Partial<BandConfig> = {}, bus?: BandEventBus) {
    this.config = { ...DEFAULT_CONFIG, ...config };
    this.state = createInitialBandState();
    this.lastUsageRatio = 0;
    this.lastTimestamp = Date.now();
    this.bus = bus ?? new BandEventBus();
  }

  getState(): BandState {
    return { ...this.state };
  }

  getBus(): BandEventBus {
    return this.bus;
  }

  update(usageRatio: number, now: number = Date.now()): BandState {
    const { state, event } = transitionBand(
      this.state,
      usageRatio,
      now,
      this.config,
      this.lastUsageRatio,
      this.lastTimestamp
    );

    this.state = state;
    this.lastUsageRatio = usageRatio;
    this.lastTimestamp = now;

    if (event) {
      this.bus.publish(event);
    }

    return this.getState();
  }
}
