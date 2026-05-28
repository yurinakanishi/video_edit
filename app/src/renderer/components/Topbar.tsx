import { CODEX_SEND_REQUEST_EVENT, CODEX_STOP_EVENT, OUTPUT_OPEN_EVENT, RUN_PRESET_EVENT } from "../events.js";
import { t } from "../i18n.js";
import { useAppStore } from "../store/app-store.js";

function dispatchTopbarAction(eventName: string) {
	document.dispatchEvent(new CustomEvent(eventName));
}

export function Topbar() {
	const language = useAppStore((appState) => appState.language);
	const appLocked = useAppStore((appState) => appState.appLocked);
	const directRunRunning = useAppStore((appState) => appState.directRunRunning);
	const directRunLabel = useAppStore((appState) => appState.directRunLabel);
	const codexTurnRunning = useAppStore((appState) => appState.codexTurnRunning);
	const codexInterruptRequested = useAppStore((appState) => appState.codexInterruptRequested);
	const runButtonText = directRunRunning
		? t("format.runningButton", { label: directRunLabel || t("runLabel.run") })
		: t("action.runPresetScript");
	const stopButtonText = codexInterruptRequested ? t("action.stoppingCodex") : t("action.stopCodex");

	return (
		<section className="topbar" data-locale={language}>
			<div>
				<h2>{t("topbar.title")}</h2>
				<p>{t("topbar.description")}</p>
			</div>
			<div className="topbar-actions">
				<button type="button" id="openOutput" onClick={() => dispatchTopbarAction(OUTPUT_OPEN_EVENT)}>
					{t("action.openSelectedOutput")}
				</button>
				<button
					type="button"
					id="runPreset"
					disabled={directRunRunning || appLocked}
					onClick={() => dispatchTopbarAction(RUN_PRESET_EVENT)}
				>
					{runButtonText}
				</button>
				<button
					type="button"
					className="primary-button"
					id="sendRequest"
					hidden={codexTurnRunning}
					disabled={directRunRunning || appLocked}
					onClick={() => dispatchTopbarAction(CODEX_SEND_REQUEST_EVENT)}
				>
					{t("action.runWithCodex")}
				</button>
				<button
					type="button"
					className="danger-button"
					id="stopCodexTurn"
					hidden={!codexTurnRunning}
					disabled={appLocked || !codexTurnRunning || codexInterruptRequested}
					onClick={() => dispatchTopbarAction(CODEX_STOP_EVENT)}
				>
					{stopButtonText}
				</button>
			</div>
		</section>
	);
}
