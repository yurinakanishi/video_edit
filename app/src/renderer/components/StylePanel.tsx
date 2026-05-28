import {
	GLOSSARY_ADD_TERM_EVENT,
	GLOSSARY_LOAD_CANDIDATES_EVENT,
	RUN_REFRESH_PROMPT_EVENT,
	SUBTITLE_MODE_CHANGE_EVENT,
} from "../events.js";
import { type StyleSettings, useAppStore } from "../store/app-store.js";
import { GlossaryList } from "./GlossaryList.js";

const SUBTITLE_MODES = [
	{ mode: "full", label: "Full" },
	{ mode: "punchline", label: "Catchy" },
	{ mode: "none", label: "None" },
] as const;

type PanelProps = {
	readonly hidden?: boolean;
};

function dispatchSubtitleModeChange(mode: string) {
	document.dispatchEvent(new CustomEvent(SUBTITLE_MODE_CHANGE_EVENT, { detail: { mode } }));
}

function dispatchStyleAction(eventName: string) {
	document.dispatchEvent(new CustomEvent(eventName));
}

export function StylePanel({ hidden = false }: PanelProps) {
	const currentSubtitleMode = useAppStore((appState) => appState.subtitleMode);
	const analysisTitleText = useAppStore((appState) => appState.analysisTitleText);
	const punchlineText = useAppStore((appState) => appState.punchlineText);
	const setPunchlineText = useAppStore((appState) => appState.setPunchlineText);
	const glossaryDraft = useAppStore((appState) => appState.glossaryDraft);
	const setGlossaryDraft = useAppStore((appState) => appState.setGlossaryDraft);
	const styleSettings = useAppStore((appState) => appState.styleSettings);
	const setStyleSettings = useAppStore((appState) => appState.setStyleSettings);
	const updateStyleSettings = (settings: Partial<StyleSettings>) => {
		setStyleSettings(settings);
		dispatchStyleAction(RUN_REFRESH_PROMPT_EVENT);
	};

	return (
		<div className="panel" data-panel="style" hidden={hidden}>
			<div className="panel-heading">
				<h3>字幕</h3>
				<span>subtitle and logo settings</span>
			</div>
			<fieldset className="segmented" aria-label="Subtitle mode">
				{SUBTITLE_MODES.map((subtitleMode) => (
					<button
						key={subtitleMode.mode}
						type="button"
						className={subtitleMode.mode === currentSubtitleMode ? "selected" : undefined}
						data-subtitle-mode={subtitleMode.mode}
						onClick={() => dispatchSubtitleModeChange(subtitleMode.mode)}
					>
						{subtitleMode.label}
					</button>
				))}
			</fieldset>
			<div className="field-stack">
				<label>
					Subtitle size
					<input
						id="subtitleSize"
						type="range"
						min="32"
						max="96"
						value={styleSettings.subtitleSize}
						onChange={(event) => updateStyleSettings({ subtitleSize: event.currentTarget.value })}
					/>
				</label>
				<label>
					Highlight color
					<input
						id="highlightColor"
						type="color"
						value={styleSettings.highlightColor}
						onChange={(event) => updateStyleSettings({ highlightColor: event.currentTarget.value })}
					/>
				</label>
				<label>
					Subtitle background
					<input
						id="boxOpacity"
						type="range"
						min="0"
						max="100"
						value={styleSettings.boxOpacity}
						onChange={(event) => updateStyleSettings({ boxOpacity: event.currentTarget.value })}
					/>
				</label>
				<label>
					Corner title
					<input id="titleText" value={analysisTitleText} readOnly />
				</label>
				<div className="two-col">
					<label>
						Title size
						<input
							id="titleSize"
							type="number"
							min="24"
							max="120"
							value={styleSettings.titleSize}
							onChange={(event) => updateStyleSettings({ titleSize: event.currentTarget.value })}
						/>
					</label>
					<label>
						Logo height
						<input
							id="logoHeight"
							type="number"
							min="20"
							max="160"
							value={styleSettings.logoHeight}
							onChange={(event) => updateStyleSettings({ logoHeight: event.currentTarget.value })}
						/>
					</label>
				</div>
				<label>
					Catchy subtitle lines
					<textarea
						id="punchlineText"
						spellCheck="false"
						value={punchlineText}
						onChange={(event) => {
							setPunchlineText(event.currentTarget.value);
							dispatchStyleAction(RUN_REFRESH_PROMPT_EVENT);
						}}
					></textarea>
				</label>
				<div className="glossary-editor">
					<div className="glossary-heading">
						<div>
							<strong>専門用語解説</strong>
							<span>字幕から候補を読み込み、表示する用語を調整</span>
						</div>
						<button
							type="button"
							id="loadGlossaryCandidates"
							onClick={() => dispatchStyleAction(GLOSSARY_LOAD_CANDIDATES_EVENT)}
						>
							候補を読み込み
						</button>
					</div>
					<label className="toggle-row">
						<input
							id="termExplanations"
							type="checkbox"
							checked={styleSettings.termExplanations}
							onChange={(event) => updateStyleSettings({ termExplanations: event.currentTarget.checked })}
						/>
						<span>専門用語解説を表示</span>
					</label>
					<GlossaryList />
					<div className="glossary-add-grid">
						<input
							id="glossaryLabel"
							placeholder="用語 例: EDM"
							value={glossaryDraft.label}
							onChange={(event) => {
								setGlossaryDraft({ label: event.currentTarget.value });
								dispatchStyleAction(RUN_REFRESH_PROMPT_EVENT);
							}}
						/>
						<input
							id="glossaryPatterns"
							placeholder="検出語 例: EDM,イーディーエム"
							value={glossaryDraft.patterns}
							onChange={(event) => {
								setGlossaryDraft({ patterns: event.currentTarget.value });
								dispatchStyleAction(RUN_REFRESH_PROMPT_EVENT);
							}}
						/>
						<textarea
							id="glossaryDescription"
							placeholder="短い解説"
							value={glossaryDraft.description}
							onChange={(event) => {
								setGlossaryDraft({ description: event.currentTarget.value });
								dispatchStyleAction(RUN_REFRESH_PROMPT_EVENT);
							}}
						></textarea>
						<button type="button" id="addGlossaryTerm" onClick={() => dispatchStyleAction(GLOSSARY_ADD_TERM_EVENT)}>
							追加
						</button>
					</div>
				</div>
			</div>
		</div>
	);
}
