import { Envelope, Priority } from "../protocol/types";

interface QueueItem {
  envelope: Envelope;
  enqueuedAt: number;
  priority: Priority;
}

// PriorityQueue implements a multi-level queue with aging to prevent starvation.
//
// Aging: P0 items waiting > P0_PROMOTION_S become P1;
//        P1 items waiting > P1_PROMOTION_S become P2.
export class PriorityQueue {
  private queues: QueueItem[][] = [[], [], []];
  private readonly P0_PROMOTION_S = 60;
  private readonly P1_PROMOTION_S = 120;

  push(env: Envelope): void {
    const p = (env.priority ?? 0) as Priority;
    this.queues[p].push({ envelope: env, enqueuedAt: Date.now(), priority: p });
  }

  pop(): Envelope | null {
    for (let level = 2; level >= 0; level--) {
      const q = this.queues[level];
      if (q.length === 0) continue;

      // P2 always dequeues first.
      if (level === 2) return q.shift()!.envelope;

      // Check for aged items — promote them so they get picked up.
      const now = Date.now();
      const agedIndex = q.findIndex((item) => {
        const age = (now - item.enqueuedAt) / 1000;
        return level === 0 ? age > this.P0_PROMOTION_S : level === 1 ? age > this.P1_PROMOTION_S : false;
      });

      if (agedIndex !== -1) {
        const [aged] = q.splice(agedIndex, 1);
        const newLevel = (level + 1) as Priority;
        aged.priority = newLevel;
        this.queues[newLevel].push(aged);
        continue; // retry from top
      }

      return q.shift()!.envelope;
    }

    return null;
  }

  size(): number {
    return this.queues.reduce((s, q) => s + q.length, 0);
  }

  clear(): void {
    this.queues = [[], [], []];
  }
}
