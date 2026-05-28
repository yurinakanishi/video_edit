import { GLOSSARY_TERM_CHANGE_EVENT, GLOSSARY_TERM_REMOVE_EVENT } from "../events.js";
import { t } from "../i18n.js";
import { useAppStore } from "../store/app-store.js";
import type { GlossaryTerm } from "../types.js";

const glossaryTermKeys = new WeakMap<GlossaryTerm, string>();
let glossaryTermKeyCounter = 0;

function termKey(term: GlossaryTerm) {
	let key = glossaryTermKeys.get(term);
	if (!key) {
		glossaryTermKeyCounter += 1;
		key = `glossary-term-${glossaryTermKeyCounter}`;
		glossaryTermKeys.set(term, key);
	}
	return key;
}

function dispatchGlossaryChange(index: number, field: keyof GlossaryTerm, value: string | boolean) {
	document.dispatchEvent(new CustomEvent(GLOSSARY_TERM_CHANGE_EVENT, { detail: { index, field, value } }));
}

function dispatchGlossaryRemove(index: number) {
	document.dispatchEvent(new CustomEvent(GLOSSARY_TERM_REMOVE_EVENT, { detail: { index } }));
}

export function GlossaryList() {
	const language = useAppStore((store) => store.language);
	const glossaryTerms = useAppStore((store) => store.glossaryTerms);

	if (!glossaryTerms.length) {
		return (
			<div id="glossaryList" className="glossary-list" data-locale={language}>
				{t("glossary.notLoaded")}
			</div>
		);
	}

	return (
		<div id="glossaryList" className="glossary-list" data-locale={language}>
			{glossaryTerms.map((term, index) => (
				<div className="glossary-row" key={termKey(term)}>
					<input
						type="checkbox"
						checked={term.enabled}
						aria-label={t("glossary.show")}
						onChange={(event) => dispatchGlossaryChange(index, "enabled", event.currentTarget.checked)}
					/>
					<input
						value={term.label}
						aria-label={t("glossary.termLabel")}
						onChange={(event) => dispatchGlossaryChange(index, "label", event.currentTarget.value)}
					/>
					<input
						value={term.patterns}
						aria-label={t("glossary.termPatterns")}
						onChange={(event) => dispatchGlossaryChange(index, "patterns", event.currentTarget.value)}
					/>
					<input
						value={term.description}
						aria-label={t("glossary.termDescription")}
						onChange={(event) => dispatchGlossaryChange(index, "description", event.currentTarget.value)}
					/>
					<button type="button" title={t("action.remove")} onClick={() => dispatchGlossaryRemove(index)}>
						×
					</button>
				</div>
			))}
		</div>
	);
}
