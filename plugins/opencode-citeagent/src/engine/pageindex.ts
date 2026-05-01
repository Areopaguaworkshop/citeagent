import fs from "fs";
import path from "path";
import type { PageIndexTree } from "./types.js";

export class PageIndexEngine {
  private corpusRoot: string;

  constructor(corpusRoot: string) {
    this.corpusRoot = corpusRoot;
  }

  async loadTree(sourceId: string, depth?: number): Promise<PageIndexTree | { error: string }> {
    const indexPath = path.join(
      this.corpusRoot,
      ".citeindex",
      "documents",
      "structured",
      `${sourceId}.citeindex.json`,
    );

    if (!fs.existsSync(indexPath)) {
      return { error: `PageIndex not found for ${sourceId}` };
    }

    try {
      const tree = JSON.parse(fs.readFileSync(indexPath, "utf-8")) as PageIndexTree;

      if (depth !== undefined && tree.root) {
        tree.root = this.pruneTree(tree.root, depth);
      }

      return tree;
    } catch {
      return { error: `Failed to parse PageIndex for ${sourceId}` };
    }
  }

  async traverseTree(sourceId: string, treePath?: string): Promise<{ nodes: Record<string, unknown>[]; path: string }> {
    const tree = await this.loadTree(sourceId);
    if ("error" in tree) {
      return { nodes: [], path: treePath || "/" };
    }

    if (!treePath || treePath === "/") {
      const allNodes = tree.levels && Object.values(tree.levels).flat();
      return { nodes: (allNodes || []) as Record<string, unknown>[], path: treePath || "/" };
    }

    const segments = treePath.split("/").filter(Boolean);
    let current = tree.root;
    for (const seg of segments) {
      if (!current?.children) {
        return { nodes: [], path: treePath };
      }
      const child = current.children.find((c) => c.id === seg || c.label === seg || c.heading === seg);
      if (!child) {
        return { nodes: [], path: treePath };
      }
      current = child;
    }

    return {
      nodes: current?.children ? current.children as unknown as Record<string, unknown>[] : [{ ...current }],
      path: treePath,
    };
  }

  private pruneTree(node: any, maxDepth: number, currentDepth: number = 0): any {
    if (currentDepth >= maxDepth) {
      const { children, ...rest } = node;
      return rest;
    }
    if (node.children) {
      return {
        ...node,
        children: node.children.map((c: any) => this.pruneTree(c, maxDepth, currentDepth + 1)),
      };
    }
    return node;
  }
}