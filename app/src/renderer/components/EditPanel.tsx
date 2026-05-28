import { RUN_REFRESH_PROMPT_EVENT } from "../events.js";
import {
	AUDIO_SOURCES,
	EDIT_PRESETS,
	ENCODER_PRESETS,
	MULTICAM_MODES,
	MUSIC_RANGE_SOURCES,
	MUSIC_SCOPES,
} from "../form-options.js";
import { type MusicSettings, type OmissionCardSettings, type RenderSettings, useAppStore } from "../store/app-store.js";
import { SelectOptions } from "./SelectOptions.js";

type PanelProps = {
	readonly hidden?: boolean;
};

function dispatchEditSettingsChange() {
	document.dispatchEvent(new CustomEvent(RUN_REFRESH_PROMPT_EVENT));
}

export function EditPanel({ hidden = false }: PanelProps) {
	const workflowSettings = useAppStore((store) => store.workflowSettings);
	const setWorkflowSettings = useAppStore((store) => store.setWorkflowSettings);
	const renderSettings = useAppStore((store) => store.renderSettings);
	const setRenderSettings = useAppStore((store) => store.setRenderSettings);
	const musicSettings = useAppStore((store) => store.musicSettings);
	const setMusicSettings = useAppStore((store) => store.setMusicSettings);
	const omissionCardSettings = useAppStore((store) => store.omissionCardSettings);
	const setOmissionCardSettings = useAppStore((store) => store.setOmissionCardSettings);
	const updateRenderSettings = (settings: Partial<RenderSettings>) => {
		setRenderSettings(settings);
		dispatchEditSettingsChange();
	};
	const updateMusicSettings = (settings: Partial<MusicSettings>) => {
		setMusicSettings(settings);
		dispatchEditSettingsChange();
	};
	const updateOmissionCardSettings = (settings: Partial<OmissionCardSettings>) => {
		setOmissionCardSettings(settings);
		dispatchEditSettingsChange();
	};

	return (
		<div className="panel" data-panel="edit" hidden={hidden}>
			<div className="panel-heading">
				<h3>編集</h3>
				<span>edit settings</span>
			</div>
			<div className="field-stack">
				<label>
					Edit preset
					<select
						id="editPreset"
						value={workflowSettings.editPreset}
						onChange={(event) => {
							const editPreset = event.currentTarget.value;
							setWorkflowSettings({
								editPreset,
								renderScript:
									editPreset === "new-interview" ? "render_app_interview.py" : workflowSettings.renderScript,
								previewDuration: editPreset === "new-interview" ? "60" : workflowSettings.previewDuration,
							});
							dispatchEditSettingsChange();
						}}
					>
						<SelectOptions options={EDIT_PRESETS} />
					</select>
				</label>
				<label>
					Multicam switching
					<select
						id="multicamMode"
						value={renderSettings.multicamMode}
						onChange={(event) => updateRenderSettings({ multicamMode: event.currentTarget.value })}
					>
						<SelectOptions options={MULTICAM_MODES} />
					</select>
				</label>
				<label>
					Audio source
					<select
						id="audioSource"
						value={renderSettings.audioSource}
						onChange={(event) => updateRenderSettings({ audioSource: event.currentTarget.value })}
					>
						<SelectOptions options={AUDIO_SOURCES} />
					</select>
				</label>
				<label className="toggle-row">
					<input
						id="audioDenoise"
						type="checkbox"
						checked={renderSettings.audioDenoise}
						onChange={(event) => updateRenderSettings({ audioDenoise: event.currentTarget.checked })}
					/>
					<span>Reduce background noise</span>
				</label>
				<label className="toggle-row">
					<input
						id="colorMatchCameras"
						type="checkbox"
						checked={renderSettings.colorMatchCameras}
						onChange={(event) => updateRenderSettings({ colorMatchCameras: event.currentTarget.checked })}
					/>
					<span>Match camera color</span>
				</label>
				<label className="toggle-row">
					<input
						id="usePersonEditPlans"
						type="checkbox"
						checked={renderSettings.usePersonEditPlans}
						onChange={(event) => updateRenderSettings({ usePersonEditPlans: event.currentTarget.checked })}
					/>
					<span>Use person analysis for crops</span>
				</label>
				<label className="toggle-row">
					<input
						id="useTranscriptComparisonSync"
						type="checkbox"
						checked={renderSettings.useTranscriptComparisonSync}
						onChange={(event) => updateRenderSettings({ useTranscriptComparisonSync: event.currentTarget.checked })}
					/>
					<span>Use transcript comparison for sync fallback</span>
				</label>
				<label className="toggle-row">
					<input
						id="naturalDialogueCuts"
						type="checkbox"
						checked={renderSettings.naturalDialogueCuts}
						onChange={(event) => updateRenderSettings({ naturalDialogueCuts: event.currentTarget.checked })}
					/>
					<span>Place camera cuts in dialogue gaps</span>
				</label>
				<label className="toggle-row">
					<input
						id="audioMastering"
						type="checkbox"
						checked={renderSettings.audioMastering}
						onChange={(event) => updateRenderSettings({ audioMastering: event.currentTarget.checked })}
					/>
					<span>Master audio for online video</span>
				</label>
				<div className="two-col">
					<label>
						Encoder preset
						<select
							id="encoderPreset"
							value={renderSettings.encoderPreset}
							onChange={(event) => updateRenderSettings({ encoderPreset: event.currentTarget.value })}
						>
							<SelectOptions options={ENCODER_PRESETS} />
						</select>
					</label>
					<label>
						Video quality (CRF, lower is better)
						<input
							id="renderCrf"
							type="number"
							min="0"
							max="51"
							step="1"
							value={renderSettings.renderCrf}
							onChange={(event) => updateRenderSettings({ renderCrf: event.currentTarget.value })}
						/>
					</label>
				</div>
				<label>
					Noise reduction strength
					<input
						id="audioDenoiseStrength"
						type="number"
						min="0"
						max="30"
						step="1"
						value={renderSettings.audioDenoiseStrength}
						onChange={(event) => updateRenderSettings({ audioDenoiseStrength: event.currentTarget.value })}
					/>
				</label>
				<div className="music-settings">
					<label className="toggle-row">
						<input
							id="musicEnabled"
							type="checkbox"
							checked={musicSettings.musicEnabled}
							onChange={(event) => updateMusicSettings({ musicEnabled: event.currentTarget.checked })}
						/>
						<span>Generate and mix background music</span>
					</label>
					<div className="two-col">
						<label>
							Music placement
							<select
								id="musicScope"
								value={musicSettings.musicScope}
								onChange={(event) => updateMusicSettings({ musicScope: event.currentTarget.value })}
							>
								<SelectOptions options={MUSIC_SCOPES} />
							</select>
						</label>
						<label>
							Omission range source
							<select
								id="musicRangeSource"
								value={musicSettings.musicRangeSource}
								onChange={(event) => updateMusicSettings({ musicRangeSource: event.currentTarget.value })}
							>
								<SelectOptions options={MUSIC_RANGE_SOURCES} />
							</select>
						</label>
						<label>
							Music level
							<input
								id="musicVolume"
								type="range"
								min="0"
								max="40"
								step="1"
								value={musicSettings.musicVolume}
								onChange={(event) => updateMusicSettings({ musicVolume: event.currentTarget.value })}
							/>
						</label>
					</div>
					<label>
						Music direction
						<textarea
							id="musicPrompt"
							spellCheck="false"
							placeholder="quiet, clean, documentary-like bed for a reflective interview"
							value={musicSettings.musicPrompt}
							onChange={(event) => updateMusicSettings({ musicPrompt: event.currentTarget.value })}
						></textarea>
					</label>
					<label>
						Omission title ranges
						<textarea
							id="musicRangesText"
							spellCheck="false"
							placeholder="00:12-00:18 省略テロップ"
							value={musicSettings.musicRangesText}
							onChange={(event) => updateMusicSettings({ musicRangesText: event.currentTarget.value })}
						></textarea>
					</label>
					<label className="toggle-row">
						<input
							id="omissionCardEnabled"
							type="checkbox"
							checked={omissionCardSettings.omissionCardEnabled}
							onChange={(event) => updateOmissionCardSettings({ omissionCardEnabled: event.currentTarget.checked })}
						/>
						<span>Replace omission ranges with a summary card</span>
					</label>
					<div className="two-col">
						<label>
							Card duration
							<input
								id="omissionCardDuration"
								type="number"
								min="0.5"
								max="30"
								step="0.5"
								value={omissionCardSettings.omissionCardDuration}
								onChange={(event) => updateOmissionCardSettings({ omissionCardDuration: event.currentTarget.value })}
							/>
						</label>
						<label>
							Card label
							<input
								id="omissionCardLabel"
								value={omissionCardSettings.omissionCardLabel}
								onChange={(event) => updateOmissionCardSettings({ omissionCardLabel: event.currentTarget.value })}
							/>
						</label>
					</div>
					<label>
						Summary card text
						<textarea
							id="omissionCardText"
							spellCheck="false"
							placeholder="質問を要約&#10;聞き手の長い質問を短く整理"
							value={omissionCardSettings.omissionCardText}
							onChange={(event) => updateOmissionCardSettings({ omissionCardText: event.currentTarget.value })}
						></textarea>
					</label>
					<label>
						Replacement ranges
						<textarea
							id="omissionCardRangesText"
							spellCheck="false"
							placeholder="00:12-00:30 | 質問を要約 | 聞き手の質問を短く整理"
							value={omissionCardSettings.omissionCardRangesText}
							onChange={(event) => updateOmissionCardSettings({ omissionCardRangesText: event.currentTarget.value })}
						></textarea>
					</label>
				</div>
				<div className="two-col">
					<label>
						Start
						<input
							id="previewStart"
							type="number"
							min="0"
							step="0.1"
							value={renderSettings.previewStart}
							onChange={(event) => updateRenderSettings({ previewStart: event.currentTarget.value })}
						/>
					</label>
					<label>
						Output duration
						<input
							id="previewDuration"
							type="number"
							min="5"
							step="1"
							value={workflowSettings.previewDuration}
							onChange={(event) => {
								setWorkflowSettings({ previewDuration: event.currentTarget.value });
								dispatchEditSettingsChange();
							}}
						/>
					</label>
				</div>
				<label className="toggle-row">
					<input
						id="shortenSilence"
						type="checkbox"
						checked={renderSettings.shortenSilence}
						onChange={(event) => updateRenderSettings({ shortenSilence: event.currentTarget.checked })}
					/>
					<span>Shorten long silence</span>
				</label>
				<label className="toggle-row">
					<input
						id="keepUncut"
						type="checkbox"
						checked={renderSettings.keepUncut}
						onChange={(event) => updateRenderSettings({ keepUncut: event.currentTarget.checked })}
					/>
					<span>Keep uncut draft video</span>
				</label>
				<div className="three-col">
					<label>
						Silence to shorten
						<input
							id="minSilence"
							type="number"
							min="0.5"
							step="0.1"
							value={renderSettings.minSilence}
							onChange={(event) => updateRenderSettings({ minSilence: event.currentTarget.value })}
						/>
					</label>
					<label>
						Silence to keep
						<input
							id="keepSilence"
							type="number"
							min="0"
							step="0.1"
							value={renderSettings.keepSilence}
							onChange={(event) => updateRenderSettings({ keepSilence: event.currentTarget.value })}
						/>
					</label>
					<label>
						Silence threshold
						<input
							id="silenceNoise"
							value={renderSettings.silenceNoise}
							onChange={(event) => updateRenderSettings({ silenceNoise: event.currentTarget.value })}
						/>
					</label>
				</div>
			</div>
		</div>
	);
}
