import { execFileSync } from "node:child_process";
import path from "node:path";

const projectRoot = process.env.E2E_PROJECT_ROOT ?? path.resolve(import.meta.dirname, "../../..");
const docker = process.env.DOCKER_COMMAND ?? "docker";
function container(...args: string[]): void {
  execFileSync(docker, args, { cwd: projectRoot, stdio: "inherit" });
}

export function pauseWorkerTwo(): void { container("stop", "-t", "1", "countyflow-ai-worker-2-1"); }
export function unpauseWorkerTwo(): void { container("start", "countyflow-ai-worker-2-1"); }
export function pauseWorkerOne(): void { container("pause", "countyflow-ai-worker-1-1"); }
export function unpauseWorkerOne(): void { container("unpause", "countyflow-ai-worker-1-1"); }
