type Unsubscribe = () => void;

type EditAppApi = {
	getEnvironment: () => Promise<any>;
	createProject: (payload: any) => Promise<ProjectInfo>;
	copyProjectAssets: (payload: any) => Promise<{ project: ProjectInfo; files: Record<string, string> }>;
	pickFile: (options: any) => Promise<string | null>;
	pickDirectory: (options: any) => Promise<string | null>;
	pickOutput: (options: any) => Promise<string | null>;
	startCodexTurn: (payload: any) => Promise<any>;
	execCodexCommand: (payload: any) => Promise<any>;
	interruptCodex: () => Promise<any>;
	getSyncReport: (appConfig?: any) => Promise<any>;
	loadGlossaryCandidates: (appConfig: any) => Promise<any>;
	showPath: (targetPath: string) => Promise<void>;
	filePath: (file: File) => string;
	onServerReady: (callback: (payload: any) => void) => Unsubscribe;
	onServerError: (callback: (payload: any) => void) => Unsubscribe;
	onServerExit: (callback: (payload: any) => void) => Unsubscribe;
	onServerStderr: (callback: (payload: any) => void) => Unsubscribe;
	onServerNotification: (callback: (payload: any) => void) => Unsubscribe;
};

const editApp = (window as unknown as { editApp: EditAppApi }).editApp;

type ProjectInfo = {
	id: string;
	name: string;
	root: string;
	sourceRoot: string;
	outputRoot: string;
};

const state = {
	env: null,
	project: null as ProjectInfo | null,
	files: {
		masterVideo: "",
		rightCloseVideo: "",
		leftCloseVideo: "",
		referenceVideo: "",
		externalAudio: "",
		logo: "",
	},
	subtitleMode: "full",
	syncReport: null,
	glossaryTerms: [],
};

type GlossaryTerm = {
	label: string;
	description: string;
	patterns: string;
	enabled: boolean;
};

const defaultPunchlines = `00:00-00:04  定義で言うと強いプロダクトというか / プロダクトが中心にあって
00:09-00:13  届けるというところだと思っているので
00:15-00:20  そこで一定なスケルメリットが / 出るということが大事だと思いますね
01:11-01:13  過剰反応されてるだけな気がしますけどね
01:27-01:33  さすがに薄々AIによって / 何かが変わるなっていうのは
01:37-01:41  どうなるんだろうっていう / 漠然とした不安がある中で
01:56-02:02  あなたの仕事例えばライターの仕事 / 明日から亡くなりますよって言われたら
02:17-02:24  会社がわざわざ / PDM配信してフリーEにしましたみたいなのは
02:24-02:29  基本的な採用候補というか / 採用におけるマーケティングの一環なのかなと思いますね
02:29-02:37  同じような職種名だと埋もれるんで / 興味持ってもらうっていうのは
03:01-03:07  採用救人状の話だったけで / 家事ある面談とか面接を通して
03:07-03:13  なるほどこういう役割を求めてるの / すり合うパターンもあるかもしれないし
03:41-03:49  会社によってビジネスのモデルとか / 通用見とかっていうのは / かなり多種多様なんですよね
03:57-04:04  各会社さんとかの / 勝ち方というか
04:06-04:13  なんでユーザーさんに必要されているか / みたいなところって / 多様性もあるし
04:25-04:35  大まかな専門職的な / この仕事が必要というのは / もちろんありますと
04:40-04:46  専門職という言葉が / 結構ミスリートというか / エンジニアとか
04:46-04:51  分かりやすすぎるだけなんですよね / 話として`;

const fileFilters = {
	masterVideo: [{ name: "Video", extensions: ["mp4", "mov", "m4v"] }],
	rightCloseVideo: [{ name: "Video", extensions: ["mp4", "mov", "m4v"] }],
	leftCloseVideo: [{ name: "Video", extensions: ["mp4", "mov", "m4v"] }],
	referenceVideo: [{ name: "Video", extensions: ["mp4", "mov", "m4v"] }],
	externalAudio: [{ name: "Audio or video", extensions: ["wav", "mp3", "aac", "m4a", "mp4", "mov"] }],
	logo: [{ name: "Image", extensions: ["png", "jpg", "jpeg", "webp"] }],
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));
const STORAGE_KEY = "video-edit-app-state-v1";
const thumbnailModes = {
	standard: {
		flag: "",
		label: "Standard",
	},
	closeup_bottom_title: {
		flag: "--closeup-bottom-title",
		label: "Center face / bottom title",
	},
	right_face_title_stack: {
		flag: "--right-face-title-stack",
		label: "Face right / title left",
	},
	left_face_title_stack: {
		flag: "--left-face-title-stack",
		label: "Face left / title right",
	},
};
const thumbnailMainColors = {
	yellow: "Yellow",
	red: "Red",
	orange: "Orange",
	green: "Green",
	blue: "Blue",
	cyan: "Cyan",
	purple: "Purple",
	pink: "Pink",
	white: "White",
};

const defaultGlossaryTerms: GlossaryTerm[] = [
	{
		label: "セミオーダー",
		patterns: "セミオゴー,セミオーダー",
		description: "標準品をベースに、一部だけ要望に合わせて調整する提供方法。",
		enabled: true,
	},
	{
		label: "セミカスタマイズ",
		patterns: "セミカスタマイズ",
		description: "完全な個別開発ではなく、共通部分を残して必要箇所だけ変えること。",
		enabled: true,
	},
	{
		label: "スケールメリット",
		patterns: "スケールメリット",
		description: "数や量が増えるほど、1件あたりのコストや手間が下がる効果。",
		enabled: true,
	},
	{
		label: "PDM",
		patterns: "PDM",
		description: "この動画で議論対象になっている制度・枠組みの略称。",
		enabled: true,
	},
	{
		label: "FD",
		patterns: "FD",
		description: "PDMの代替として話題に出ている新しい制度・枠組みの略称。",
		enabled: true,
	},
];

function shortPath(value) {
	if (!value) {
		return "not selected";
	}
	const parts = value.split(/[\\/]/);
	return parts.length > 2 ? `${parts.at(-2)}\\${parts.at(-1)}` : value;
}

function joinPath(root: string, ...parts: string[]) {
	return [root.replace(/[\\/]+$/, ""), ...parts.map((part) => part.replace(/^[\\/]+|[\\/]+$/g, ""))].join("\\");
}

function projectIdFromName(name: string) {
	const id = name
		.trim()
		.toLowerCase()
		.replace(/[^a-z0-9._-]+/g, "-")
		.replace(/^-+|-+$/g, "");
	return id || `project-${new Date().toISOString().slice(0, 10)}`;
}

function activeOutputRoot() {
	return state.project?.outputRoot || state.env?.outputRoot || "";
}

function activeSourceRoot() {
	if (state.project?.sourceRoot) {
		return state.project.sourceRoot;
	}
	return state.env?.videoEditRoot ? joinPath(state.env.videoEditRoot, "source") : "";
}

function activeProjectVideoSourceRoot() {
	return state.project ? joinPath(state.project.sourceRoot, "video") : "";
}

function setProject(project: ProjectInfo | null) {
	state.project = project;
	const nameInput = $("#projectName");
	const idInput = $("#projectId");
	const rootInput = $("#projectRoot");
	const sourceInput = $("#projectSourceRoot");
	const outputInput = $("#projectOutputRoot");
	if (nameInput) {
		nameInput.value = project?.name || "";
	}
	if (idInput) {
		idInput.value = project?.id || "";
	}
	if (rootInput) {
		rootInput.value = project?.root || "";
	}
	if (sourceInput) {
		sourceInput.value = project?.sourceRoot || "";
	}
	if (outputInput) {
		outputInput.value = project?.outputRoot || "";
	}
	const label = $("#projectLabel");
	if (label) {
		label.textContent = project ? `${project.name} / ${shortPath(project.outputRoot)}` : "No project selected";
	}
	const videoSourceRoot = activeProjectVideoSourceRoot();
	if (videoSourceRoot) {
		$("#sourceRoot").value = videoSourceRoot;
	}
	setDefaultProjectOutput(false);
	refreshPrompt();
}

function setDefaultProjectOutput(preserveExisting = true) {
	if (!state.project) {
		return;
	}
	const outputPath = $("#outputPath");
	if (!outputPath) {
		return;
	}
	const current = outputPath.value || "";
	if (preserveExisting && current && !state.env?.knownOutputs?.includes(current)) {
		return;
	}
	const mode = state.subtitleMode === "punchline" ? "punchline" : "full_transcript";
	outputPath.value = joinPath(state.project.outputRoot, "videos", `codex_edit_${mode}.mp4`);
}

function syncReportPath() {
	return joinPath(activeOutputRoot(), "reports", "app_sync_offsets.json");
}

function glossaryTerms(): GlossaryTerm[] {
	return state.glossaryTerms as GlossaryTerm[];
}

function normalizeGlossaryTerm(term: Partial<GlossaryTerm>): GlossaryTerm | null {
	const label = String(term.label || "").trim();
	const description = String(term.description || "").trim();
	const patterns = String(term.patterns || label).trim();
	if (!label || !description || !patterns) {
		return null;
	}
	return {
		label,
		description,
		patterns,
		enabled: term.enabled !== false,
	};
}

function setGlossaryTerms(terms: Partial<GlossaryTerm>[]) {
	const seen = new Set<string>();
	const normalized: GlossaryTerm[] = [];
	for (const term of terms) {
		const item = normalizeGlossaryTerm(term);
		if (!item) {
			continue;
		}
		const key = item.label.toLowerCase();
		if (seen.has(key)) {
			continue;
		}
		seen.add(key);
		normalized.push(item);
	}
	state.glossaryTerms = normalized;
	renderGlossaryList();
	refreshPrompt();
}

function renderGlossaryList() {
	const list = $("#glossaryList");
	if (!list) {
		return;
	}
	const terms = glossaryTerms();
	if (!terms.length) {
		list.textContent = "候補未読み込み";
		return;
	}
	list.innerHTML = "";
	terms.forEach((term, index) => {
		const row = document.createElement("div");
		row.className = "glossary-row";
		row.innerHTML = `
			<input type="checkbox" data-glossary-enabled="${index}" ${term.enabled ? "checked" : ""} />
			<input data-glossary-label="${index}" value="${escapeHtml(term.label)}" aria-label="term label" />
			<input data-glossary-patterns="${index}" value="${escapeHtml(term.patterns)}" aria-label="term patterns" />
			<input data-glossary-description="${index}" value="${escapeHtml(term.description)}" aria-label="term description" />
			<button type="button" data-glossary-remove="${index}" title="remove">×</button>
		`;
		list.appendChild(row);
	});
	$$("[data-glossary-enabled]").forEach((input) => {
		input.addEventListener("change", () => {
			const index = Number(input.dataset.glossaryEnabled);
			glossaryTerms()[index].enabled = input.checked;
			refreshPrompt();
		});
	});
	$$("[data-glossary-label]").forEach((input) => {
		input.addEventListener("input", () => {
			const index = Number(input.dataset.glossaryLabel);
			glossaryTerms()[index].label = input.value;
			if (!glossaryTerms()[index].patterns) {
				glossaryTerms()[index].patterns = input.value;
			}
			refreshPrompt();
		});
	});
	$$("[data-glossary-patterns]").forEach((input) => {
		input.addEventListener("input", () => {
			const index = Number(input.dataset.glossaryPatterns);
			glossaryTerms()[index].patterns = input.value;
			refreshPrompt();
		});
	});
	$$("[data-glossary-description]").forEach((input) => {
		input.addEventListener("input", () => {
			const index = Number(input.dataset.glossaryDescription);
			glossaryTerms()[index].description = input.value;
			refreshPrompt();
		});
	});
	$$("[data-glossary-remove]").forEach((button) => {
		button.addEventListener("click", () => {
			const index = Number(button.dataset.glossaryRemove);
			state.glossaryTerms = glossaryTerms().filter((_, itemIndex) => itemIndex !== index);
			renderGlossaryList();
			refreshPrompt();
		});
	});
}

function escapeHtml(value: string) {
	return value.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function termsFromGlossaryManifest(manifest: any[]): GlossaryTerm[] {
	const terms: GlossaryTerm[] = [];
	for (const item of manifest || []) {
		for (const term of item.terms || []) {
			terms.push({
				label: String(term.label || ""),
				description: String(term.description || ""),
				patterns: String(term.label || ""),
				enabled: true,
			});
		}
	}
	return terms;
}

function log(message: string, data?: any) {
	const line = data ? `${message} ${JSON.stringify(data)}` : message;
	const eventLog = $("#eventLog");
	eventLog.textContent += `${new Date().toLocaleTimeString()}  ${line}\n`;
	eventLog.scrollTop = eventLog.scrollHeight;
}

function setStatus(text, kind = "idle") {
	const status = $("#serverStatus");
	status.innerHTML = `<span class="status-dot ${kind}"></span><span>${text}</span>`;
}

function setFile(slot, filePath) {
	state.files[slot] = filePath || "";
	const label = $(`#${slot}Label`);
	if (label) {
		label.textContent = slot === "logo" && !filePath ? "current repo logo" : shortPath(filePath);
		label.title = filePath || "";
	}
	refreshPrompt();
}

function saveState() {
	if (!state.env) {
		return;
	}
	const fields = {};
	$$("input, select, textarea").forEach((element) => {
		if (!element.id) {
			return;
		}
		fields[element.id] = element.type === "checkbox" ? element.checked : element.value;
	});
	localStorage.setItem(
		STORAGE_KEY,
		JSON.stringify({
			project: state.project,
			files: state.files,
			subtitleMode: state.subtitleMode,
			glossaryTerms: state.glossaryTerms,
			fields,
		}),
	);
}

function loadState() {
	const raw = localStorage.getItem(STORAGE_KEY);
	if (!raw) {
		return;
	}
	try {
		const saved = JSON.parse(raw);
		if (saved.project) {
			setProject(saved.project);
		}
		if (saved.files) {
			Object.entries(saved.files).forEach(([slot, filePath]) => {
				if (slot in state.files) {
					setFile(slot, filePath);
				}
			});
		}
		if (saved.fields) {
			Object.entries(saved.fields).forEach(([id, value]) => {
				const element = $(`#${id}`);
				if (!element) {
					return;
				}
				if (element.type === "checkbox") {
					element.checked = Boolean(value);
				} else {
					element.value = String(value ?? "");
				}
			});
		}
		if (saved.subtitleMode) {
			state.subtitleMode = saved.subtitleMode;
			$$("[data-subtitle-mode]").forEach((button) => {
				button.classList.toggle("selected", button.dataset.subtitleMode === state.subtitleMode);
			});
		}
		if (Array.isArray(saved.glossaryTerms)) {
			state.glossaryTerms = saved.glossaryTerms;
			renderGlossaryList();
		}
	} catch (error) {
		log("saved state ignored", { message: error.message });
	}
}

async function pickFile(slot) {
	const selected = await editApp.pickFile({
		title: `Select ${slot}`,
		filters: fileFilters[slot] || [{ name: "All files", extensions: ["*"] }],
	});
	if (selected) {
		setFile(slot, selected);
	}
}

async function pickTool(id) {
	const selected = await editApp.pickFile({
		title: `Select ${id}`,
		filters: [{ name: "All files", extensions: ["*"] }],
	});
	if (selected) {
		$(`#${id}`).value = selected;
		refreshPrompt();
	}
}

async function pickDirectory(id) {
	const selected = await editApp.pickDirectory({ title: `Select ${id}` });
	if (selected) {
		$(`#${id}`).value = selected;
		refreshPrompt();
	}
}

async function pickOutput() {
	const mode = state.subtitleMode === "punchline" ? "punchline" : "full_transcript";
	const selected = await editApp.pickOutput({
		suggestedName: `codex_edit_${mode}.mp4`,
		outputRoot: activeOutputRoot(),
	});
	if (selected) {
		$("#outputPath").value = selected;
		refreshPrompt();
	}
}

async function createProjectFromForm() {
	const name = formValue("projectName") || `project-${new Date().toISOString().slice(0, 10)}`;
	const id = formValue("projectId") || projectIdFromName(name);
	try {
		const project = await editApp.createProject({ name, id });
		setProject(project);
		log("project ready", { id: project.id, root: project.root });
	} catch (error) {
		log("project create failed", { message: error.message });
	}
}

async function copyAssetsToProject() {
	if (!state.project) {
		await createProjectFromForm();
	}
	if (!state.project) {
		return false;
	}
	try {
		const result = await editApp.copyProjectAssets({
			project: state.project,
			files: state.files,
		});
		setProject(result.project);
		Object.entries(result.files || {}).forEach(([slot, filePath]) => {
			if (slot in state.files) {
				setFile(slot, filePath);
			}
		});
		log("project sources copied", { count: Object.keys(result.files || {}).length, root: result.project.sourceRoot });
		return true;
	} catch (error) {
		log("project copy failed", { message: error.message });
		return false;
	}
}

async function prepareProjectForRun() {
	if (!state.project && !formValue("projectName") && !formValue("projectId")) {
		return true;
	}
	if (!state.project) {
		await createProjectFromForm();
	}
	if (state.project) {
		return copyAssetsToProject();
	}
	return false;
}

function formValue(id) {
	const element = $(`#${id}`);
	if (element.type === "checkbox") {
		return element.checked;
	}
	return element.value;
}

function selectedLabel(id) {
	const element = $(`#${id}`);
	return element?.selectedOptions?.[0]?.textContent?.trim() || formValue(id);
}

function thumbnailMode() {
	const mode = formValue("thumbnailMode") || "standard";
	return mode in thumbnailModes ? mode : "standard";
}

function thumbnailModeConfig() {
	return thumbnailModes[thumbnailMode()];
}

function thumbnailMainColor() {
	const color = formValue("thumbnailMainColor") || "yellow";
	return color in thumbnailMainColors ? color : "yellow";
}

function thumbnailOutputStem() {
	const color = thumbnailMainColor();
	const colorSuffix = color === "yellow" ? "" : `_${color}`;
	return `thumbnail_${thumbnailMode()}${colorSuffix}`;
}

function scoreKind(score) {
	if (typeof score !== "number" || Number.isNaN(score)) {
		return "bad";
	}
	if (score >= 0.82) {
		return "good";
	}
	if (score >= 0.65) {
		return "warn";
	}
	return "bad";
}

function describeSyncReport() {
	const offsets = (state.syncReport?.offsets || {}) as Record<string, any>;
	return Object.entries(offsets)
		.filter(([role]) => role !== "master")
		.map(([role, item]) => ({
			role,
			score: Number(item.score),
			offset: Number(item.offsetSeconds),
			path: item.path || "",
		}));
}

function renderSyncReport() {
	const container = $("#syncReportList");
	if (!container) {
		return;
	}
	const rows = describeSyncReport();
	if (!rows.length) {
		container.textContent = "No camera sync report yet.";
		return;
	}
	container.innerHTML = "";
	rows.forEach((row) => {
		const element = document.createElement("div");
		element.className = `sync-row ${scoreKind(row.score)}`;
		const role = document.createElement("strong");
		role.textContent = row.role;
		const detail = document.createElement("span");
		detail.textContent = `${Number.isFinite(row.offset) ? `${row.offset.toFixed(3)}s` : "offset unknown"} · ${shortPath(row.path)}`;
		const score = document.createElement("span");
		score.className = "score";
		score.textContent = Number.isFinite(row.score) ? row.score.toFixed(3) : "n/a";
		element.append(role, detail, score);
		container.appendChild(element);
	});
}

async function refreshSyncReport() {
	try {
		state.syncReport = await editApp.getSyncReport(buildAppConfig());
	} catch (error) {
		state.syncReport = null;
		log("sync report error", { message: error.message });
	}
	renderSyncReport();
	updateRunSummary();
}

async function loadGlossaryCandidates() {
	try {
		const manifest = await editApp.loadGlossaryCandidates(buildAppConfig());
		const candidates = termsFromGlossaryManifest(manifest);
		setGlossaryTerms([...glossaryTerms(), ...candidates]);
		log("glossary candidates loaded", { count: candidates.length });
	} catch (error) {
		log("glossary load failed", { message: error.message });
	}
}

function addGlossaryTerm() {
	const term = normalizeGlossaryTerm({
		label: formValue("glossaryLabel"),
		patterns: formValue("glossaryPatterns"),
		description: formValue("glossaryDescription"),
		enabled: true,
	});
	if (!term) {
		log("glossary add skipped", { reason: "用語・検出語・解説を入力してください" });
		return;
	}
	setGlossaryTerms([...glossaryTerms(), term]);
	$("#glossaryLabel").value = "";
	$("#glossaryPatterns").value = "";
	$("#glossaryDescription").value = "";
}

function pythonExe() {
	return formValue("pythonPath") || state.env?.pythonExe || "python";
}

function ffprobeExe() {
	return formValue("ffprobePath") || "ffprobe";
}

function stillOutputPath(inputVideo, outputPath) {
	if (outputPath && /\.(png|jpg|jpeg)$/i.test(outputPath)) {
		return outputPath;
	}
	const source = inputVideo || outputPath || "preview";
	return `${source.replace(/\.[^.\\/]+$/, "")}_still.png`;
}

function thumbnailContactSheetPath() {
	return joinPath(
		activeOutputRoot() || "output",
		"thumbnails",
		`${thumbnailOutputStem()}_candidates_contact_sheet.jpg`,
	);
}

function thumbnailSourceRoot() {
	return state.env?.thumbnailSourceRoot || joinPath(activeSourceRoot() || "source", "thumbnail", "etype260515_p_takei");
}

function personBboxesDir() {
	return joinPath(activeOutputRoot() || "output", "reports", "person_bboxes");
}

function personEditPlansDir() {
	return joinPath(activeOutputRoot() || "output", "reports", "person_edit_plans");
}

function referencePersonBboxesDir() {
	return joinPath(activeOutputRoot() || "output", "reports", "reference_person_bboxes");
}

function referenceEditPlansDir() {
	return joinPath(activeOutputRoot() || "output", "reports", "reference_edit_plans");
}

function referenceEditProfilePath() {
	return joinPath(activeOutputRoot() || "output", "reports", "reference_edit_profile.json");
}

function selectedAnalysisVideos() {
	return [state.files.masterVideo, state.files.rightCloseVideo, state.files.leftCloseVideo].filter(Boolean);
}

function withRuntimeConfig(command) {
	return command;
}

function scriptPath(scriptName) {
	return state.env?.scriptsRoot ? `${state.env.scriptsRoot}\\${scriptName}` : scriptName;
}

function buildPresetCommand() {
	const action = formValue("workflowAction");
	return {
		command: withRuntimeConfig([pythonExe(), scriptPath("video_edit_run.py"), "--action", action]),
		reason: "",
	};
}

function quoteArg(arg) {
	if (/^[A-Za-z0-9_./:=+-]+$/.test(arg)) {
		return arg;
	}
	return `"${arg.replace(/"/g, '\\"')}"`;
}

function refreshCommand() {
	const { command, reason } = buildPresetCommand();
	$("#commandPreview").value = command ? command.map(quoteArg).join(" ") : reason;
}

function validateSelections() {
	const errors = [];
	const warnings = [];
	const ok = [];
	const action = formValue("workflowAction");
	const script = formValue("renderScript");
	const outputPath = $("#outputPath").value.trim();
	const inputVideo = formValue("inputVideoPath").trim();

	if (action === "render-selected") {
		if (!outputPath) {
			errors.push("出力先を指定してください。");
		} else {
			ok.push(`出力: ${shortPath(outputPath)}`);
		}
		if (script === "render_app_interview.py") {
			if (!state.files.masterVideo) {
				errors.push("Dropped-file interview render にはマスター動画が必要です。");
			}
			if (!state.files.rightCloseVideo && !state.files.leftCloseVideo) {
				warnings.push("アップ素材が未指定なので、実質1カメラのレンダーになります。");
			}
			if (state.files.rightCloseVideo || state.files.leftCloseVideo) {
				warnings.push(
					"新規マルチカム素材は、先に Auto-sync dropped cameras を実行して app_sync_offsets.json を作るのが安全です。",
				);
			}
		}
		if (formValue("shortenSilence")) {
			warnings.push("無音詰めONの場合、指定した出力尺からさらに短くなります。尺を固定したい場合はOFFにしてください。");
		}
	}

	if (action === "auto-sync-dropped") {
		if (!state.files.masterVideo) {
			errors.push("自動同期にはマスター動画が必要です。");
		}
		if (!state.files.rightCloseVideo && !state.files.leftCloseVideo && !state.files.externalAudio) {
			errors.push("自動同期には右アップ・左アップ・別録り音声のいずれかが必要です。");
		}
		ok.push("カメラ/別録り音声の同期結果は output\\reports\\app_sync_offsets.json に保存されます。");
	}

	if (action === "generate-thumbnails") {
		ok.push(
			`サムネ候補をソース画像の枚数ぶん、${thumbnailModeConfig().label} / ${thumbnailMainColors[thumbnailMainColor()]} で output\\thumbnails に生成します。`,
		);
		ok.push(`確認用: ${shortPath(thumbnailContactSheetPath())}`);
		ok.push("素材は Downloads の etype260515 p-takei から import します。");
	}

	if (action === "analyze-person-edit-metadata") {
		const videos = selectedAnalysisVideos();
		ok.push(`人物bbox: ${shortPath(personBboxesDir())}`);
		ok.push(`編集プラン: ${shortPath(personEditPlansDir())}`);
		ok.push(`解析間隔: ${formValue("personFpsSample")} fps`);
		if (videos.length) {
			ok.push(`解析対象: 選択済み動画 ${videos.length}本`);
		} else {
			ok.push("解析対象: source/video と 2cam/3cam root");
		}
		if (formValue("personMaxSeconds")) {
			warnings.push("Analysis max seconds が入っているため、全尺ではなくテスト解析になります。");
		}
	}

	if (action === "analyze-reference-video") {
		if (!state.files.referenceVideo) {
			errors.push("参考動画を1本ドラッグ&ドロップしてください。");
		}
		ok.push("参考動画は60秒以内として解析します。超えている場合は実行時に止めます。");
		ok.push(`参考プロファイル: ${shortPath(referenceEditProfilePath())}`);
		ok.push(`参考人物bbox: ${shortPath(referencePersonBboxesDir())}`);
		ok.push(`参考編集プラン: ${shortPath(referenceEditPlansDir())}`);
	}

	if (action === "replace-sound2" && !outputPath) {
		errors.push("音声差し替えには出力先が必要です。");
	}
	if (action === "shorten-input" && (!inputVideo || !outputPath)) {
		errors.push("無音詰めには入力動画と出力先が必要です。");
	}
	if (["extract-still", "verify-duration", "verify-audio"].includes(action) && !inputVideo) {
		errors.push("この工程には Verification / input video が必要です。");
	}

	const audioSource = formValue("audioSource");
	if (audioSource === "external-if-selected") {
		if (state.files.externalAudio) {
			ok.push(`音声: 別録り ${shortPath(state.files.externalAudio)}`);
		} else {
			warnings.push("別録り音声が未指定なので、レンダーはマスター動画音声にフォールバックします。");
		}
	}
	if (audioSource === "rightCloseVideo" && !state.files.rightCloseVideo) {
		warnings.push("右アップ音声が未指定なので、レンダーはマスター動画音声にフォールバックします。");
	}
	if (audioSource === "leftCloseVideo" && !state.files.leftCloseVideo) {
		warnings.push("左アップ音声が未指定なので、レンダーはマスター動画音声にフォールバックします。");
	}

	ok.push(`工程: ${selectedLabel("workflowAction")}`);
	ok.push(`字幕: ${state.subtitleMode}`);
	ok.push(
		formValue("termExplanations")
			? `用語解説: ON (${glossaryTerms().filter((term) => term.enabled).length}語)`
			: "用語解説: OFF",
	);
	ok.push(formValue("audioDenoise") ? `ノイズ低減: ON (${formValue("audioDenoiseStrength")})` : "ノイズ低減: OFF");
	ok.push(formValue("shortenSilence") ? "無音詰め: ON" : "無音詰め: OFF");
	const syncRows = describeSyncReport();
	if (syncRows.length) {
		const weakest = syncRows.reduce((min, row) => (row.score < min.score ? row : min), syncRows[0]);
		ok.push(`前回同期: ${weakest.role} score ${weakest.score.toFixed(3)}`);
		if (weakest.score < 0.65) {
			warnings.push("前回の自動同期スコアが低い素材があります。短尺QAで音ズレ確認してください。");
		}
	}
	return { errors, warnings, ok };
}

function updateRunSummary() {
	const list = $("#runChecklist");
	if (!list) {
		return;
	}
	const validation = validateSelections();
	const items = [
		...validation.errors.map((text) => ({ text, kind: "error" })),
		...validation.warnings.map((text) => ({ text, kind: "warn" })),
		...validation.ok.slice(0, 5).map((text) => ({ text, kind: "ok" })),
	];
	list.innerHTML = "";
	items.forEach((item) => {
		const li = document.createElement("li");
		li.className = item.kind;
		li.textContent = item.text;
		list.appendChild(li);
	});
}

function buildPrompt() {
	const outputPath = $("#outputPath").value || "(choose an output path under the video_edit folder)";
	const lines = [
		"You are working in C:\\Users\\yurin\\Desktop\\video_edit.",
		"Create or run the video edit requested by the Electron operator UI.",
		"",
		"Use the existing pipeline and docs first:",
		"- Read docs\\video_edit_method.md for the current ST7_7550 workflow.",
		"- Prefer scripts\\render_1min_onepass_ffmpeg.py for the current 1-minute preset.",
		"- Prefer scripts\\render_final_png_overlays.py for current 5-minute PNG-overlay renders.",
		"- Use scripts\\analyze_person_edit_metadata.py before edit planning when person position/crop decisions matter.",
		"- If a reference video is selected, analyze it first and use output\\reports\\reference_edit_profile.json as the style/layout target.",
		"- Use scripts\\generate_thumbnail_candidates.py --import-assets --main-color <color> plus the selected thumbnail layout flag for thumbnail candidate generation.",
		"- Keep existing user changes in the repo; do not revert unrelated files.",
		"",
		"Operator selections:",
		`- Edit preset: ${formValue("editPreset")}`,
		`- Direct workflow action: ${formValue("workflowAction")}`,
		`- Thumbnail layout: ${thumbnailMode()} (${thumbnailModeConfig().flag || "no extra flag"})`,
		`- Thumbnail main color: ${thumbnailMainColor()}`,
		`- Person analysis: ${formValue("personFpsSample")} fps, model ${formValue("personModel")}, confidence ${formValue("personConfidence")}, max seconds ${formValue("personMaxSeconds") || "all"}, limit ${formValue("personLimit") || "all"}`,
		`- Reference video: ${state.files.referenceVideo || "(not selected)"}`,
		`- Reference profile: ${referenceEditProfilePath()}`,
		`- Render script: ${formValue("renderScript")}`,
		`- Multicam mode: ${formValue("multicamMode")}`,
		`- Subtitle mode: ${state.subtitleMode}`,
		`- Audio source: ${formValue("audioSource")}`,
		`- Audio denoise: ${formValue("audioDenoise")} strength ${formValue("audioDenoiseStrength")}`,
		`- Preview start: ${formValue("previewStart")} seconds`,
		`- Output duration: ${formValue("previewDuration")} seconds`,
		`- Shorten long silence: ${formValue("shortenSilence")}`,
		`- Silence options: min ${formValue("minSilence")}s, keep ${formValue("keepSilence")}s, noise ${formValue("silenceNoise")}, keep uncut ${formValue("keepUncut")}`,
		`- Rebuild base: ${formValue("rebuildBase")}`,
		`- Reuse existing overlays: ${formValue("skipSubtitleRegeneration")}`,
		`- Reclassify speakers: ${formValue("reclassifySpeakers")}`,
		`- Auto context/speaker camera cuts: ${formValue("autoContextCuts")}`,
		`- Place cuts in short dialogue gaps: ${formValue("naturalDialogueCuts")}`,
		`- Term explanations: ${formValue("termExplanations")} (${
			glossaryTerms()
				.filter((term) => term.enabled)
				.map((term) => term.label)
				.join(", ") || "none"
		})`,
		`- Output path: ${outputPath}`,
		`- Active project: ${state.project ? `${state.project.name} (${state.project.root})` : "(none; using workspace defaults)"}`,
		`- Project source root: ${activeSourceRoot() || "(not set)"}`,
		`- Project output root: ${activeOutputRoot() || "(not set)"}`,
		`- Still extraction time: ${formValue("stillTime") || "00:00:25"}`,
		`- Thumbnail source images: ${joinPath(thumbnailSourceRoot(), "ST-*.jpg")}`,
		`- Thumbnail contact sheet: ${thumbnailContactSheetPath()}`,
		`- Person bbox output: ${personBboxesDir()}`,
		`- Person edit plan output: ${personEditPlansDir()}`,
		`- Reference person edit plan output: ${referenceEditPlansDir()}`,
		`- Source root override: ${formValue("sourceRoot") || "(not set)"}`,
		`- Python: ${pythonExe()}`,
		`- FFmpeg: ${formValue("ffmpegPath") || "(script default)"}`,
		`- FFprobe: ${ffprobeExe()}`,
		"",
		"Dropped assets:",
		`- Master/day video: ${state.files.masterVideo || "(use current repo default if preset supports it)"}`,
		`- Right close-up/person 1: ${state.files.rightCloseVideo || "(use current repo default if preset supports it)"}`,
		`- Left close-up/person 2: ${state.files.leftCloseVideo || "(use current repo default if preset supports it)"}`,
		`- Reference style video: ${state.files.referenceVideo || "(not selected)"}`,
		`- External audio: ${state.files.externalAudio || "(not selected)"}`,
		`- Logo: ${state.files.logo || "(use current repo logo)"}`,
		"",
		"Style selections:",
		`- Subtitle font size target: ${formValue("subtitleSize")}`,
		`- Subtitle highlight color: ${formValue("highlightColor")}`,
		`- Subtitle box opacity: ${formValue("boxOpacity")} percent`,
		`- Top-left text: ${formValue("titleText")}`,
		`- Top-left text size: ${formValue("titleSize")}`,
		`- Right-top logo height: ${formValue("logoHeight")} px`,
		`- Punchline list:\n${formValue("punchlineText") || "(use existing script list)"}`,
		"",
		"Expected behavior:",
		"- If external audio is selected, sync it or clearly report if existing offset data cannot be reused.",
		"- If no external audio is selected, use the selected camera audio source.",
		"- Support interview/multicam source roles: master, person 1 close-up, person 2 close-up.",
		"- For person-aware crop/cut planning, analyze source videos first, then use output\\reports\\person_edit_plans as metadata for camera/crop decisions.",
		"- Reflect the reference profile in the edit: match person size, layout, face direction when possible, and visual tone (brightness, contrast, saturation, warmth).",
		"- For full subtitles, use corrected SRT when available.",
		"- For catchy subtitles, use the punchline overlay mode.",
		"- If punchline text/timing/style changed, update the relevant generator script or data in the smallest maintainable way before regenerating overlays.",
		"- If style/logo/title settings are not exposed by CLI flags, update the Python style/title scripts carefully and regenerate PNG overlays.",
		"- Use source root override for 2cam/3cam inputs if it is set.",
		`- For thumbnail generation, produce one candidate per source thumbnail image with the selected mode (${thumbnailMode()}) and main color (${thumbnailMainColor()}), write the mode/color-specific contact sheet at ${thumbnailContactSheetPath()}, keep the fixed title/hook from docs\\video_edit_method.md, avoid faces unless the mode intentionally allows slight title overlap, do not draw a duration chip, and use the cropped Engineer Type logo with small even padding.`,
		"- Make minimal script changes needed for this request, then render or provide the exact command if rendering is blocked.",
		"- Report the output file path and any limitations.",
	];
	return lines.join("\n");
}

function buildAppConfig() {
	return {
		project: {
			id: state.project?.id || "",
			name: state.project?.name || "",
			root: state.project?.root || "",
			sourceRoot: activeSourceRoot(),
			outputRoot: activeOutputRoot(),
		},
		assets: {
			masterVideo: state.files.masterVideo,
			rightCloseVideo: state.files.rightCloseVideo,
			leftCloseVideo: state.files.leftCloseVideo,
			referenceVideo: state.files.referenceVideo,
			externalAudio: state.files.externalAudio,
			logo: state.files.logo,
			sourceRoot: formValue("sourceRoot"),
		},
		render: {
			editPreset: formValue("editPreset"),
			workflowAction: formValue("workflowAction"),
			thumbnailMode: thumbnailMode(),
			thumbnailMainColor: thumbnailMainColor(),
			renderScript: formValue("renderScript"),
			outputPath: $("#outputPath").value,
			syncOffsetsPath: syncReportPath(),
			subtitleMode: state.subtitleMode,
			multicamMode: formValue("multicamMode"),
			audioSource: formValue("audioSource"),
			audioDenoise: formValue("audioDenoise"),
			audioDenoiseStrength: Number(formValue("audioDenoiseStrength") || 10),
			previewStart: Number(formValue("previewStart") || 0),
			previewDuration: Number(formValue("previewDuration") || 60),
			rebuildBase: formValue("rebuildBase"),
			skipSubtitleRegeneration: formValue("skipSubtitleRegeneration"),
			reclassifySpeakers: formValue("reclassifySpeakers"),
			autoContextCuts: formValue("autoContextCuts"),
			naturalDialogueCuts: formValue("naturalDialogueCuts"),
			termExplanations: formValue("termExplanations"),
			shortenSilence: formValue("shortenSilence"),
			minSilence: Number(formValue("minSilence") || 3),
			keepSilence: Number(formValue("keepSilence") || 2),
			silenceNoise: formValue("silenceNoise") || "-30dB",
			keepUncut: formValue("keepUncut"),
		},
		workflow: {
			inputVideoPath: formValue("inputVideoPath"),
			replaceAudioInput: formValue("replaceAudioInput"),
			stillTime: formValue("stillTime") || "00:00:25",
			stillOutputPath: stillOutputPath(formValue("inputVideoPath") || $("#outputPath").value, $("#outputPath").value),
			noAudioClips: formValue("noAudioClips"),
			transcribeReview: formValue("transcribeReview"),
			reviewModel: formValue("reviewModel") || "medium",
		},
		analysis: {
			personFpsSample: Number(formValue("personFpsSample") || 1),
			personModel: formValue("personModel") || "yolov8n.pt",
			personConfidence: Number(formValue("personConfidence") || 0.35),
			personMaxSeconds: formValue("personMaxSeconds") ? Number(formValue("personMaxSeconds")) : null,
			personLimit: formValue("personLimit") ? Number(formValue("personLimit")) : null,
			personNoMulticamRoot: formValue("personNoMulticamRoot"),
			personBboxesDir: personBboxesDir(),
			personEditPlansDir: personEditPlansDir(),
			referencePersonBboxesDir: referencePersonBboxesDir(),
			referenceEditPlansDir: referenceEditPlansDir(),
			referenceEditProfilePath: referenceEditProfilePath(),
		},
		style: {
			subtitleSize: Number(formValue("subtitleSize") || 80),
			highlightColor: formValue("highlightColor"),
			boxOpacity: Number(formValue("boxOpacity") || 72),
			titleText: formValue("titleText"),
			titleSize: Number(formValue("titleSize") || 64),
			logoHeight: Number(formValue("logoHeight") || 48),
			punchlineText: formValue("punchlineText"),
		},
		glossary: {
			enabled: formValue("termExplanations"),
			terms: glossaryTerms(),
		},
		tools: {
			python: formValue("pythonPath"),
			ffmpeg: formValue("ffmpegPath"),
			ffprobe: formValue("ffprobePath"),
		},
		thumbnails: {
			mode: thumbnailMode(),
			modeFlag: thumbnailModeConfig().flag,
			mainColor: thumbnailMainColor(),
			sourceRoot: thumbnailSourceRoot(),
			sourceGlob: joinPath(thumbnailSourceRoot(), "ST-*.jpg"),
			contactSheet: thumbnailContactSheetPath(),
			outputRoot: joinPath(activeOutputRoot(), "thumbnails"),
			importAssets: formValue("workflowAction") === "generate-thumbnails",
		},
	};
}

function refreshPrompt() {
	refreshCommand();
	updateRunSummary();
	$("#promptPreview").value = buildPrompt();
	saveState();
}

async function runPreset() {
	if (!(await prepareProjectForRun())) {
		setStatus("Project error", "idle");
		return;
	}
	refreshCommand();
	const validation = validateSelections();
	if (validation.errors.length) {
		updateRunSummary();
		setStatus("Check required fields", "idle");
		log("direct run blocked", { errors: validation.errors });
		return;
	}
	const { command, reason } = buildPresetCommand();
	if (!command) {
		log("direct run unavailable", { reason });
		return;
	}
	setStatus("Preset running", "busy");
	log("command/exec", { command });
	try {
		const result = await editApp.execCodexCommand({
			command,
			timeoutMs: 60 * 60 * 1000,
			appConfig: buildAppConfig(),
		});
		if (result?.stdout) {
			log("stdout", { text: result.stdout });
		}
		if (result?.stderr) {
			log("stderr", { text: result.stderr });
		}
		log("command completed", { exitCode: result?.exitCode });
		if (formValue("workflowAction") === "auto-sync-dropped" && result?.exitCode === 0) {
			await refreshSyncReport();
		}
		if (formValue("workflowAction") === "generate-thumbnails" && result?.exitCode === 0) {
			log("thumbnail contact sheet", { path: thumbnailContactSheetPath() });
		}
		if (formValue("workflowAction") === "analyze-person-edit-metadata" && result?.exitCode === 0) {
			log("person analysis outputs", { bboxes: personBboxesDir(), plans: personEditPlansDir() });
		}
		if (formValue("workflowAction") === "analyze-reference-video" && result?.exitCode === 0) {
			log("reference analysis output", { profile: referenceEditProfilePath() });
		}
		setStatus(result?.exitCode === 0 ? "Codex ready" : "Command failed", result?.exitCode === 0 ? "ready" : "idle");
	} catch (error) {
		setStatus("Command error", "idle");
		log("command error", { message: error.message });
	}
}

async function sendRequest() {
	if (!(await prepareProjectForRun())) {
		setStatus("Project error", "idle");
		return;
	}
	refreshPrompt();
	setStatus("Codex running", "busy");
	log("turn/start");
	try {
		await editApp.startCodexTurn({
			settings: {
				model: $("#modelName")?.value || "",
				effort: "medium",
			},
			prompt: $("#promptPreview").value,
		});
	} catch (error) {
		setStatus("Codex error", "idle");
		log("error", { message: error.message });
	}
}

function handleNotification(message) {
	const method = message.method || "notification";
	const params = message.params || {};
	if (method === "item/agentMessage/delta") {
		log("agent", { delta: params.delta || params.text || params });
		return;
	}
	if (method === "item/commandExecution/outputDelta") {
		log("command", { text: params.delta || params.text || params });
		return;
	}
	if (method === "command/exec/outputDelta") {
		log("command", { text: params.delta || params.text || params });
		return;
	}
	if (method === "turn/completed") {
		setStatus("Codex idle", "ready");
	}
	log(method, params);
}

function initDropZones() {
	$$(".drop-zone").forEach((zone) => {
		const slot = zone.dataset.slot;
		zone.addEventListener("dragover", (event) => {
			event.preventDefault();
			zone.classList.add("dragging");
		});
		zone.addEventListener("dragleave", () => zone.classList.remove("dragging"));
		zone.addEventListener("drop", (event) => {
			event.preventDefault();
			zone.classList.remove("dragging");
			const file = event.dataTransfer.files[0];
			if (file) {
				setFile(slot, editApp.filePath(file));
			}
		});
	});
}

function bindEvents() {
	$$("[data-pick]").forEach((button) => {
		button.addEventListener("click", () => pickFile(button.dataset.pick));
	});
	$$("[data-pick-tool]").forEach((button) => {
		button.addEventListener("click", () => pickTool(button.dataset.pickTool));
	});
	$$("[data-pick-dir]").forEach((button) => {
		button.addEventListener("click", () => pickDirectory(button.dataset.pickDir));
	});
	$("#pickOutput").addEventListener("click", pickOutput);
	$("#createProject").addEventListener("click", createProjectFromForm);
	$("#copyProjectAssets").addEventListener("click", copyAssetsToProject);
	$("#projectName").addEventListener("input", () => {
		if (!formValue("projectId")) {
			$("#projectId").value = projectIdFromName(formValue("projectName"));
		}
		refreshPrompt();
	});
	$("#refreshCommand").addEventListener("click", refreshCommand);
	$("#refreshPrompt").addEventListener("click", refreshPrompt);
	$("#refreshSyncReport").addEventListener("click", refreshSyncReport);
	$("#loadGlossaryCandidates").addEventListener("click", loadGlossaryCandidates);
	$("#addGlossaryTerm").addEventListener("click", addGlossaryTerm);
	$("#runPreset").addEventListener("click", runPreset);
	$("#sendRequest").addEventListener("click", sendRequest);
	$("#interrupt").addEventListener("click", async () => {
		await editApp.interruptCodex();
		log("turn/interrupt requested");
	});
	$("#openOutput").addEventListener("click", () => {
		const output = $("#outputPath").value;
		if (output) {
			editApp.showPath(output);
		}
	});
	$("#openThumbnails").addEventListener("click", () => {
		editApp.showPath(thumbnailContactSheetPath());
	});
	$$("input, select, textarea").forEach((element) => {
		element.addEventListener("input", refreshPrompt);
		element.addEventListener("change", refreshPrompt);
	});
	$("#editPreset").addEventListener("change", () => {
		const mapping = {
			"current-1min-color": "render_1min_color_matched.py",
			"current-onepass": "render_1min_onepass_ffmpeg.py",
			"current-5min": "render_final_png_overlays.py",
			"new-interview": "render_app_interview.py",
		};
		const durations = {
			"current-1min-color": 60,
			"current-onepass": 85,
			"current-5min": 300,
			"new-interview": 60,
		};
		if (mapping[formValue("editPreset")]) {
			$("#renderScript").value = mapping[formValue("editPreset")];
		}
		if (durations[formValue("editPreset")]) {
			$("#previewDuration").value = String(durations[formValue("editPreset")]);
		}
		refreshPrompt();
	});
	$$("[data-subtitle-mode]").forEach((button) => {
		button.addEventListener("click", () => {
			$$("[data-subtitle-mode]").forEach((item) => {
				item.classList.remove("selected");
			});
			button.classList.add("selected");
			state.subtitleMode = button.dataset.subtitleMode;
			refreshPrompt();
		});
	});
	$$(".step-button").forEach((button) => {
		button.addEventListener("click", () => {
			$$(".step-button").forEach((item) => {
				item.classList.remove("active");
			});
			button.classList.add("active");
			const panel = document.querySelector(`[data-panel="${button.dataset.section}"]`);
			panel?.scrollIntoView({ behavior: "smooth", block: "start" });
		});
	});
}

async function init() {
	state.env = await editApp.getEnvironment();
	$("#workspacePath").textContent = state.env.videoEditRoot;
	$("#outputPath").value = state.env.knownOutputs[0];
	$("#inputVideoPath").value = state.env.knownOutputs[0];
	$("#replaceAudioInput").value = state.env.knownOutputs[2];
	$("#pythonPath").value = state.env.pythonExe;
	$("#sourceRoot").value = "C:\\Users\\yurin\\Downloads\\cdc260515 mov\\cdc260515 mov";
	$("#punchlineText").value = defaultPunchlines;
	state.glossaryTerms = defaultGlossaryTerms;
	loadState();
	renderGlossaryList();
	initDropZones();
	bindEvents();
	refreshPrompt();

	editApp.onServerReady(() => {
		setStatus("Codex ready", "ready");
		log("server ready");
	});
	editApp.onServerError((payload) => {
		setStatus("Codex error", "idle");
		log("server error", payload);
	});
	editApp.onServerExit((payload) => {
		setStatus("Codex exited", "idle");
		log("server exit", payload);
	});
	editApp.onServerStderr((payload) => log("stderr", payload));
	editApp.onServerNotification(handleNotification);
	refreshSyncReport();
}

init().catch((error) => {
	log("init error", { message: error.message });
});
