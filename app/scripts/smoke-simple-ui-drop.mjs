import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const appRoot = path.resolve(scriptDir, "..");
const smokeRoot = path.join(
	appRoot,
	"smoke_outputs",
	`simple-ui-drop-${new Date().toISOString().replace(/[:.]/g, "-")}`,
);
const materialRoot = path.join(smokeRoot, "material folder");
const audioRoot = path.join(smokeRoot, "audio folder");
const resultPath = path.join(smokeRoot, "result.json");
const codexCapturePath = path.join(smokeRoot, "codex-turns.json");
const smokeStamp = new Date().toISOString().replace(/[:.]/g, "-");

function findTool(name, fallback) {
	const candidates =
		process.platform === "win32"
			? [process.env[`VIDEO_EDIT_${name.toUpperCase()}`], fallback, `${name}.exe`, name].filter(Boolean)
			: [process.env[`VIDEO_EDIT_${name.toUpperCase()}`], fallback, name].filter(Boolean);
	for (const candidate of candidates) {
		if (path.isAbsolute(candidate) && existsSync(candidate)) {
			return candidate;
		}
		if (!path.isAbsolute(candidate)) {
			const probe = spawnSync(candidate, ["-version"], { encoding: "utf8" });
			if (!probe.error && probe.status === 0) {
				return candidate;
			}
		}
	}
	throw new Error(`${name} was not found`);
}

function run(command, args, options = {}) {
	const result = spawnSync(command, args, {
		cwd: appRoot,
		encoding: "utf8",
		stdio: options.stdio || "pipe",
		env: options.env || process.env,
		timeout: options.timeout || 60_000,
	});
	if (result.error) {
		throw result.error;
	}
	if (result.status !== 0) {
		throw new Error(
			[
				`${path.basename(command)} ${args.join(" ")} failed with exit code ${result.status}`,
				result.stdout,
				result.stderr,
			]
				.filter(Boolean)
				.join("\n"),
		);
	}
	return result;
}

function shellQuotePowerShell(value) {
	return `'${String(value).replace(/'/g, "''")}'`;
}

function synthesizeSpeechAudio(audioPath) {
	if (process.platform !== "win32") {
		return false;
	}
	const script = [
		"Add-Type -AssemblyName System.Speech",
		"$s = New-Object System.Speech.Synthesis.SpeechSynthesizer",
		"$s.Rate = -1",
		`$s.SetOutputToWaveFile(${shellQuotePowerShell(audioPath)})`,
		"$s.Speak('hello smoke test preview final rendering')",
		"$s.Dispose()",
	].join("; ");
	const result = spawnSync("powershell.exe", ["-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script], {
		cwd: appRoot,
		encoding: "utf8",
		stdio: "pipe",
		timeout: 60_000,
	});
	return !result.error && result.status === 0 && existsSync(audioPath);
}

function normalize(value) {
	return path.resolve(String(value || "")).toLowerCase();
}

function assert(condition, message) {
	if (!condition) {
		throw new Error(message);
	}
}

function makeFixture() {
	mkdirSync(path.join(materialRoot, "nested subtitles"), { recursive: true });
	mkdirSync(path.join(materialRoot, "images"), { recursive: true });
	mkdirSync(audioRoot, { recursive: true });
	const ffmpeg = findTool("ffmpeg", "C:\\ProgramData\\chocolatey\\bin\\ffmpeg.exe");
	const videoPath = path.join(materialRoot, "nested camera 1.mp4");
	const imagePath = path.join(materialRoot, "images", "logo image.png");
	const subtitlePath = path.join(materialRoot, "nested subtitles", "captions.srt");
	const otherPath = path.join(materialRoot, "production notes.txt");
	const audioPath = path.join(audioRoot, "drop narration.wav");
	const audioDecoyPath = path.join(audioRoot, "not audio.txt");

	const videoArgs = (videoCodec) => [
		"-y",
		"-f",
		"lavfi",
		"-i",
		"testsrc=size=320x180:rate=10",
		"-f",
		"lavfi",
		"-i",
		"sine=frequency=440:duration=2",
		"-t",
		"2",
		"-pix_fmt",
		"yuv420p",
		"-c:v",
		videoCodec,
		"-c:a",
		"aac",
		videoPath,
	];
	try {
		run(ffmpeg, videoArgs("libx264"));
	} catch {
		run(ffmpeg, videoArgs("mpeg4"));
	}
	const speechAudio = synthesizeSpeechAudio(audioPath);
	if (!speechAudio) {
		run(ffmpeg, ["-y", "-f", "lavfi", "-i", "sine=frequency=880:duration=1", "-c:a", "pcm_s16le", audioPath]);
	}
	run(ffmpeg, ["-y", "-f", "lavfi", "-i", "color=c=0x0f766e:s=80x80", "-frames:v", "1", imagePath]);
	writeFileSync(subtitlePath, "1\n00:00:00,000 --> 00:00:01,000\nhello from smoke\n", "utf8");
	writeFileSync(otherPath, "production notes", "utf8");
	writeFileSync(audioDecoyPath, "this file must not be appended from the audio drop zone", "utf8");
	return { videoPath, imagePath, subtitlePath, otherPath, audioPath, audioDecoyPath, speechAudio };
}

function validateSmokeResult(payload, fixture) {
	assert(payload?.ok, `smoke failed: ${payload?.error || "unknown error"}`);
	const result = payload.result || {};
	const project = result.project || {};
	const files = result.files || [];
	const counts = result.counts || {};
	assert(project.root && project.sourceRoot && project.outputRoot, "project paths were not returned");
	assert(result.sourceDirectory === project.sourceRoot, "manifest sourceDirectory is not the project sourceRoot");
	assert(
		result.manifestPath && normalize(result.manifestPath).startsWith(normalize(project.outputRoot)),
		"manifest path is outside outputRoot",
	);
	assert(existsSync(result.manifestPath), "manifest file was not written");
	assert(files.length >= 5, `expected at least 5 files after material+audio drop, got ${files.length}`);
	assert(counts.cameras >= 1, "video was not classified as a camera");
	assert(counts.audio >= 1, "dropped audio was not added to manifest audio");
	assert(counts.images >= 1, "image was not classified");
	assert(counts.subtitles >= 1, "subtitle was not classified");
	assert(counts.other >= 1, "other file was not preserved");
	const sourceRoot = normalize(project.sourceRoot);
	const projectRoot = normalize(project.root);
	for (const item of files) {
		assert(item.path && normalize(item.path).startsWith(sourceRoot), `${item.name} path is not under sourceRoot`);
		assert(existsSync(item.path), `${item.name} copied path is missing`);
		assert(item.originalPath && existsSync(item.originalPath), `${item.name} originalPath is missing`);
		assert(
			normalize(item.originalPath) !== normalize(item.path),
			`${item.name} originalPath was not preserved separately`,
		);
		assert(!normalize(item.originalPath).startsWith(projectRoot), `${item.name} originalPath points inside project`);
	}
	const audioOriginal = normalize(fixture.audioPath);
	assert(
		files.some((item) => item.kind === "audio" && normalize(item.originalPath) === audioOriginal),
		"audio drop originalPath was not merged",
	);
	assert(
		!files.some((item) => normalize(item.originalPath) === normalize(fixture.audioDecoyPath)),
		"non-audio file from the audio drop was merged into the manifest",
	);
	const relativeProjectPath = (value) => (value ? path.relative(project.root, value) : "");
	return {
		project: project.root,
		manifest: result.manifestPath,
		counts,
		files: files.map((item) => ({
			kind: item.kind,
			role: item.role,
			path: path.relative(project.root, item.path),
			original: path.relative(smokeRoot, item.originalPath),
		})),
		editRequest: result.editRequest
			? {
					history: (result.editRequest.instructionHistory || []).map((item) => ({
						mode: item.mode,
						targetPath: relativeProjectPath(item.targetPath || ""),
						text: item.text,
					})),
					requestedPreviewPath: relativeProjectPath(result.editRequest.requestedPreviewPath || ""),
					requestedFinalPath: relativeProjectPath(result.editRequest.requestedFinalPath || ""),
					lastPreviewPath: relativeProjectPath(result.editRequest.lastPreviewPath || ""),
					lastFinalPath: relativeProjectPath(result.editRequest.lastFinalPath || ""),
				}
			: null,
	};
}

function selectedManifestPath(manifest, key, group) {
	const selected = manifest.selected && typeof manifest.selected === "object" ? manifest.selected : {};
	if (selected[key]) {
		return String(selected[key]);
	}
	const items = Array.isArray(manifest[group]) ? manifest[group] : [];
	return items[0]?.path ? String(items[0].path) : "";
}

function smokeAppConfig(result, targetPath, mode) {
	const project = result.project;
	const manifest = JSON.parse(readFileSync(result.manifestPath, "utf8"));
	return {
		version: 1,
		project,
		assets: {
			mediaDirectory: project.sourceRoot,
			mediaManifestPath: result.manifestPath,
			mediaManifest: manifest,
			sourceRoot: project.sourceRoot,
			masterVideo: selectedManifestPath(manifest, "masterVideo", "cameras"),
			externalAudio: selectedManifestPath(manifest, "externalAudio", "audio"),
			logo: selectedManifestPath(manifest, "logo", "images"),
		},
		render: {
			renderScript: "render_multicam.py",
			workflowAction: "render-selected",
			outputPath: targetPath,
			renderProfile: mode === "preview" ? "preview" : "final",
			rangeMode: mode === "preview" ? "range" : "full",
			previewStart: 0,
			previewDuration: 1.25,
			subtitleMode: "none",
			audioSource: "external-if-selected",
			audioDenoise: false,
			audioMastering: false,
			shortenSilence: false,
			multicamMode: "master-first",
			encoderPreset: "ultrafast",
			encoderCrf: mode === "preview" ? 30 : 28,
			usePersonEditPlans: false,
			useTranscriptComparisonSync: false,
			globalVideoZoom: 1,
		},
		analysis: {
			transcribeModel: "tiny",
			transcribeLanguage: "en",
			transcribeBeamSize: 1,
			transcribeTemperature: "0",
			conditionOnPreviousText: false,
			transcribeNormalizeAudio: false,
			transcribeFilterLowConfidence: false,
		},
		tools: {
			ffmpeg: findTool("ffmpeg", "C:\\ProgramData\\chocolatey\\bin\\ffmpeg.exe"),
			ffprobe: findTool("ffprobe", "C:\\ProgramData\\chocolatey\\bin\\ffprobe.exe"),
		},
		style: {
			titleText: "Smoke",
			logoHeight: 48,
		},
	};
}

function writeSmokeConfig(result, targetPath, mode) {
	const configPath = path.join(smokeRoot, `runtime-${mode}.json`);
	writeFileSync(configPath, JSON.stringify(smokeAppConfig(result, targetPath, mode), null, 2), "utf8");
	return configPath;
}

function runPythonAction(action, configPath, timeout = 600_000) {
	return run("python", [path.join("..", "scripts", "video_edit_run.py"), "--action", action], {
		timeout,
		env: {
			...process.env,
			VIDEO_EDIT_APP_CONFIG: configPath,
		},
	});
}

function validateTranscription(result, fixture) {
	const configPath = writeSmokeConfig(
		result,
		path.join(result.project.outputRoot, "videos", "previews", "transcribe_probe.mp4"),
		"preview",
	);
	runPythonAction("transcribe-dropped", configPath, 900_000);
	const transcriptPath = path.join(
		result.project.outputRoot,
		"transcripts",
		"manifest_sources",
		"manifest_transcripts.json",
	);
	assert(existsSync(transcriptPath), "transcript manifest was not written");
	const transcript = JSON.parse(readFileSync(transcriptPath, "utf8"));
	const transcripts = Array.isArray(transcript.transcripts) ? transcript.transcripts : [];
	assert(transcripts.length >= 1, "no transcript entries were written");
	assert(Array.isArray(transcript.errors) && transcript.errors.length === 0, "transcription reported errors");
	assert(transcript.primarySrt && existsSync(transcript.primarySrt), "primary transcript SRT was not written");
	if (fixture.speechAudio) {
		const external = transcripts.find((item) => item.role === "external");
		assert(external && Number(external.textLength || 0) > 0, "speech audio did not produce transcript text");
	}
	return {
		manifest: transcriptPath,
		primarySrt: transcript.primarySrt,
		transcripts: transcripts.map((item) => ({
			role: item.role,
			kind: item.kind,
			textLength: item.textLength,
			segmentCount: item.segmentCount,
		})),
	};
}

function outputDurationSeconds(targetPath) {
	const ffprobe = findTool("ffprobe", "C:\\ProgramData\\chocolatey\\bin\\ffprobe.exe");
	const result = run(ffprobe, [
		"-v",
		"error",
		"-show_entries",
		"format=duration",
		"-of",
		"default=noprint_wrappers=1:nokey=1",
		targetPath,
	]);
	return Number.parseFloat(result.stdout.trim());
}

function validateRender(result, mode) {
	const outputName = mode === "preview" ? `preview_${smokeStamp}.mp4` : `final_${smokeStamp}.mp4`;
	const targetPath =
		mode === "preview"
			? path.join(result.project.outputRoot, "videos", "previews", outputName)
			: path.join(result.project.outputRoot, "videos", outputName);
	const configPath = writeSmokeConfig(result, targetPath, mode);
	runPythonAction("render-selected", configPath, 900_000);
	assert(existsSync(targetPath), `${mode} render output was not written`);
	const duration = outputDurationSeconds(targetPath);
	assert(Number.isFinite(duration) && duration > 0, `${mode} render output duration is invalid`);
	return {
		path: targetPath,
		duration,
	};
}

function validateCodexCapture(result) {
	assert(existsSync(codexCapturePath), "Codex request capture was not written");
	const capture = JSON.parse(readFileSync(codexCapturePath, "utf8"));
	const turns = Array.isArray(capture.turns) ? capture.turns : [];
	assert(turns.length >= 2, `expected preview and final Codex turns, got ${turns.length}`);
	const preview = turns.find((turn) => String(turn.prompt || "").includes("preview_"));
	const final = turns.find((turn) => String(turn.prompt || "").includes("final_"));
	assert(preview, "preview Codex prompt was not captured");
	assert(final, "final Codex prompt was not captured");
	assert(
		String(preview.prompt).includes(result.manifestPath),
		"preview prompt did not include the media manifest path",
	);
	assert(String(final.prompt).includes(result.manifestPath), "final prompt did not include the media manifest path");
	assert(
		String(preview.prompt).includes("Create a short energetic preview"),
		"preview prompt missed the natural language instruction",
	);
	assert(
		String(final.prompt).includes("Add a concise finishing version"),
		"final prompt missed the follow-up instruction",
	);
	const request = result.editRequest || {};
	assert(
		String(request.requestedPreviewPath || "").includes("preview_"),
		"project state did not store requestedPreviewPath",
	);
	assert(String(request.requestedFinalPath || "").includes("final_"), "project state did not store requestedFinalPath");
	assert(!request.lastPreviewPath, "lastPreviewPath should not be promoted before the output file exists");
	assert(!request.lastFinalPath, "lastFinalPath should not be promoted before the output file exists");
	return {
		turns: turns.map((turn) => ({
			createdAt: turn.createdAt,
			model: turn.settings?.model || "",
			promptLength: String(turn.prompt || "").length,
			target: String(turn.prompt || "").match(/Target output path: (.+)/)?.[1] || "",
		})),
	};
}

mkdirSync(smokeRoot, { recursive: true });
const fixture = makeFixture();
const electronCommand = process.platform === "win32" ? "cmd.exe" : "pnpm";
const electronArgs =
	process.platform === "win32" ? ["/d", "/s", "/c", "pnpm exec electron ."] : ["exec", "electron", "."];
run(electronCommand, electronArgs, {
	stdio: "inherit",
	timeout: 90_000,
	env: {
		...process.env,
		VIDEO_EDIT_SMOKE: "1",
		VIDEO_EDIT_SMOKE_UI_DROP_RESULT: resultPath,
		VIDEO_EDIT_SMOKE_MATERIAL_PATHS: JSON.stringify([materialRoot]),
		VIDEO_EDIT_SMOKE_AUDIO_PATHS: JSON.stringify([fixture.audioPath, fixture.audioDecoyPath]),
		VIDEO_EDIT_SMOKE_CODEX_CAPTURE_PATH: codexCapturePath,
		VIDEO_EDIT_SMOKE_SIMPLE_INSTRUCTION: "Create a short energetic preview from the dropped materials.",
		VIDEO_EDIT_SMOKE_UI_DROP_TIMEOUT_MS: "60000",
	},
});

const payload = JSON.parse(readFileSync(resultPath, "utf8"));
const summary = validateSmokeResult(payload, fixture);
const transcription = validateTranscription(payload.result, fixture);
const preview = validateRender(payload.result, "preview");
const final = validateRender(payload.result, "final");
const codex = validateCodexCapture(payload.result);
console.log(JSON.stringify({ ok: true, smokeRoot, ...summary, transcription, preview, final, codex }, null, 2));
