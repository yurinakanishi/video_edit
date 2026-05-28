import { codexModelValue } from "../codex-models.js";
import { CODEX_MODEL_CHANGE_EVENT } from "../events.js";
import { t } from "../i18n.js";
import { useAppStore } from "../store/app-store.js";
import type { CodexModel } from "../types.js";

function codexModelLabel(model: CodexModel, value: string) {
	if (model.isDefault) {
		return `${model.displayName || value} (${t("codex.modelDefaultSuffix")})`;
	}
	return model.displayName || value;
}

function dispatchCodexModelChange(model: string) {
	document.dispatchEvent(new CustomEvent(CODEX_MODEL_CHANGE_EVENT, { detail: { model } }));
}

export function CodexModelControls() {
	const language = useAppStore((store) => store.language);
	const codexModels = useAppStore((store) => store.codexModels);
	const codexModel = useAppStore((store) => store.codexModel);
	const codexModelStatusKey = useAppStore((store) => store.codexModelStatusKey);
	const codexModelStatusValues = useAppStore((store) => store.codexModelStatusValues);
	const seen = new Set([""]);
	const selectedUnavailable = Boolean(codexModel && codexModels.length);
	const hasSelectedModel =
		!codexModel || codexModels.some((model) => codexModelValue(model) === codexModel) || !codexModels.length;
	const selectedValue = selectedUnavailable && !hasSelectedModel ? "" : codexModel;

	return (
		<>
			<label data-locale={language}>
				AI model
				<select
					id="modelName"
					value={selectedValue}
					onChange={(event) => dispatchCodexModelChange(event.currentTarget.value)}
				>
					<option value="">{t("codex.modelDefault")}</option>
					{codexModels.map((model) => {
						const value = codexModelValue(model);
						if (!value || seen.has(value)) {
							return null;
						}
						seen.add(value);
						return (
							<option key={value} value={value} title={value}>
								{codexModelLabel(model, value)}
							</option>
						);
					})}
					{codexModel && !codexModels.length ? (
						<option value={codexModel} title={codexModel}>
							{codexModel} ({t("codex.modelCustomSuffix")})
						</option>
					) : null}
				</select>
			</label>
			<span id="codexModelStatus" className="field-status" data-locale={language}>
				{t(codexModelStatusKey, codexModelStatusValues)}
			</span>
		</>
	);
}
