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

	const videoArgs = (videoCodec) => [
		"-y",
		"-f",
		"lavfi",
		"-i",
		"testsrc=size=320x180:rate=10",
		"-f",
		"lavfi",
		"-i",
		"sine=frequency=440:duration=1",
		"-t",
		"1",
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
	run(ffmpeg, ["-y", "-f", "lavfi", "-i", "sine=frequency=880:duration=1", "-c:a", "pcm_s16le", audioPath]);
	run(ffmpeg, ["-y", "-f", "lavfi", "-i", "color=c=0x0f766e:s=80x80", "-frames:v", "1", imagePath]);
	writeFileSync(subtitlePath, "1\n00:00:00,000 --> 00:00:01,000\nhello from smoke\n", "utf8");
	writeFileSync(otherPath, "production notes", "utf8");
	return { videoPath, imagePath, subtitlePath, otherPath, audioPath };
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
		VIDEO_EDIT_SMOKE_AUDIO_PATHS: JSON.stringify([fixture.audioPath]),
		VIDEO_EDIT_SMOKE_UI_DROP_TIMEOUT_MS: "60000",
	},
});

const payload = JSON.parse(readFileSync(resultPath, "utf8"));
const summary = validateSmokeResult(payload, fixture);
console.log(JSON.stringify({ ok: true, smokeRoot, ...summary }, null, 2));
