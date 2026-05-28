import { localizePlainText, t } from "../i18n.js";
import { useAppStore } from "../store/app-store.js";
import type { AnalysisResult } from "../types.js";

const ANALYSIS_LABEL_KEYS: Record<string, string> = {
	ingest: "analysis.materialClassification",
	"auto-sync-dropped": "analysis.syncCamerasAudio",
	"transcribe-dropped": "analysis.transcription",
	"compare-transcripts": "analysis.transcriptComparison",
	"text-overlays": "analysis.subtitleUi",
	"analyze-person-edit-metadata": "analysis.personOpenCv",
	"analyze-blocking": "analysis.blockingOpenCv",
	"analyze-reference-video": "analysis.referenceVideo",
};

function analysisLabel(item: AnalysisResult) {
	const labelKey = ANALYSIS_LABEL_KEYS[item.key];
	return labelKey ? t(labelKey) : localizePlainText(item.label || item.key);
}

function analysisStatusLabel(status: string) {
	if (status === "done") {
		return t("analysis.statusDone");
	}
	if (status === "error") {
		return t("analysis.statusError");
	}
	return t("analysis.statusRunning");
}

function analysisStatusClass(status: string) {
	if (status === "error") {
		return "error";
	}
	if (status === "done") {
		return "done";
	}
	return "";
}

export function AnalysisResultsList() {
	const language = useAppStore((appState) => appState.language);
	const analysisResults = useAppStore((appState) => appState.analysisResults);

	if (!analysisResults.length) {
		return (
			<div id="analysisResultList" className="analysis-result-list" data-locale={language}>
				{t("materials.analysisEmpty")}
			</div>
		);
	}

	return (
		<div id="analysisResultList" className="analysis-result-list" data-locale={language}>
			{analysisResults.map((item) => (
				<div key={item.key} className={`analysis-result-row ${analysisStatusClass(item.status)}`.trim()}>
					<strong>{analysisLabel(item)}</strong>
					<span title={item.path || item.detail}>{localizePlainText(item.detail)}</span>
					<span className="status">{analysisStatusLabel(item.status)}</span>
				</div>
			))}
		</div>
	);
}
