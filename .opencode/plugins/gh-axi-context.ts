import { execFile } from "node:child_process"
import { promisify } from "node:util"
import { Plugin } from "@opencode/plugin"

const GH_AXI_TIMEOUT_MILLISECONDS = 10_000
const runCommand = promisify(execFile)

async function readGitHubDashboard(projectDirectory: string): Promise<string | undefined> {
  try {
    const { stdout } = await runCommand("gh-axi", [], {
      cwd: projectDirectory,
      timeout: GH_AXI_TIMEOUT_MILLISECONDS,
      maxBuffer: 1024 * 1024,
      windowsHide: true,
    })

    const dashboard = stdout.trim()
    return dashboard.length > 0 ? dashboard : undefined
  } catch {
    return undefined
  }
}

export default Plugin.define({
  id: "gh-axi-context",
  async setup(ctx) {
    const dashboardsBySession = new Map<string, string>()

    await ctx.session.hook("context", async (event) => {
      if (!dashboardsBySession.has(event.sessionID)) {
        const dashboard = await readGitHubDashboard(ctx.location.directory)
        dashboardsBySession.set(event.sessionID, dashboard ?? "")
      }

      const dashboard = dashboardsBySession.get(event.sessionID)
      if (dashboard) {
        event.system.push({
          type: "text",
          text: `GitHub context (from gh-axi):\n\n${dashboard}`,
        })
      }
    })
  },
})
