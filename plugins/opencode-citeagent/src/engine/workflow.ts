import { mkdir, readFile, readdir, rename, unlink, writeFile } from "fs/promises";
import path from "path";

type Stage = "research" | "outline" | "draft" | "review";

interface WorkflowState {
  workflow_id: string;
  topic: string;
  stage: Stage;
  evidence_count: number;
  created_at: string;
  saved_at: number;
}

const ttlMs = 60 * 60 * 1000;
const stages: Stage[] = ["research", "outline", "draft", "review"];

/**
 * Backend-owned checkpoints. Hosts may write prose, but cannot advance past
 * evidence retrieval without an explicit user decision.
 */
export class ResearchWorkflow {
  private readonly directory: string;
  private writes: Promise<void> = Promise.resolve();

  constructor(stateRoot: string) {
    this.directory = path.join(stateRoot, "workflows");
  }

  async start(topic: string, evidenceCount: number) {
    return this.serial(async () => {
      if (!topic.trim()) throw new Error("topic is required");
      if (!evidenceCount) return this.error("NO_VERIFIED_EVIDENCE", "No scoped corpus evidence was found.", "Ingest or approve sources, then search again.");
      const workflow: WorkflowState = { workflow_id: crypto.randomUUID().slice(0, 8), topic: topic.trim(), stage: "research", evidence_count: evidenceCount, created_at: new Date().toISOString(), saved_at: Date.now() };
      await this.save(workflow);
      return this.checkpoint(workflow);
    });
  }

  async resume(workflowId: string, choice: "proceed" | "refine" | "abort" = "proceed") {
    return this.serial(async () => {
      const workflow = await this.load(workflowId);
      if (choice === "abort") {
        await unlink(this.file(workflowId));
        return { status: "aborted", workflow_id: workflowId };
      }
      if (choice === "refine") return this.checkpoint(workflow);
      const next = stages[stages.indexOf(workflow.stage) + 1];
      if (!next) {
        await unlink(this.file(workflowId));
        return { status: "ok", workflow_id: workflowId, topic: workflow.topic, evidence_count: workflow.evidence_count };
      }
      workflow.stage = next;
      workflow.saved_at = Date.now();
      await this.save(workflow);
      return this.checkpoint(workflow);
    });
  }

  async status() {
    try {
      const ids = (await readdir(this.directory)).filter((name) => name.endsWith(".json"));
      return { active_workflow_count: ids.length };
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === "ENOENT") return { active_workflow_count: 0 };
      throw error;
    }
  }

  private checkpoint(workflow: WorkflowState) {
    const questions: Record<Stage, string> = {
      research: "Review the verified evidence before outlining?",
      outline: "Review the outline before drafting?",
      draft: "Review the draft and its citations before final review?",
      review: "Review the publication checks?",
    };
    return {
      status: "needs_checkpoint",
      workflow_id: workflow.workflow_id,
      stage: workflow.stage,
      topic: workflow.topic,
      evidence_count: workflow.evidence_count,
      question: questions[workflow.stage],
      options: ["proceed", "refine", "abort"],
    };
  }

  private error(error_code: string, message: string, next_action: string) {
    return { status: "error", error_code, message, next_action };
  }

  private file(id: string) {
    if (!/^[a-f0-9-]{8,36}$/i.test(id)) throw new Error("workflow_id is invalid");
    return path.join(this.directory, `${id}.json`);
  }

  private async load(id: string): Promise<WorkflowState> {
    try {
      const workflow = JSON.parse(await readFile(this.file(id), "utf8")) as WorkflowState;
      if (Date.now() - workflow.saved_at > ttlMs) {
        await unlink(this.file(id));
        throw new Error(`Workflow ${id} expired`);
      }
      return workflow;
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === "ENOENT") throw new Error(`Workflow ${id} not found`);
      throw error;
    }
  }

  private async save(workflow: WorkflowState) {
    await mkdir(this.directory, { recursive: true });
    const file = this.file(workflow.workflow_id);
    const temporary = `${file}.tmp`;
    await writeFile(temporary, `${JSON.stringify(workflow, null, 2)}\n`, "utf8");
    await rename(temporary, file);
  }

  private serial<T>(operation: () => Promise<T>): Promise<T> {
    const result = this.writes.then(operation);
    this.writes = result.then(() => undefined, () => undefined);
    return result;
  }
}
