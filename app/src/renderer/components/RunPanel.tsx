import { useEffect, useRef } from "react";
import {
	CODEX_MODELS_REFRESH_EVENT,
	CODEX_STOP_EVENT,
	RUN_REFRESH_COMMAND_EVENT,
	RUN_REFRESH_PROMPT_EVENT,
} from "../events.js";
import { t } from "../i18n.js";
import { useAppStore } from "../store/app-store.js";
import { CodexModelControls } from "./CodexModelControls.js";
import { RunChecklist } from "./RunChecklist.js";

type PanelProps = {
	readonly hidden?: boolean;
};

function dispatchRunAction(eventName: string) {
	document.dispatchEvent(new CustomEvent(eventName));
}

function EventLog() {
	const eventLogLines = useAppStore((appState) => appState.eventLogLines);
	const eventLogRef = useRef<HTMLPreElement | null>(null);
	const text = eventLogLines.length ? `${eventLogLines.join("\n")}\n` : "";

	useEffect(() => {
		const element = eventLogRef.current;
		if (element) {
			element.scrollTop = element.scrollHeight;
		}
	});

	return (
		<pre id="eventLog" ref={eventLogRef}>
			{text}
		</pre>
	);
}

export function RunPanel({ hidden = false }: PanelProps) {
	const language = useAppStore((appState) => appState.language);
	const appLocked = useAppStore((appState) => appState.appLocked);
	const codexModelsLoading = useAppStore((appState) => appState.codexModelsLoading);
	const codexTurnRunning = useAppStore((appState) => appState.codexTurnRunning);
	const codexInterruptRequested = useAppStore((appState) => appState.codexInterruptRequested);
	const commandPreviewText = useAppStore((appState) => appState.commandPreviewText);
	const promptPreviewText = useAppStore((appState) => appState.promptPreviewText);
	const stopButtonText = codexInterruptRequested ? t("action.stoppingCodex") : t("action.stopCodex");

	return (
		<>
			<div className="panel wide" data-panel="run" data-locale={language} hidden={hidden}>
				<div className="panel-heading">
					<h3>AI editing request</h3>
					<span>Review before running</span>
				</div>
				<div className="codex-options">
					<CodexModelControls />
					<button
						type="button"
						id="refreshCodexModels"
						disabled={appLocked || codexModelsLoading}
						onClick={() => dispatchRunAction(CODEX_MODELS_REFRESH_EVENT)}
					>
						Refresh models
					</button>
				</div>
				<div className="run-summary">
					<strong>実行前チェック</strong>
					<RunChecklist />
				</div>
				<details className="advanced-settings codex-details">
					<summary>Review request details</summary>
					<label className="command-preview-label">
						Execution details
						<textarea id="commandPreview" spellCheck="false" readOnly value={commandPreviewText}></textarea>
					</label>
					<label>
						Request text sent to AI
						<textarea id="promptPreview" spellCheck="false" readOnly value={promptPreviewText}></textarea>
					</label>
					<div className="run-actions">
						<button type="button" id="refreshCommand" onClick={() => dispatchRunAction(RUN_REFRESH_COMMAND_EVENT)}>
							Refresh execution details
						</button>
						<button type="button" id="refreshPrompt" onClick={() => dispatchRunAction(RUN_REFRESH_PROMPT_EVENT)}>
							Refresh request text
						</button>
						<button
							type="button"
							className="danger-button"
							id="interrupt"
							hidden={!codexTurnRunning}
							disabled={appLocked || !codexTurnRunning || codexInterruptRequested}
							onClick={() => dispatchRunAction(CODEX_STOP_EVENT)}
						>
							{stopButtonText}
						</button>
					</div>
				</details>
			</div>

			<div className="panel wide log-panel" data-panel="run" hidden={hidden}>
				<div className="panel-heading">
					<h3>Progress</h3>
					<span>Run log</span>
				</div>
				<EventLog />
			</div>
		</>
	);
}
