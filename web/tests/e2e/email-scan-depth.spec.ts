import { test, expect } from "@playwright/test";

/**
 * E2E tests for depth-gated email scan (charter §5).
 *
 * Verifies that the /email/scan-schedule endpoint respects the user's
 * email integration depth setting:
 *   sync_notify     → read-only, no agent actions
 *   agent_mediated  → draft replies included, agent_actions_enabled=true
 *   full_two_way    → suggestions auto-actionable, autonomous_enabled=true
 *
 * These tests hit the API directly (no connected email providers needed —
 * the depth fields are present even with an empty inbox).
 */
test.describe("Email scan depth gating", () => {
  test("scan at sync_notify has no agent actions", async ({ request }) => {
    // Ensure depth is sync_notify
    await request.post("http://localhost:8000/api/a-cal/settings/email", {
      data: { depth: "sync_notify", auto_scan_enabled: false },
    });

    const resp = await request.post("http://localhost:8000/api/a-cal/email/scan-schedule");
    expect(resp.ok()).toBeTruthy();
    const body = await resp.json();
    expect(body.depth).toBe("sync_notify");
    expect(body.agent_actions_enabled).toBe(false);
    expect(body.autonomous_enabled).toBe(false);
  });

  test("scan at agent_mediated enables draft replies", async ({ request }) => {
    await request.post("http://localhost:8000/api/a-cal/settings/email", {
      data: { depth: "agent_mediated", auto_scan_enabled: true },
    });

    const resp = await request.post("http://localhost:8000/api/a-cal/email/scan-schedule");
    expect(resp.ok()).toBeTruthy();
    const body = await resp.json();
    expect(body.depth).toBe("agent_mediated");
    expect(body.agent_actions_enabled).toBe(true);
    expect(body.autonomous_enabled).toBe(false);
  });

  test("scan at full_two_way enables autonomous actions", async ({ request }) => {
    await request.post("http://localhost:8000/api/a-cal/settings/email", {
      data: { depth: "full_two_way", auto_scan_enabled: true },
    });

    const resp = await request.post("http://localhost:8000/api/a-cal/email/scan-schedule");
    expect(resp.ok()).toBeTruthy();
    const body = await resp.json();
    expect(body.depth).toBe("full_two_way");
    expect(body.agent_actions_enabled).toBe(true);
    expect(body.autonomous_enabled).toBe(true);
  });

  test("suggestions include draft_reply and auto_action fields", async ({ request }) => {
    await request.post("http://localhost:8000/api/a-cal/settings/email", {
      data: { depth: "agent_mediated" },
    });

    const resp = await request.post("http://localhost:8000/api/a-cal/email/scan-schedule");
    expect(resp.ok()).toBeTruthy();
    const body = await resp.json();
    // Even with no emails, the stats should include the new fields
    expect(body.stats).toHaveProperty("draft_replies");
    expect(body.stats).toHaveProperty("auto_actions");
  });
});
