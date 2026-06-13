import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const appRoot = path.resolve(scriptDir, "..");
const videoEditRoot = path.resolve(appRoot, "..");
const smokeRunName = `review-ui-${new Date().toISOString().replace(/[:.]/g, "-")}`;
const smokeProjectsRoot = path.join(videoEditRoot, "projects", "__smoke__", "review-ui", smokeRunName);
const smokeRoot = path.join(appRoot, "smoke_outputs", smokeRunName);
const projectId = "review-ui-project";
const projectRoot = path.join(smokeProjectsRoot, projectId);
const sourceRoot = path.join(projectRoot, "source");
const outputRoot = path.join(projectRoot, "output");
const sourceVideoPath = path.join(sourceRoot, "video", "review_source.mp4");
const previewPath = path.join(outputRoot, "videos", "previews", "review_preview.mp4");
const manifestPath = path.join(outputRoot, "reports", "media_manifest.json");
const statePath = path.join(projectRoot, "project_state.json");
const resultPath = path.join(smokeRoot, "result.json");
const codexCapturePath = path.join(smokeRoot, "codex-turns.json");
const rangeInstruction = "Tighten selected smoke range.";
const globalInstruction = "Polish the full smoke preview globally.";

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
		cwd: options.cwd || appRoot,
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

function assert(condition, message) {
	if (!condition) {
		throw new Error(message);
	}
}

function normalize(value) {
	return path.resolve(String(value || "")).toLowerCase();
}

function makeFixture() {
	mkdirSync(path.dirname(sourceVideoPath), { recursive: true });
	mkdirSync(path.dirname(previewPath), { recursive: true });
	mkdirSync(path.dirname(manifestPath), { recursive: true });
	mkdirSync(path.join(outputRoot, "app"), { recursive: true });
	const ffmpeg = findTool("ffmpeg", "C:\\ProgramData\\chocolatey\\bin\\ffmpeg.exe");
	const args = (targetPath) => [
		"-y",
		"-f",
		"lavfi",
		"-i",
		"testsrc2=size=480x270:rate=24",
		"-f",
		"lavfi",
		"-i",
		"sine=frequency=660:duration=3",
		"-t",
		"3",
		"-pix_fmt",
		"yuv420p",
		"-c:v",
		"libx264",
		"-preset",
		"ultrafast",
		"-c:a",
		"aac",
		targetPath,
	];
	try {
		run(ffmpeg, args(sourceVideoPath), { timeout: 120_000 });
	} catch {
		const fallbackArgs = args(sourceVideoPath);
		const codecIndex = fallbackArgs.indexOf("libx264");
		fallbackArgs[codecIndex] = "mpeg4";
		run(ffmpeg, fallbackArgs, { timeout: 120_000 });
	}
	const previewArgs = ["-y", "-i", sourceVideoPath, "-t", "3", "-c", "copy", previewPath];
	run(ffmpeg, previewArgs, { timeout: 120_000 });
}

function projectInfo() {
	return {
		id: projectId,
		name: "Review UI Project",
		root: projectRoot,
		sourceRoot,
		outputRoot,
	};
}

function writeProjectFiles() {
	const project = projectInfo();
	const now = new Date().toISOString();
	const videoStat = statSync(sourceVideoPath);
	const mediaItem = {
		id: "media-001",
		kind: "video",
		role: "master",
		label: "Review source",
		path: sourceVideoPath,
		originalPath: sourceVideoPath,
		relativePath: path.relative(sourceRoot, sourceVideoPath),
		name: path.basename(sourceVideoPath),
		extension: path.extname(sourceVideoPath).toLowerCase(),
		sizeBytes: videoStat.size,
		confidence: 1,
		reason: "review smoke fixture",
		metadata: {
			duration: 3,
			width: 480,
			height: 270,
			frameRate: 24,
			hasVideo: true,
			hasAudio: true,
			storage: "project",
		},
	};
	const manifest = {
		version: 1,
		generatedAt: now,
		sourceDirectory: sourceRoot,
		sourcePaths: [sourceVideoPath],
		manifestPath,
		files: [mediaItem],
		cameras: [mediaItem],
		audio: [],
		images: [],
		subtitles: [],
		other: [],
		selected: {
			masterVideo: sourceVideoPath,
		},
	};
	const projectState = {
		version: 1,
		revision: 1,
		updatedAt: now,
		project,
		assets: {
			mediaDirectory: sourceRoot,
			mediaManifestPath: manifestPath,
			mediaManifest: manifest,
			sourceRoot,
			masterVideo: sourceVideoPath,
		},
		render: {
			renderScript: "render_multicam.py",
			workflowAction: "render-selected",
			outputPath: previewPath,
			renderProfile: "preview",
			rangeMode: "range",
			previewStart: 0,
			previewDuration: 3,
			subtitleMode: "none",
			encoderPreset: "ultrafast",
			encoderCrf: 30,
		},
		editRequest: {
			instructionDraft: "",
			instructionHistory: [],
			requestedPreviewPath: "",
			requestedFinalPath: "",
			lastPreviewPath: previewPath,
			lastFinalPath: "",
		},
		review: {
			previewVideoPath: previewPath,
			currentTime: 0,
			selectedRange: null,
			zoom: 1,
			scrollStart: 0,
			reviewTimelinePath: "",
		},
		tools: {
			ffmpeg: findTool("ffmpeg", "C:\\ProgramData\\chocolatey\\bin\\ffmpeg.exe"),
			ffprobe: findTool("ffprobe", "C:\\ProgramData\\chocolatey\\bin\\ffprobe.exe"),
		},
	};
	writeFileSync(
		path.join(projectRoot, "project.json"),
		JSON.stringify(
			{
				id: project.id,
				name: project.name,
				sourceRoot: project.sourceRoot,
				outputRoot: project.outputRoot,
				updatedAt: now,
			},
			null,
			2,
		),
		"utf8",
	);
	writeFileSync(manifestPath, JSON.stringify(manifest, null, 2), "utf8");
	writeFileSync(statePath, JSON.stringify(projectState, null, 2), "utf8");
	return { project, manifest };
}

function extractSection(text, startLabel, endLabel) {
	const start = text.indexOf(startLabel);
	if (start < 0) {
		return "";
	}
	const end = text.indexOf(endLabel, start + startLabel.length);
	return end < 0 ? text.slice(start) : text.slice(start, end);
}

function validateSmokeResult(payload) {
	assert(payload?.ok, `smoke failed: ${payload?.error || "unknown error"}`);
	const result = payload.result || {};
	assert(
		result.inlineVideoSrc && String(result.inlineVideoSrc).startsWith("file:"),
		"inline video src was not a file URL",
	);
	assert(result.loadedPreview?.ok, "loadReviewPreview did not succeed");
	assert(result.loadedPreview.thumbnailCount > 0, "thumbnail strip was not loaded");
	assert(result.loadedPreview.waveformPeakCount > 0, "waveform peaks were not loaded");
	assert(result.outsidePreviewRejected === true, "project-external preview path was not rejected");
	assert(
		result.selection && Number(result.selection.end) > Number(result.selection.start),
		"selectedRange was not created",
	);
	assert(result.rangePreviewStart !== undefined, "range previewStart was not persisted");
	assert(Number(result.rangePreviewDuration) > 0, "range previewDuration was not persisted");
	const history = Array.isArray(result.history) ? result.history : [];
	assert(
		history.some((item) => item.scope === "range" && item.selection),
		"range instruction was not recorded",
	);
	assert(
		history.some((item) => item.scope === "global" && !item.selection),
		"global instruction was not recorded",
	);
	const reviewTimelinePath = result.loadedPreview.reviewTimelinePath;
	assert(existsSync(reviewTimelinePath), "review_timeline.json was not written");
	const reviewTimeline = JSON.parse(readFileSync(reviewTimelinePath, "utf8"));
	for (const key of ["thumbnailStripPath", "waveformPath"]) {
		const assetPath = reviewTimeline[key];
		assert(assetPath && existsSync(assetPath), `${key} was not written`);
		assert(
			normalize(assetPath).startsWith(normalize(path.join(outputRoot, "app"))),
			`${key} was written outside output/app: ${assetPath}`,
		);
	}
	assert(existsSync(codexCapturePath), "Codex capture was not written");
	const capture = JSON.parse(readFileSync(codexCapturePath, "utf8"));
	const turns = Array.isArray(capture.turns) ? capture.turns : [];
	const rangeTurn = turns.find((turn) => String(turn.prompt || "").includes(rangeInstruction));
	const globalTurn = turns.find((turn) => String(turn.prompt || "").includes(globalInstruction));
	assert(rangeTurn, "range prompt was not captured");
	assert(globalTurn, "global prompt was not captured");
	const rangePrompt = String(rangeTurn.prompt || "");
	const globalPrompt = String(globalTurn.prompt || "");
	assert(rangePrompt.includes("- Scope: range"), "range prompt did not include range scope");
	assert(rangePrompt.includes("- Selected range:"), "range prompt did not include selected range");
	assert(rangePrompt.includes("- Current review time:"), "range prompt did not include current review time");
	const globalReviewTarget = extractSection(globalPrompt, "Review target:", "Requested output:");
	assert(globalReviewTarget.includes("- Scope: global"), "global prompt did not include global scope");
	assert(!globalReviewTarget.includes("Selected range:"), "global review target included selected range");
	assert(!globalReviewTarget.includes("Current review time:"), "global review target included current review time");
	return {
		project: result.project.root,
		preview: path.relative(projectRoot, result.loadedPreview.previewVideoPath),
		reviewTimeline: path.relative(projectRoot, reviewTimelinePath),
		selection: result.selection,
		history: result.history,
	};
}

mkdirSync(smokeRoot, { recursive: true });
makeFixture();
writeProjectFiles();
const electronCommand = process.platform === "win32" ? "cmd.exe" : "pnpm";
const electronArgs =
	process.platform === "win32" ? ["/d", "/s", "/c", "pnpm exec electron ."] : ["exec", "electron", "."];
run(electronCommand, electronArgs, {
	stdio: "inherit",
	timeout: 120_000,
	env: {
		...process.env,
		VIDEO_EDIT_SMOKE: "1",
		VIDEO_EDIT_PROJECTS_ROOT: smokeProjectsRoot,
		VIDEO_EDIT_SMOKE_REVIEW_RESULT: resultPath,
		VIDEO_EDIT_SMOKE_CODEX_CAPTURE_PATH: codexCapturePath,
		VIDEO_EDIT_SMOKE_REVIEW_RANGE_INSTRUCTION: rangeInstruction,
		VIDEO_EDIT_SMOKE_REVIEW_GLOBAL_INSTRUCTION: globalInstruction,
		VIDEO_EDIT_SMOKE_UI_DROP_TIMEOUT_MS: "60000",
	},
});

const payload = JSON.parse(readFileSync(resultPath, "utf8"));
const summary = validateSmokeResult(payload);
console.log(JSON.stringify({ ok: true, smokeRoot, ...summary }, null, 2));
