import { RUN_REFRESH_PROMPT_EVENT, SYNC_REPORT_REFRESH_EVENT, TOOL_PICK_EVENT } from "../events.js";
import { THUMBNAIL_COLOR_OPTIONS, THUMBNAIL_MODES, WORKFLOW_ACTIONS } from "../form-options.js";
import {
	type AnalysisSettings,
	type SubtitleReviewSettings,
	type SubtitleSpeakerSettings,
	type ThumbnailSettings,
	useAppStore,
} from "../store/app-store.js";
import { WorkflowInputVideoPreview } from "./PathPreviews.js";
import { SelectOptions } from "./SelectOptions.js";
import { SyncReportList } from "./SyncReportList.js";

type PanelProps = {
	readonly hidden?: boolean;
};

function dispatchWorkflowAction(eventName: string) {
	document.dispatchEvent(new CustomEvent(eventName));
}

function dispatchWorkflowSettingsChange() {
	dispatchWorkflowAction(RUN_REFRESH_PROMPT_EVENT);
}

function dispatchToolPick(id: string) {
	document.dispatchEvent(new CustomEvent(TOOL_PICK_EVENT, { detail: { id } }));
}

export function WorkflowPanel({ hidden = false }: PanelProps) {
	const inputVideoPath = useAppStore((store) => store.inputVideoPath);
	const workflowSettings = useAppStore((store) => store.workflowSettings);
	const setWorkflowSettings = useAppStore((store) => store.setWorkflowSettings);
	const toolPaths = useAppStore((store) => store.toolPaths);
	const setToolPaths = useAppStore((store) => store.setToolPaths);
	const analysisSettings = useAppStore((store) => store.analysisSettings);
	const setAnalysisSettings = useAppStore((store) => store.setAnalysisSettings);
	const thumbnailSettings = useAppStore((store) => store.thumbnailSettings);
	const setThumbnailSettings = useAppStore((store) => store.setThumbnailSettings);
	const subtitleReviewSettings = useAppStore((store) => store.subtitleReviewSettings);
	const setSubtitleReviewSettings = useAppStore((store) => store.setSubtitleReviewSettings);
	const subtitleSpeakerSettings = useAppStore((store) => store.subtitleSpeakerSettings);
	const setSubtitleSpeakerSettings = useAppStore((store) => store.setSubtitleSpeakerSettings);
	const updateAnalysisSettings = (settings: Partial<AnalysisSettings>) => {
		setAnalysisSettings(settings);
		dispatchWorkflowSettingsChange();
	};
	const updateThumbnailSettings = (settings: Partial<ThumbnailSettings>) => {
		setThumbnailSettings(settings);
		dispatchWorkflowSettingsChange();
	};
	const updateSubtitleReviewSettings = (settings: Partial<SubtitleReviewSettings>) => {
		setSubtitleReviewSettings(settings);
		dispatchWorkflowSettingsChange();
	};
	const updateSubtitleSpeakerSettings = (settings: Partial<SubtitleSpeakerSettings>) => {
		setSubtitleSpeakerSettings(settings);
		dispatchWorkflowSettingsChange();
	};

	return (
		<div className="panel wide" data-panel="workflow" hidden={hidden}>
			<div className="panel-heading">
				<h3>工程</h3>
				<span>Choose what to run</span>
			</div>
			<div className="workflow-grid">
				<label>
					Step to run
					<select
						id="workflowAction"
						value={workflowSettings.workflowAction}
						onChange={(event) => {
							setWorkflowSettings({ workflowAction: event.currentTarget.value });
							dispatchWorkflowSettingsChange();
						}}
					>
						<SelectOptions options={WORKFLOW_ACTIONS} />
					</select>
				</label>
				<details className="advanced-settings">
					<summary>Advanced settings</summary>
					<div className="advanced-settings-grid">
						<label>
							Render method
							<select
								id="renderScript"
								value={workflowSettings.renderScript}
								onChange={(event) => {
									setWorkflowSettings({ renderScript: event.currentTarget.value });
									dispatchWorkflowSettingsChange();
								}}
							>
								<option value="render_multicam.py">Multicam render from selected media</option>
								<option value="render_app_interview.py">Compatibility renderer alias</option>
							</select>
						</label>
						<label>
							Transcription quality
							<input
								id="transcribeModel"
								value={analysisSettings.transcribeModel}
								onChange={(event) => updateAnalysisSettings({ transcribeModel: event.currentTarget.value })}
							/>
						</label>
						<div className="three-col">
							<label>
								Language
								<input
									id="transcribeLanguage"
									value={analysisSettings.transcribeLanguage}
									onChange={(event) => updateAnalysisSettings({ transcribeLanguage: event.currentTarget.value })}
								/>
							</label>
							<label>
								Accuracy
								<input
									id="transcribeBeamSize"
									type="number"
									min="1"
									max="10"
									step="1"
									value={analysisSettings.transcribeBeamSize}
									onChange={(event) => updateAnalysisSettings({ transcribeBeamSize: event.currentTarget.value })}
								/>
							</label>
							<label>
								Wording variation
								<input
									id="transcribeTemperature"
									type="number"
									min="0"
									max="1"
									step="0.1"
									value={analysisSettings.transcribeTemperature}
									onChange={(event) => updateAnalysisSettings({ transcribeTemperature: event.currentTarget.value })}
								/>
							</label>
						</div>
						<label>
							Terms to prioritize in transcription
							<textarea
								id="transcribePromptTerms"
								spellCheck="false"
								placeholder="Amaneka、Kiitos、調布FM、認定NPO、Cloud Run"
								value={analysisSettings.transcribePromptTerms}
								onChange={(event) => updateAnalysisSettings({ transcribePromptTerms: event.currentTarget.value })}
							></textarea>
						</label>
						<div className="toggle-column">
							<label className="toggle-row">
								<input
									id="transcribeNormalizeAudio"
									type="checkbox"
									checked={analysisSettings.transcribeNormalizeAudio}
									onChange={(event) =>
										updateAnalysisSettings({ transcribeNormalizeAudio: event.currentTarget.checked })
									}
								/>
								<span>Normalize volume before transcription</span>
							</label>
							<label className="toggle-row">
								<input
									id="transcribeFilterLowConfidence"
									type="checkbox"
									checked={analysisSettings.transcribeFilterLowConfidence}
									onChange={(event) =>
										updateAnalysisSettings({ transcribeFilterLowConfidence: event.currentTarget.checked })
									}
								/>
								<span>Remove obvious empty transcription segments</span>
							</label>
							<label className="toggle-row">
								<input
									id="conditionOnPreviousText"
									type="checkbox"
									checked={analysisSettings.conditionOnPreviousText}
									onChange={(event) => updateAnalysisSettings({ conditionOnPreviousText: event.currentTarget.checked })}
								/>
								<span>Use previous subtitle text as context</span>
							</label>
						</div>
					</div>
				</details>
				<details className="advanced-settings">
					<summary>Runtime paths</summary>
					<div className="advanced-settings-grid">
						<label>
							Python executable
							<input
								id="pythonPath"
								value={toolPaths.pythonPath}
								onChange={(event) => {
									setToolPaths({ pythonPath: event.currentTarget.value });
									dispatchWorkflowSettingsChange();
								}}
							/>
						</label>
						<label>
							FFmpeg executable
							<input
								id="ffmpegPath"
								value={toolPaths.ffmpegPath}
								onChange={(event) => {
									setToolPaths({ ffmpegPath: event.currentTarget.value });
									dispatchWorkflowSettingsChange();
								}}
							/>
						</label>
						<label>
							FFprobe executable
							<input
								id="ffprobePath"
								value={toolPaths.ffprobePath}
								onChange={(event) => {
									setToolPaths({ ffprobePath: event.currentTarget.value });
									dispatchWorkflowSettingsChange();
								}}
							/>
						</label>
					</div>
				</details>
				<label className="workflow-media-field">
					Input video to process
					<input id="inputVideoPath" type="hidden" value={inputVideoPath} readOnly />
					<WorkflowInputVideoPreview />
					<button type="button" onClick={() => dispatchToolPick("inputVideoPath")}>
						Select input video
					</button>
				</label>
				<details className="advanced-settings">
					<summary>Thumbnail / subtitle QA</summary>
					<div className="advanced-settings-grid">
						<label>
							Thumbnail time
							<input
								id="thumbnailTime"
								value={thumbnailSettings.thumbnailTime}
								onChange={(event) => updateThumbnailSettings({ thumbnailTime: event.currentTarget.value })}
							/>
						</label>
						<label>
							Thumbnail title
							<input
								id="thumbnailTitle"
								placeholder="Project title"
								value={thumbnailSettings.thumbnailTitle}
								onChange={(event) => updateThumbnailSettings({ thumbnailTitle: event.currentTarget.value })}
							/>
						</label>
						<label>
							Thumbnail subtitle
							<input
								id="thumbnailSubtitle"
								placeholder="Short supporting line"
								value={thumbnailSettings.thumbnailSubtitle}
								onChange={(event) => updateThumbnailSettings({ thumbnailSubtitle: event.currentTarget.value })}
							/>
						</label>
						<label>
							Thumbnail candidates
							<input
								id="thumbnailCandidateCount"
								type="number"
								min="1"
								max="24"
								step="1"
								value={thumbnailSettings.thumbnailCandidateCount}
								onChange={(event) => updateThumbnailSettings({ thumbnailCandidateCount: event.currentTarget.value })}
							/>
						</label>
						<label>
							Thumbnail layout
							<select
								id="thumbnailMode"
								value={thumbnailSettings.thumbnailMode}
								onChange={(event) => updateThumbnailSettings({ thumbnailMode: event.currentTarget.value })}
							>
								<SelectOptions options={THUMBNAIL_MODES} />
							</select>
						</label>
						<label>
							Thumbnail main color
							<select
								id="thumbnailMainColor"
								value={thumbnailSettings.thumbnailMainColor}
								onChange={(event) => updateThumbnailSettings({ thumbnailMainColor: event.currentTarget.value })}
							>
								<SelectOptions options={THUMBNAIL_COLOR_OPTIONS} />
							</select>
						</label>
						<label>
							Candidate times
							<textarea
								id="thumbnailCandidateTimes"
								spellCheck="false"
								placeholder="00:00:03 | Hook | Title | Subtitle"
								value={thumbnailSettings.thumbnailCandidateTimes}
								onChange={(event) => updateThumbnailSettings({ thumbnailCandidateTimes: event.currentTarget.value })}
							></textarea>
						</label>
						<label className="toggle-row">
							<input
								id="thumbnailDebugFaces"
								type="checkbox"
								checked={thumbnailSettings.thumbnailDebugFaces}
								onChange={(event) => updateThumbnailSettings({ thumbnailDebugFaces: event.currentTarget.checked })}
							/>
							<span>Draw detected face boxes on candidates</span>
						</label>
						<label>
							Max subtitle duration
							<input
								id="subtitleReviewMaxDuration"
								type="number"
								min="1"
								step="0.5"
								value={subtitleReviewSettings.subtitleReviewMaxDuration}
								onChange={(event) =>
									updateSubtitleReviewSettings({ subtitleReviewMaxDuration: event.currentTarget.value })
								}
							/>
						</label>
						<label>
							Max reading speed
							<input
								id="subtitleReviewMaxCharsPerSecond"
								type="number"
								min="4"
								step="0.5"
								value={subtitleReviewSettings.subtitleReviewMaxCharsPerSecond}
								onChange={(event) =>
									updateSubtitleReviewSettings({ subtitleReviewMaxCharsPerSecond: event.currentTarget.value })
								}
							/>
						</label>
						<label>
							Suspicious subtitle patterns
							<textarea
								id="subtitleSuspiciousPatterns"
								spellCheck="false"
								placeholder="misheard phrase or regex"
								value={subtitleReviewSettings.subtitleSuspiciousPatterns}
								onChange={(event) =>
									updateSubtitleReviewSettings({ subtitleSuspiciousPatterns: event.currentTarget.value })
								}
							></textarea>
						</label>
						<div className="toggle-column">
							<label className="toggle-row">
								<input
									id="subtitleReviewExtractClips"
									type="checkbox"
									checked={subtitleReviewSettings.subtitleReviewExtractClips}
									onChange={(event) =>
										updateSubtitleReviewSettings({ subtitleReviewExtractClips: event.currentTarget.checked })
									}
								/>
								<span>Extract flagged subtitle audio clips</span>
							</label>
							<label className="toggle-row">
								<input
									id="subtitleReviewTranscribeClips"
									type="checkbox"
									checked={subtitleReviewSettings.subtitleReviewTranscribeClips}
									onChange={(event) =>
										updateSubtitleReviewSettings({ subtitleReviewTranscribeClips: event.currentTarget.checked })
									}
								/>
								<span>Re-transcribe flagged subtitle clips</span>
							</label>
						</div>
						<label>
							Subtitle corrections
							<textarea
								id="subtitleCorrectionsText"
								spellCheck="false"
								placeholder="12 | corrected subtitle text | reason"
								value={subtitleReviewSettings.subtitleCorrectionsText}
								onChange={(event) =>
									updateSubtitleReviewSettings({ subtitleCorrectionsText: event.currentTarget.value })
								}
							></textarea>
						</label>
						<label>
							Offscreen speaker ranges
							<textarea
								id="subtitleInterviewerRanges"
								spellCheck="false"
								placeholder="00:12-00:18 | offscreen question"
								value={subtitleSpeakerSettings.subtitleInterviewerRanges}
								onChange={(event) =>
									updateSubtitleSpeakerSettings({ subtitleInterviewerRanges: event.currentTarget.value })
								}
							></textarea>
						</label>
						<label>
							Offscreen speaker patterns
							<textarea
								id="subtitleInterviewerPatterns"
								spellCheck="false"
								placeholder="offscreen|host|question"
								value={subtitleSpeakerSettings.subtitleInterviewerPatterns}
								onChange={(event) =>
									updateSubtitleSpeakerSettings({ subtitleInterviewerPatterns: event.currentTarget.value })
								}
							></textarea>
						</label>
						<label>
							Manual speaker roles
							<textarea
								id="subtitleManualRoles"
								spellCheck="false"
								placeholder="12 | interviewer | offscreen question"
								value={subtitleSpeakerSettings.subtitleManualRoles}
								onChange={(event) => updateSubtitleSpeakerSettings({ subtitleManualRoles: event.currentTarget.value })}
							></textarea>
						</label>
						<label className="toggle-row">
							<input
								id="subtitleMouthMotionDiagnostics"
								type="checkbox"
								checked={subtitleSpeakerSettings.subtitleMouthMotionDiagnostics}
								onChange={(event) =>
									updateSubtitleSpeakerSettings({ subtitleMouthMotionDiagnostics: event.currentTarget.checked })
								}
							/>
							<span>Add mouth-motion diagnostic</span>
						</label>
					</div>
				</details>
				<details className="advanced-settings">
					<summary>Analysis settings</summary>
					<div className="advanced-settings-grid">
						<label>
							Still image time
							<input
								id="stillTime"
								value={analysisSettings.stillTime}
								onChange={(event) => updateAnalysisSettings({ stillTime: event.currentTarget.value })}
							/>
						</label>
						<label>
							Person analysis detail
							<input
								id="personFpsSample"
								type="number"
								min="0.1"
								max="15"
								step="0.1"
								value={analysisSettings.personFpsSample}
								onChange={(event) => updateAnalysisSettings({ personFpsSample: event.currentTarget.value })}
							/>
						</label>
						<label>
							Person detection model
							<input
								id="personModel"
								value={analysisSettings.personModel}
								onChange={(event) => updateAnalysisSettings({ personModel: event.currentTarget.value })}
							/>
						</label>
						<label>
							Person detection threshold
							<input
								id="personConfidence"
								type="number"
								min="0.05"
								max="0.95"
								step="0.05"
								value={analysisSettings.personConfidence}
								onChange={(event) => updateAnalysisSettings({ personConfidence: event.currentTarget.value })}
							/>
						</label>
						<label>
							Test analysis length
							<input
								id="personMaxSeconds"
								type="number"
								min="1"
								step="1"
								placeholder="all"
								value={analysisSettings.personMaxSeconds}
								onChange={(event) => updateAnalysisSettings({ personMaxSeconds: event.currentTarget.value })}
							/>
						</label>
						<label>
							Videos to analyze
							<input
								id="personLimit"
								type="number"
								min="1"
								step="1"
								placeholder="all"
								value={analysisSettings.personLimit}
								onChange={(event) => updateAnalysisSettings({ personLimit: event.currentTarget.value })}
							/>
						</label>
						<div className="toggle-column">
							<label className="toggle-row">
								<input
									id="personNoMulticamRoot"
									type="checkbox"
									checked={analysisSettings.personNoMulticamRoot}
									onChange={(event) => updateAnalysisSettings({ personNoMulticamRoot: event.currentTarget.checked })}
								/>
								<span>Analyze only selected project videos</span>
							</label>
						</div>
					</div>
				</details>
			</div>
			<div className="sync-report">
				<div className="sync-report-heading">
					<strong>同期スコア</strong>
					<button
						id="refreshSyncReport"
						type="button"
						onClick={() => dispatchWorkflowAction(SYNC_REPORT_REFRESH_EVENT)}
					>
						Refresh
					</button>
				</div>
				<SyncReportList />
			</div>
		</div>
	);
}
