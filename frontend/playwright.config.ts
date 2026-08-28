import { defineConfig } from "@playwright/test";

const realStack =
  process.env.RUN_REAL_STACK_E2E === "1" ||
  process.env.RUN_REAL_EXPERIMENT_E2E === "1";

export default defineConfig({
  testDir: "./e2e",
  use: {
    baseURL: realStack ? "http://127.0.0.1:3000" : "http://127.0.0.1:3100",
    trace: "retain-on-failure",
  },
  webServer: realStack
    ? undefined
    : {
        command: "npm run dev -- --port 3100",
        url: "http://127.0.0.1:3100/projects",
        reuseExistingServer: true,
      },
});
