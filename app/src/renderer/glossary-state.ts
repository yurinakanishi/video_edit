import { state } from "./state.js";
import { patchAppState } from "./store/app-store.js";
import type { GlossaryTerm } from "./types.js";

type GlossaryStateControllerOptions = {
	readonly refreshPrompt: () => void;
};

export function createGlossaryStateController({ refreshPrompt }: GlossaryStateControllerOptions) {
	function glossaryTerms(): GlossaryTerm[] {
		return state.glossaryTerms as GlossaryTerm[];
	}

	function syncGlossaryStore() {
		patchAppState({ glossaryTerms: [...glossaryTerms()] });
	}

	function normalizeGlossaryTerm(term: Partial<GlossaryTerm>): GlossaryTerm | null {
		const label = String(term.label || "").trim();
		const description = String(term.description || "").trim();
		const patterns = String(term.patterns || label).trim();
		if (!label || !description || !patterns) {
			return null;
		}
		return {
			label,
			description,
			patterns,
			enabled: term.enabled !== false,
		};
	}

	function setGlossaryTerms(terms: Partial<GlossaryTerm>[]) {
		const seen = new Set<string>();
		const normalized: GlossaryTerm[] = [];
		for (const term of terms) {
			const item = normalizeGlossaryTerm(term);
			if (!item) {
				continue;
			}
			const key = item.label.toLowerCase();
			if (seen.has(key)) {
				continue;
			}
			seen.add(key);
			normalized.push(item);
		}
		state.glossaryTerms = normalized;
		renderGlossaryList();
		refreshPrompt();
	}

	function renderGlossaryList() {
		syncGlossaryStore();
	}

	function handleGlossaryTermChange(event: Event) {
		const detail = (event as CustomEvent).detail || {};
		const index = Number(detail.index);
		const field = String(detail.field || "");
		const term = glossaryTerms()[index];
		if (!term || !["enabled", "label", "patterns", "description"].includes(field)) {
			return;
		}
		if (field === "enabled") {
			term.enabled = Boolean(detail.value);
		} else if (field === "label") {
			term.label = String(detail.value || "");
			if (!term.patterns) {
				term.patterns = term.label;
			}
		} else if (field === "patterns") {
			term.patterns = String(detail.value || "");
		} else {
			term.description = String(detail.value || "");
		}
		syncGlossaryStore();
		refreshPrompt();
	}

	function handleGlossaryTermRemove(event: Event) {
		const index = Number((event as CustomEvent).detail?.index);
		if (!Number.isInteger(index) || index < 0) {
			return;
		}
		state.glossaryTerms = glossaryTerms().filter((_, itemIndex) => itemIndex !== index);
		renderGlossaryList();
		refreshPrompt();
	}

	function termsFromGlossaryManifest(manifest: any[]): GlossaryTerm[] {
		const terms: GlossaryTerm[] = [];
		for (const item of manifest || []) {
			for (const term of item.terms || []) {
				terms.push({
					label: String(term.label || ""),
					description: String(term.description || ""),
					patterns: String(term.label || ""),
					enabled: true,
				});
			}
		}
		return terms;
	}

	return {
		glossaryTerms,
		handleGlossaryTermChange,
		handleGlossaryTermRemove,
		normalizeGlossaryTerm,
		renderGlossaryList,
		setGlossaryTerms,
		termsFromGlossaryManifest,
	};
}
