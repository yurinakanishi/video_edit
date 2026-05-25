const state = {
  env: null,
  files: {
    masterVideo: "",
    rightCloseVideo: "",
    leftCloseVideo: "",
    externalAudio: "",
    logo: "",
  },
  subtitleMode: "full",
  syncReport: null,
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
  externalAudio: [{ name: "Audio or video", extensions: ["wav", "mp3", "aac", "m4a", "mp4", "mov"] }],
  logo: [{ name: "Image", extensions: ["png", "jpg", "jpeg", "webp"] }],
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));
const STORAGE_KEY = "video-edit-app-state-v1";

function shortPath(value) {
  if (!value) {
    return "not selected";
  }
  const parts = value.split(/[\\/]/);
  return parts.length > 2 ? `${parts.at(-2)}\\${parts.at(-1)}` : value;
}

function log(message, data) {
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
      files: state.files,
      subtitleMode: state.subtitleMode,
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
  } catch (error) {
    log("saved state ignored", { message: error.message });
  }
}

async function pickFile(slot) {
  const selected = await window.editApp.pickFile({
    title: `Select ${slot}`,
    filters: fileFilters[slot] || [{ name: "All files", extensions: ["*"] }],
  });
  if (selected) {
    setFile(slot, selected);
  }
}

async function pickTool(id) {
  const selected = await window.editApp.pickFile({
    title: `Select ${id}`,
    filters: [{ name: "All files", extensions: ["*"] }],
  });
  if (selected) {
    $(`#${id}`).value = selected;
    refreshPrompt();
  }
}

async function pickDirectory(id) {
  const selected = await window.editApp.pickDirectory({ title: `Select ${id}` });
  if (selected) {
    $(`#${id}`).value = selected;
    refreshPrompt();
  }
}

async function pickOutput() {
  const mode = state.subtitleMode === "punchline" ? "punchline" : "full_transcript";
  const selected = await window.editApp.pickOutput(`codex_edit_${mode}.mp4`);
  if (selected) {
    $("#outputPath").value = selected;
    refreshPrompt();
  }
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
  const offsets = state.syncReport?.offsets || {};
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
    state.syncReport = await window.editApp.getSyncReport();
  } catch (error) {
    state.syncReport = null;
    log("sync report error", { message: error.message });
  }
  renderSyncReport();
  updateRunSummary();
}

function pythonExe() {
  return formValue("pythonPath") || state.env?.pythonExe || "python";
}

function ffprobeExe() {
  return formValue("ffprobePath") || "ffprobe";
}

function ffmpegExe() {
  return formValue("ffmpegPath") || "ffmpeg";
}

function stillOutputPath(inputVideo, outputPath) {
  if (outputPath && /\.(png|jpg|jpeg)$/i.test(outputPath)) {
    return outputPath;
  }
  const source = inputVideo || outputPath || "preview";
  return source.replace(/\.[^.\\/]+$/, "") + "_still.png";
}

function psQuote(value) {
  return `'${String(value).replace(/'/g, "''")}'`;
}

function withSourceRoot(command) {
  const sourceRoot = formValue("sourceRoot");
  const appConfigPath = state.env?.appConfigPath;
  if (!sourceRoot && !appConfigPath) {
    return command;
  }
  const setup = ["$env:PYTHONUTF8 = '1'"];
  if (sourceRoot) {
    setup.push(`$env:VIDEO_EDIT_SOURCE_ROOT = ${psQuote(sourceRoot)}`);
  }
  if (appConfigPath) {
    setup.push(`$env:VIDEO_EDIT_APP_CONFIG = ${psQuote(appConfigPath)}`);
  }
  const script = [...setup, `& ${command.map(psQuote).join(" ")}`].join("; ");
  return ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script];
}

function scriptPath(scriptName) {
  return state.env?.scriptsRoot ? `${state.env.scriptsRoot}\\${scriptName}` : scriptName;
}

function addSilenceArgs(command) {
  if (!formValue("shortenSilence")) {
    command.push("--no-shorten-silence");
  }
  command.push("--min-silence", String(Number(formValue("minSilence") || 3)));
  command.push("--keep-silence", String(Number(formValue("keepSilence") || 2)));
  command.push("--silence-noise", formValue("silenceNoise") || "-30dB");
  if (formValue("keepUncut")) {
    command.push("--keep-uncut");
  }
}

function addAudioArgs(command) {
  if (!formValue("audioDenoise")) {
    command.push("--no-audio-denoise");
  }
  command.push("--audio-denoise-strength", String(Number(formValue("audioDenoiseStrength") || 10)));
}

function buildRenderCommand() {
  const script = formValue("renderScript");
  const subtitleMode = state.subtitleMode;
  const outputPath = $("#outputPath").value;
  if (!outputPath) {
    return {
      command: null,
      reason: "Choose an output path before running a preset script.",
    };
  }

  if (script === "render_app_interview.py") {
    return { command: withSourceRoot([pythonExe(), scriptPath(script)]), reason: "" };
  }

  const mode = subtitleMode === "none" ? "none" : subtitleMode === "punchline" ? "punchline" : "full";
  const command = [pythonExe(), scriptPath(script), "--mode", mode, "--output", outputPath];

  if (script === "render_1min_onepass_ffmpeg.py") {
    command.push(
      "--preview-start",
      String(Number(formValue("previewStart") || 0)),
      "--preview-duration",
      String(Number(formValue("previewDuration") || 60)),
    );
  }
  if (script === "render_final_png_overlays.py" || script === "render_1min_color_matched.py") {
    command.push("--duration", String(Number(formValue("previewDuration") || 60)));
  }
  if (script === "render_1min_color_matched.py") {
    if (formValue("rebuildBase")) {
      command.push("--rebuild-base");
    }
    if (formValue("skipSubtitleRegeneration")) {
      command.push("--skip-subtitle-regeneration");
    }
    if (formValue("reclassifySpeakers")) {
      command.push("--reclassify-speakers");
    }
  }
  if (script === "render_1min_onepass_ffmpeg.py" && formValue("skipSubtitleRegeneration")) {
    command.push("--skip-subtitle-regeneration");
  }

  addAudioArgs(command);
  addSilenceArgs(command);
  return { command: withSourceRoot(command), reason: "" };
}

function buildPresetCommand() {
  const action = formValue("workflowAction");
  const inputVideo = formValue("inputVideoPath") || $("#outputPath").value;
  const replaceInput = formValue("replaceAudioInput") || inputVideo;
  const outputPath = $("#outputPath").value;

  if (action === "render-selected") {
    return buildRenderCommand();
  }

  const simplePythonScripts = {
    "subtitle-review": "subtitle_review_cycle.py",
    "generate-punchlines": "generate_punchline_png_overlays.py",
    "generate-full-overlays": "generate_full_transcript_png_overlays.py",
    "analyze-blocking": "analyze_multicam_blocking.py",
    "auto-sync-dropped": "auto_sync_app_sources.py",
    "transcribe-align": "transcribe_align_st7_7550_multicam.py",
    "compare-all-cameras": "transcribe_compare_all_st7_7550_multicam.py",
    "refine-strong-wave": "refine_st7_7550_strong_wave_offsets.py",
    "build-base": "build_st7_7550_strong_transcript_multicam.py",
    "transcribe-sound2": "transcribe_sound2.py",
    "compare-sound2": "compare_sound2_transcripts.py",
    "refine-sound2": "refine_sound2_audio_offset.py",
  };

  if (action in simplePythonScripts) {
    const command = [pythonExe(), scriptPath(simplePythonScripts[action])];
    if (action === "subtitle-review") {
      if (formValue("noAudioClips")) {
        command.push("--no-audio-clips");
      }
      if (formValue("transcribeReview")) {
        command.push("--transcribe-review", "--review-model", formValue("reviewModel") || "medium");
      }
    }
    return { command: withSourceRoot(command), reason: "" };
  }

  if (action === "replace-sound2") {
    if (!outputPath) {
      return { command: null, reason: "Choose an output path before replacing audio." };
    }
    const command = [pythonExe(), scriptPath("replace_audio_with_sound2.py"), "--video", replaceInput, "--output", outputPath];
    addSilenceArgs(command);
    return { command: withSourceRoot(command), reason: "" };
  }

  if (action === "shorten-input") {
    if (!inputVideo || !outputPath) {
      return { command: null, reason: "Choose an input video and output path for silence shortening." };
    }
    return {
      command: withSourceRoot([
        pythonExe(),
        scriptPath("shorten_silences.py"),
        "--input",
        inputVideo,
        "--output",
        outputPath,
        "--min-silence",
        String(Number(formValue("minSilence") || 3)),
        "--keep-silence",
        String(Number(formValue("keepSilence") || 2)),
        "--noise",
        formValue("silenceNoise") || "-30dB",
      ]),
      reason: "",
    };
  }

  if (action === "extract-still") {
    if (!inputVideo) {
      return { command: null, reason: "Choose an input video before extracting a still." };
    }
    return {
      command: withSourceRoot([
        ffmpegExe(),
        "-y",
        "-ss",
        formValue("stillTime") || "00:00:25",
        "-i",
        inputVideo,
        "-frames:v",
        "1",
        "-update",
        "1",
        stillOutputPath(inputVideo, outputPath),
      ]),
      reason: "",
    };
  }

  if (action === "verify-duration") {
    if (!inputVideo) {
      return { command: null, reason: "Choose a verification input video." };
    }
    return {
      command: withSourceRoot([ffprobeExe(), "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", inputVideo]),
      reason: "",
    };
  }

  if (action === "verify-audio") {
    if (!inputVideo) {
      return { command: null, reason: "Choose a verification input video." };
    }
    return {
      command: withSourceRoot([ffprobeExe(), "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=codec_name,sample_rate,channels", "-of", "json", inputVideo]),
      reason: "",
    };
  }

  return { command: null, reason: `Unknown workflow action: ${action}` };
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
        warnings.push("新規マルチカム素材は、先に Auto-sync dropped cameras を実行して app_sync_offsets.json を作るのが安全です。");
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
    if (!state.files.rightCloseVideo && !state.files.leftCloseVideo) {
      errors.push("自動同期には右アップか左アップのどちらかが必要です。");
    }
    ok.push("同期結果は output\\reports\\app_sync_offsets.json に保存されます。");
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
    "- Keep existing user changes in the repo; do not revert unrelated files.",
    "",
    "Operator selections:",
    `- Edit preset: ${formValue("editPreset")}`,
    `- Direct workflow action: ${formValue("workflowAction")}`,
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
    `- Output path: ${outputPath}`,
    `- Still extraction time: ${formValue("stillTime") || "00:00:25"}`,
    `- Source root override: ${formValue("sourceRoot") || "(not set)"}`,
    `- Python: ${pythonExe()}`,
    `- FFmpeg: ${formValue("ffmpegPath") || "(script default)"}`,
    `- FFprobe: ${ffprobeExe()}`,
    "",
    "Dropped assets:",
    `- Master/day video: ${state.files.masterVideo || "(use current repo default if preset supports it)"}`,
    `- Right close-up/person 1: ${state.files.rightCloseVideo || "(use current repo default if preset supports it)"}`,
    `- Left close-up/person 2: ${state.files.leftCloseVideo || "(use current repo default if preset supports it)"}`,
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
    "- For full subtitles, use corrected SRT when available.",
    "- For catchy subtitles, use the punchline overlay mode.",
    "- If punchline text/timing/style changed, update the relevant generator script or data in the smallest maintainable way before regenerating overlays.",
    "- If style/logo/title settings are not exposed by CLI flags, update the Python style/title scripts carefully and regenerate PNG overlays.",
    "- Use source root override for 2cam/3cam inputs if it is set.",
    "- Make minimal script changes needed for this request, then render or provide the exact command if rendering is blocked.",
    "- Report the output file path and any limitations.",
  ];
  return lines.join("\n");
}

function buildAppConfig() {
  return {
    assets: {
      masterVideo: state.files.masterVideo,
      rightCloseVideo: state.files.rightCloseVideo,
      leftCloseVideo: state.files.leftCloseVideo,
      externalAudio: state.files.externalAudio,
      logo: state.files.logo,
      sourceRoot: formValue("sourceRoot"),
    },
    render: {
      editPreset: formValue("editPreset"),
      workflowAction: formValue("workflowAction"),
      renderScript: formValue("renderScript"),
      outputPath: $("#outputPath").value,
      syncOffsetsPath: state.env ? `${state.env.outputRoot}\\reports\\app_sync_offsets.json` : "",
      subtitleMode: state.subtitleMode,
      multicamMode: formValue("multicamMode"),
      audioSource: formValue("audioSource"),
      audioDenoise: formValue("audioDenoise"),
      audioDenoiseStrength: Number(formValue("audioDenoiseStrength") || 10),
      previewStart: Number(formValue("previewStart") || 0),
      previewDuration: Number(formValue("previewDuration") || 60),
      shortenSilence: formValue("shortenSilence"),
      minSilence: Number(formValue("minSilence") || 3),
      keepSilence: Number(formValue("keepSilence") || 2),
      silenceNoise: formValue("silenceNoise") || "-30dB",
      keepUncut: formValue("keepUncut"),
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
    tools: {
      python: formValue("pythonPath"),
      ffmpeg: formValue("ffmpegPath"),
      ffprobe: formValue("ffprobePath"),
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
    const result = await window.editApp.execCodexCommand({
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
    setStatus(result?.exitCode === 0 ? "Codex ready" : "Command failed", result?.exitCode === 0 ? "ready" : "idle");
  } catch (error) {
    setStatus("Command error", "idle");
    log("command error", { message: error.message });
  }
}

async function sendRequest() {
  refreshPrompt();
  setStatus("Codex running", "busy");
  log("turn/start");
  try {
    await window.editApp.startCodexTurn({
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
        setFile(slot, window.editApp.filePath(file));
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
  $("#refreshCommand").addEventListener("click", refreshCommand);
  $("#refreshPrompt").addEventListener("click", refreshPrompt);
  $("#refreshSyncReport").addEventListener("click", refreshSyncReport);
  $("#runPreset").addEventListener("click", runPreset);
  $("#sendRequest").addEventListener("click", sendRequest);
  $("#interrupt").addEventListener("click", async () => {
    await window.editApp.interruptCodex();
    log("turn/interrupt requested");
  });
  $("#openOutput").addEventListener("click", () => {
    const output = $("#outputPath").value;
    if (output) {
      window.editApp.showPath(output);
    }
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
    if (mapping[formValue("editPreset")]) {
      $("#renderScript").value = mapping[formValue("editPreset")];
    }
    refreshPrompt();
  });
  $$("[data-subtitle-mode]").forEach((button) => {
    button.addEventListener("click", () => {
      $$("[data-subtitle-mode]").forEach((item) => item.classList.remove("selected"));
      button.classList.add("selected");
      state.subtitleMode = button.dataset.subtitleMode;
      refreshPrompt();
    });
  });
  $$(".step-button").forEach((button) => {
    button.addEventListener("click", () => {
      $$(".step-button").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      const panel = document.querySelector(`[data-panel="${button.dataset.section}"]`);
      panel?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  });
}

async function init() {
  state.env = await window.editApp.getEnvironment();
  $("#workspacePath").textContent = state.env.videoEditRoot;
  $("#outputPath").value = state.env.knownOutputs[0];
  $("#inputVideoPath").value = state.env.knownOutputs[0];
  $("#replaceAudioInput").value = state.env.knownOutputs[2];
  $("#pythonPath").value = state.env.pythonExe;
  $("#sourceRoot").value = "C:\\Users\\yurin\\Downloads\\cdc260515 mov\\cdc260515 mov";
  $("#punchlineText").value = defaultPunchlines;
  loadState();
  initDropZones();
  bindEvents();
  refreshPrompt();

  window.editApp.onServerReady(() => {
    setStatus("Codex ready", "ready");
    log("server ready");
  });
  window.editApp.onServerError((payload) => {
    setStatus("Codex error", "idle");
    log("server error", payload);
  });
  window.editApp.onServerExit((payload) => {
    setStatus("Codex exited", "idle");
    log("server exit", payload);
  });
  window.editApp.onServerStderr((payload) => log("stderr", payload));
  window.editApp.onServerNotification(handleNotification);
  refreshSyncReport();
}

init().catch((error) => {
  log("init error", { message: error.message });
});
