// dsh-skills-claude — DSH plugin exposing bundled Claude Code skills.
//
// Reuses @deepseek-ai/dsh-skill-filesystem's bundled-skill mechanism
// (trustedHost root at BUNDLED_SKILL_RANK) so discovery, frontmatter parsing
// and watching behave exactly like the built-in skill roots.
//
// Loader row:
//   - insert:
//       - id: dsh-skills-claude
//         name: dsh-skills-claude

import { fileURLToPath } from "node:url";
import {
  apply as skillFilesystemApply,
} from "@deepseek-ai/dsh-skill-filesystem";

/** Cordis plugin name (matches the loader entry id). */
const name = "dsh-skills-claude";
/** Required service: the layered skill registry lives in the host composition. */
const inject = ["skills"];

/**
 * Register a bundled skill provider over this package's own `skills/` directory.
 * @param ctx - the mounting context (global layer when patched at profile root).
 * @param config - optional overrides; `providerName`, `includeDefaultRoots` and
 *   `bundledSkillDir` are pinned unless explicitly overridden.
 */
function apply(ctx, config = {}) {
  const bundledSkillDir = fileURLToPath(new URL("../skills/", import.meta.url));
  skillFilesystemApply(ctx, {
    providerName: "claude-skills",
    includeDefaultRoots: false,
    bundledSkillDir,
    ...config,
  });
}

export { apply, inject, name };
