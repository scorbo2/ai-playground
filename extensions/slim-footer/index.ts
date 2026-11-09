/**
 * slim-footer — replaces pi's built-in footer with a slimmer one.
 *
 *   ~/<path> (branch) • <session name>
 *   (provider) model-id • thinking                    23.4k/128k (18.3%) (auto)
 *
 * Deliberately drops the built-in's token stats (↑input ↓output R/W cache,
 * CH cache-hit rate) and $cost; keeps context usage vs. the limit (now in
 * tokens AND percent) plus the auto-compaction indicator.
 *
 * Implementation notes:
 * - Context numbers come from ctx.getContextUsage() — the exact same source
 *   the built-in footer uses. After compaction (until the next LLM response)
 *   the estimate is unknown and we render `?` the same way the built-in does.
 * - The auto-compaction flag is not exposed to extensions, so we read the
 *   merged settings (global + project, deep-merged, project wins) and apply
 *   `compaction.enabled ?? true` — the same rule AgentSession uses. File
 *   reads are mtime-cached so per-render cost stays a couple of stat calls.
 * - The provider is always shown (width permitting). pi's built-in footer
 *   gates it behind getAvailableProviderCount() > 1, which is never true for
 *   a single-provider models.json setup — see the note in renderFooter().
 * - The footer is reinstalled on every session_start: pi creates a fresh
 *   extension runner per session, so a footer closure holding a stale ctx
 *   would start throwing (its getters are guarded). setExtensionFooter()
 *   disposes the previous custom footer before installing, so this is safe.
 *
 * Toggle: /slim-footer (or /slim-footer on | /slim-footer off).
 */

import { readFileSync, statSync } from "node:fs";
import { homedir } from "node:os";
import { isAbsolute, join, relative, resolve, sep } from "node:path";
import type { ExtensionAPI, ExtensionContext, ReadonlyFooterDataProvider } from "@earendil-works/pi-coding-agent";
import { truncateToWidth, visibleWidth } from "@earendil-works/pi-tui";

type Json = Record<string, unknown>;

/** Structural slice of the pi theme we actually use (theme type is not public). */
type ThemeLike = {
	fg(color: string, text: string): string;
};

function isPlainObject(value: unknown): value is Json {
	return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** Mirrors pi's settings deep merge: nested objects merge recursively, override wins. */
function deepMerge(base: Json, overrides: Json): Json {
	const out: Json = { ...base };
	for (const [key, overrideValue] of Object.entries(overrides)) {
		const baseValue = base[key];
		out[key] =
			isPlainObject(baseValue) && isPlainObject(overrideValue)
				? deepMerge(baseValue, overrideValue)
				: overrideValue;
	}
	return out;
}

/** mtime-keyed cache so renders don't re-parse settings JSON on every redraw. */
const settingsCache = new Map<string, { mtimeMs: number; value: Json }>();

function readJsonFile(path: string): Json {
	try {
		const stat = statSync(path);
		const cached = settingsCache.get(path);
		if (cached && cached.mtimeMs === stat.mtimeMs) return cached.value;
		const value = JSON.parse(readFileSync(path, "utf8"));
		if (!isPlainObject(value)) return {};
		settingsCache.set(path, { mtimeMs: stat.mtimeMs, value });
		return value;
	} catch {
		// Missing or malformed settings files behave as empty.
		return {};
	}
}

/** Auto-compaction flag, same rule as AgentSession.autoCompactionEnabled. */
function autoCompactionEnabled(cwd: string): boolean {
	const agentDir = process.env.PI_CODING_AGENT_DIR || join(homedir(), ".pi", "agent");
	const merged = deepMerge(
		readJsonFile(join(agentDir, "settings.json")),
		readJsonFile(join(cwd, ".pi", "settings.json")),
	);
	const compaction = isPlainObject(merged.compaction) ? merged.compaction : null;
	// pi types this field `boolean | undefined`, but we read the raw
	// (unvalidated) settings file — so treat anything that isn't a real
	// boolean as "absent" and fall back to the schema default (true).
	const enabled = compaction?.enabled;
	return typeof enabled === "boolean" ? enabled : true;
}

/** Re-implementation of pi's built-in footer token formatter (not exported). */
function formatTokens(count: number): string {
	if (count < 1000) return count.toString();
	if (count < 10000) return `${(count / 1000).toFixed(1)}k`;
	if (count < 1000000) return `${Math.round(count / 1000)}k`;
	if (count < 10000000) return `${(count / 1000000).toFixed(1)}M`;
	return `${Math.round(count / 1000000)}M`;
}

/**
 * Used-tokens formatter, one decimal for the k range ("23.5k") — matches the
 * requested "23.4k/128k" display style. The limit stays in pi's native
 * integer-k style ("128k"), and the percent already carries sub-k precision.
 */
function formatUsedTokens(count: number): string {
	if (count < 1000) return count.toString();
	if (count < 1000000) return `${(count / 1000).toFixed(1)}k`;
	return `${(count / 1000000).toFixed(2)}M`;
}

/** Re-implementation of pi's built-in footer cwd formatter (not exported). */
function formatCwdForFooter(cwd: string, home: string): string {
	if (!home) return cwd;
	const resolvedCwd = resolve(cwd);
	const resolvedHome = resolve(home);
	const relativeToHome = relative(resolvedHome, resolvedCwd);
	const isInsideHome =
		relativeToHome === "" ||
		(relativeToHome !== ".." && !relativeToHome.startsWith(`..${sep}`) && !isAbsolute(relativeToHome));
	if (!isInsideHome) return cwd;
	return relativeToHome === "" ? "~" : `~${sep}${relativeToHome}`;
}

/** Re-implementation of pi's built-in status sanitizer (not exported). */
function sanitizeStatusText(text: string): string {
	return text.replace(/[\r\n\t]/g, " ").replace(/ +/g, " ").trim();
}

export default function (pi: ExtensionAPI) {
	let enabled = true;
	let currentCtx: ExtensionContext | null = null;
	/** Last good frame, served while a stale-ctx transition is in flight. */
	let lastLines: string[] = [];

	function renderFooter(
		width: number,
		theme: ThemeLike,
		footerData: ReadonlyFooterDataProvider,
		ctx: ExtensionContext,
	): string[] {
		const cwd = ctx.sessionManager.getCwd();
		const home = process.env.HOME || process.env.USERPROFILE || homedir();

		// Line 1: cwd (branch) • session name — same as the built-in footer.
		let pwd = formatCwdForFooter(cwd, home);
		const branch = footerData.getGitBranch();
		if (branch) pwd = `${pwd} (${branch})`;
		const sessionName = ctx.sessionManager.getSessionName();
		if (sessionName) pwd = `${pwd} • ${sessionName}`;

		// Line 2: model on the left, context-usage token stats on the right
		// (swapped from the built-in order). The token stats are the primary
		// info — kept whole, like the built-in's left side — so the model side
		// truncates when there isn't enough room.
		const minPadding = 2;

		// Left: model id, thinking level, provider — same content as the
		// built-in footer's right side.
		const model = ctx.model;
		const modelName = model?.id || "no-model";
		let modelSide = modelName;
		if (model?.reasoning) {
			const thinkingLevel = ctx.thinkingLevel || "off";
			modelSide = thinkingLevel === "off" ? `${modelName} • thinking off` : `${modelName} • ${thinkingLevel}`;
		}

		// Right: context usage. tokens/percent are null right after compaction
		// until the next LLM response — render `?` like the built-in.
		const usage = ctx.getContextUsage();
		const contextWindow = usage?.contextWindow ?? ctx.model?.contextWindow ?? 0;
		const autoIndicator = autoCompactionEnabled(cwd) ? " (auto)" : "";
		let percentValue = 0;
		let usageSide: string;
		if (usage?.tokens == null || usage.percent == null || contextWindow <= 0) {
			usageSide = `?/${formatTokens(contextWindow)}${autoIndicator}`;
		} else {
			percentValue = usage.percent;
			usageSide = `${formatUsedTokens(usage.tokens)}/${formatTokens(contextWindow)} (${percentValue.toFixed(1)}%)${autoIndicator}`;
		}
		// Same thresholds as the built-in footer: >90% error, >70% warning.
		if (percentValue > 90) usageSide = theme.fg("error", usageSide);
		else if (percentValue > 70) usageSide = theme.fg("warning", usageSide);
		const usageWidth = visibleWidth(usageSide);

		// Prepend the provider, with only the width budget as a veto.
		//
		// pi's built-in footer additionally requires getAvailableProviderCount()
		// > 1 ("if you only have one provider, you obviously know which one
		// you're on"). That count is the number of *distinct providers with
		// available models*, not the number configured in models.json — so with a
		// single-provider models.json (and no other provider holding credentials)
		// it is always 1 and the provider name would never render. We want it
		// regardless, so the heuristic is deliberately not copied here.
		if (model) {
			const withProvider = `(${model.provider}) ${modelSide}`;
			if (visibleWidth(withProvider) + minPadding + usageWidth <= width) modelSide = withProvider;
		}

		// Layout: model + stats with >= 2 spaces between; keep the token stats
		// whole and truncate the model side to fit (see note above).
		const modelWidth = visibleWidth(modelSide);
		let leftPart: string;
		let rightPart: string;
		let padLen: number;
		if (modelWidth + minPadding + usageWidth <= width) {
			// Both fit — pad the model side so the stats hug the right edge.
			leftPart = modelSide;
			rightPart = usageSide;
			padLen = width - modelWidth - usageWidth;
		} else if (width - usageWidth - minPadding > 0) {
			// Tight — truncate the model side to keep the full token stats.
			leftPart = truncateToWidth(modelSide, width - usageWidth - minPadding, "");
			rightPart = usageSide;
			padLen = Math.max(0, width - visibleWidth(leftPart) - usageWidth);
		} else {
			// No room for the model at all — token stats only.
			leftPart = "";
			rightPart = truncateToWidth(usageSide, width, "");
			padLen = 0;
		}

		const lines: string[] = [
			truncateToWidth(theme.fg("dim", pwd), width, theme.fg("dim", "...")),
			// Dim each segment separately rather than wrapping the whole line:
			// a truncated leftPart and the colored rightPart each carry a
			// trailing ANSI reset that would otherwise leak into the next
			// segment and drop its dim.
			theme.fg("dim", leftPart) + theme.fg("dim", " ".repeat(padLen)) + theme.fg("dim", rightPart),
		];

		// Line 3 (optional): extension statuses, sorted, single line.
		const statuses = footerData.getExtensionStatuses();
		if (statuses.size > 0) {
			const statusLine = Array.from(statuses.entries())
				.sort(([a], [b]) => a.localeCompare(b))
				.map(([, text]) => sanitizeStatusText(text))
				.join(" ");
			lines.push(truncateToWidth(statusLine, width, theme.fg("dim", "...")));
		}

		return lines;
	}

	function installFooter(ctx: ExtensionContext) {
		currentCtx = ctx;
		lastLines = [];
		ctx.ui.setFooter((tui, theme, footerData) => {
			// Re-render when the git branch changes (the TUI doesn't know about it).
			const unsubBranch = footerData.onBranchChange(() => tui.requestRender());
			return {
				dispose: unsubBranch,
				invalidate() {},
				render(width: number): string[] {
					// pi builds a fresh extension runner per session, so a captured
					// ctx goes stale right after a session switch (guarded getters
					// throw). The next session_start reinstalls with a fresh ctx;
					// keep showing the last good frame until then.
					if (!currentCtx) return lastLines;
					try {
						return lastLines = renderFooter(width, theme, footerData, currentCtx);
					} catch {
						return lastLines;
					}
				},
			};
		});
	}

	// (Re)install on every session start — new, resumed, switched, or reloaded.
	pi.on("session_start", (_event, ctx) => {
		if (enabled) installFooter(ctx);
		else ctx.ui.setFooter(undefined);
	});

	pi.registerCommand("slim-footer", {
		description: "Toggle this slim footer (usage: /slim-footer [on|off])",
		handler: async (args: string, ctx) => {
			const flag = args.trim().toLowerCase();
			enabled = flag === "off" ? false : flag === "on" ? true : !enabled;
			if (enabled) installFooter(ctx);
			else ctx.ui.setFooter(undefined);
			ctx.ui.notify(`slim-footer ${enabled ? "enabled" : "disabled"}`, "info");
		},
	});
}
