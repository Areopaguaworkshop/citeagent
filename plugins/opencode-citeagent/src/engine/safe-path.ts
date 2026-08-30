import path from "path";

export function safePath(root: string, ...parts: string[]): string {
  const base = path.resolve(root); // nosemgrep: root is trusted and containment is enforced below
  const candidate = path.resolve(base, ...parts); // nosemgrep: resolved path is rejected unless contained
  if (candidate === base || !candidate.startsWith(base + path.sep)) {
    throw new Error("Path escapes its storage directory");
  }
  return candidate;
}
