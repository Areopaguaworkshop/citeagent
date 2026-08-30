import { mkdir, readFile, rename, writeFile } from "fs/promises";
import path from "path";

interface SessionRecord {
  session_id: string;
  topics: string[];
  source_ids: string[];
  open_questions: string[];
  recorded_at: string;
}

/** Local, opt-in research metadata; source text is intentionally never copied here. */
export class ResearchState {
  private readonly file: string;
  private writes: Promise<void> = Promise.resolve();

  constructor(stateRoot: string) {
    this.file = path.join(stateRoot, "research-state.json");
  }

  async record(session_id: string, topics: string[] = [], source_ids: string[] = [], open_questions: string[] = []) {
    return this.serial(async () => {
      if (!session_id.trim()) throw new Error("session_id is required");
      const records = await this.records();
      const record: SessionRecord = { session_id, topics, source_ids, open_questions, recorded_at: new Date().toISOString() };
      await this.write([...records.filter((item) => item.session_id !== session_id), record].slice(-20));
      return record;
    });
  }

  async wakeUp(max_records = 3) {
    const records = (await this.records()).slice(-max_records).reverse();
    return {
      status: "ok",
      recent_sessions: records.map(({ session_id, topics, source_ids, open_questions, recorded_at }) => ({ session_id, topics, source_ids, open_questions, recorded_at })),
    };
  }

  async snapshot() {
    const records = await this.records();
    return { session_count: records.length, latest_session: records.at(-1)?.session_id ?? null };
  }

  private async records(): Promise<SessionRecord[]> {
    try {
      return JSON.parse(await readFile(this.file, "utf8")) as SessionRecord[];
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === "ENOENT") return [];
      throw error;
    }
  }

  private async write(records: SessionRecord[]) {
    await mkdir(path.dirname(this.file), { recursive: true });
    const temporary = `${this.file}.tmp`;
    await writeFile(temporary, `${JSON.stringify(records, null, 2)}\n`, "utf8");
    await rename(temporary, this.file);
  }

  private serial<T>(operation: () => Promise<T>): Promise<T> {
    const result = this.writes.then(operation);
    this.writes = result.then(() => undefined, () => undefined);
    return result;
  }
}
