type Unsubscribe = () => void;

type EditAppApi = {
	getEnvironment: () => Promise<any>;
	createProject: (payload: any) => Promise<ProjectInfo>;
	listProjects: () => Promise<{ projects: ProjectListEntry[] }>;
	loadProject: (payload: any) => Promise<{ project: ProjectInfo; manifest?: MediaManifest | null }>;
	pickProject: (payload?: any) => Promise<{ project: ProjectInfo; manifest?: MediaManifest | null } | null>;
	deleteProject: (
		payload: any,
	) => Promise<{ deleted: boolean; canceled?: boolean; missing?: boolean; project?: ProjectInfo }>;
	copyProjectAssets: (payload: any) => Promise<{ project: ProjectInfo; files: Record<string, string> }>;
	ingestDirectory: (
		payload: any,
	) => Promise<{ project: ProjectInfo; manifest: MediaManifest; files: Record<string, any> }>;
	cancelIngest: () => Promise<any>;
	pickFile: (options: any) => Promise<string | string[] | null>;
	pickDirectory: (options: any) => Promise<string | null>;
	pickOutput: (options: any) => Promise<string | null>;
	startCodexTurn: (payload: any) => Promise<any>;
	listCodexModels: (options?: any) => Promise<any>;
	execCodexCommand: (payload: any) => Promise<any>;
	runWorkflowAction: (payload: any) => Promise<any>;
	interruptCodex: () => Promise<any>;
	loadAnalysisState: (payload: any) => Promise<any>;
	saveAnalysisState: (payload: any) => Promise<any>;
	loadProjectState: (payload: any) => Promise<any>;
	saveProjectState: (payload: any) => Promise<any>;
	patchProjectState: (payload: any) => Promise<any>;
	getSyncReport: (appConfig?: any) => Promise<any>;
	loadGlossaryCandidates: (appConfig: any) => Promise<any>;
	loadTextOverlayCandidates: (payload: any) => Promise<any>;
	listDirectory: (payload: any) => Promise<any>;
	describeMediaPaths: (payload: any) => Promise<any[]>;
	showPath: (targetPath: string) => Promise<any>;
	filePath: (file: File) => string;
	onServerReady: (callback: (payload: any) => void) => Unsubscribe;
	onServerError: (callback: (payload: any) => void) => Unsubscribe;
	onServerExit: (callback: (payload: any) => void) => Unsubscribe;
	onServerStderr: (callback: (payload: any) => void) => Unsubscribe;
	onServerNotification: (callback: (payload: any) => void) => Unsubscribe;
	onIngestProgress: (callback: (payload: any) => void) => Unsubscribe;
	onWorkflowProgress: (callback: (payload: any) => void) => Unsubscribe;
	onProjectStateChanged: (callback: (payload: any) => void) => Unsubscribe;
};

const editApp = (window as unknown as { editApp: EditAppApi }).editApp;

type ProjectInfo = {
	id: string;
	name: string;
	root: string;
	sourceRoot: string;
	outputRoot: string;
};

type ProjectListEntry = {
	project: ProjectInfo;
	updatedAt: string;
	lastModifiedAt: string;
	hasManifest: boolean;
	manifestPath: string;
	mediaCount: number;
};

type MediaItem = {
	id: string;
	kind: string;
	role: string;
	label: string;
	path: string;
	originalPath?: string;
	relativePath: string;
	name: string;
	extension: string;
	sizeBytes: number;
	confidence: number;
	reason: string;
	metadata: Record<string, any>;
	thumbnailDataUrl?: string;
};

type MediaManifest = {
	version: number;
	sourceDirectory: string;
	sourcePaths?: string[];
	generatedAt: string;
	manifestPath?: string;
	files: MediaItem[];
	cameras: MediaItem[];
	audio: MediaItem[];
	images: MediaItem[];
	subtitles: MediaItem[];
	other: MediaItem[];
	selected: Record<string, any>;
};

type Locale = "ja" | "en";
type AnalysisResult = { key: string; label: string; status: string; detail: string; path?: string };
type CodexModel = {
	id: string;
	model: string;
	displayName: string;
	defaultReasoningEffort?: string;
	isDefault?: boolean;
	hidden?: boolean;
};

const LANGUAGE_STORAGE_KEY = "video-edit-app-language-v1";

function normalizeLanguage(value: any): Locale {
	return value === "en" ? "en" : "ja";
}

function initialLanguage(): Locale {
	try {
		const saved = localStorage.getItem(LANGUAGE_STORAGE_KEY);
		if (saved) {
			return normalizeLanguage(saved);
		}
	} catch {
		// localStorage can be unavailable in unusual renderer contexts.
	}
	return navigator.language?.toLowerCase().startsWith("ja") ? "ja" : "en";
}

const state = {
	env: null,
	project: null as ProjectInfo | null,
	projectStatePath: "",
	projectStateRevision: 0,
	projectStateApplying: false,
	projectStatePersistTimer: 0,
	projectList: [] as ProjectListEntry[],
	projectListLoading: false,
	mediaManifest: null as MediaManifest | null,
	mediaDirectory: "",
	materialPaths: [] as string[],
	ingestRunning: false,
	fullAnalysisRunning: false,
	directRunRunning: false,
	codexTurnRunning: false,
	codexInterruptRequested: false,
	runningAction: "",
	lastWorkflowProgressLog: 0,
	lastWorkflowStage: "",
	appLocked: false,
	analysisResults: [] as AnalysisResult[],
	analysisTitleText: "",
	files: {
		masterVideo: "",
		rightCloseVideo: "",
		leftCloseVideo: "",
		referenceVideo: "",
		externalAudio: "",
		logo: "",
		stillImages: [] as string[],
	},
	subtitleMode: "full",
	syncReport: null,
	glossaryTerms: [],
	outputPreview: null,
	outputPreviewKind: "",
	outputPreviewLoading: false,
	filePreviews: {} as Record<string, any>,
	codexModels: [] as CodexModel[],
	codexModel: "",
	codexModelStatusKey: "codex.modelNotLoaded",
	codexModelStatusValues: {} as Record<string, string | number>,
	activeSection: "assets",
	language: initialLanguage(),
	statusText: "AI idle",
	statusKind: "idle",
};

type GlossaryTerm = {
	label: string;
	description: string;
	patterns: string;
	enabled: boolean;
};

const defaultPunchlines = "";

const fileFilterSpecs = {
	masterVideo: [{ nameKey: "filter.video", extensions: ["mp4", "mov", "m4v"] }],
	rightCloseVideo: [{ nameKey: "filter.video", extensions: ["mp4", "mov", "m4v"] }],
	leftCloseVideo: [{ nameKey: "filter.video", extensions: ["mp4", "mov", "m4v"] }],
	referenceVideo: [{ nameKey: "filter.video", extensions: ["mp4", "mov", "m4v"] }],
	externalAudio: [{ nameKey: "filter.audioOrVideo", extensions: ["wav", "mp3", "aac", "m4a", "mp4", "mov"] }],
	logo: [{ nameKey: "filter.image", extensions: ["png", "jpg", "jpeg", "webp"] }],
	stillImages: [{ nameKey: "filter.stillImages", extensions: ["png", "jpg", "jpeg", "webp"] }],
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));
const STORAGE_KEY = "video-edit-app-state-v1";
const DEFAULT_FFMPEG_EXE = "C:\\ProgramData\\chocolatey\\bin\\ffmpeg.exe";
const DEFAULT_FFPROBE_EXE = "C:\\ProgramData\\chocolatey\\bin\\ffprobe.exe";
const defaultGlossaryTerms: GlossaryTerm[] = [];

const messages: Record<Locale, Record<string, string>> = {
	ja: {
		"app.title": "Video Edit",
		"language.display": "表示言語",
		"language.aria.display": "表示言語",
		"language.aria.group": "言語",
		"nav.aria.workflow": "ワークフロー",
		"nav.assets": "素材",
		"nav.edit": "編集",
		"nav.style": "字幕・ロゴ",
		"nav.workflow": "工程",
		"nav.codex": "AI依頼",
		"status.codexIdle": "AI 待機中",
		"status.codexReady": "AI 準備完了",
		"status.codexError": "AI エラー",
		"status.codexExited": "AI 終了",
		"status.codexRunning": "AI 実行中",
		"status.codexStopping": "AI 停止中",
		"status.codexStopped": "AI 停止済み",
		"status.projectError": "プロジェクトエラー",
		"status.projectRequired": "先にプロジェクトを作成してください",
		"status.checkRequiredFields": "必須項目を確認してください",
		"status.rendering": "レンダー中",
		"status.presetRunning": "プリセット実行中",
		"status.runComplete": "実行完了",
		"status.commandFailed": "コマンド失敗",
		"status.commandError": "コマンドエラー",
		"status.analyzingMaterial": "素材解析中",
		"status.analysisComplete": "解析完了",
		"status.analysisCompletedWithErrors": "解析完了（一部エラー）",
		"status.ingestFailed": "取り込み失敗",
		"summary.precheck": "実行前チェック",
		"app.workspaceLabel": "ローカル動画編集",
		"topbar.title": "動画編集ワークスペース",
		"topbar.description": "素材を追加し、編集内容を選んで実行します。",
		"action.openSelectedOutput": "生成動画を確認",
		"action.openInExplorer": "Explorerで開く",
		"action.refreshPreview": "更新",
		"action.runPresetScript": "選択中の工程を実行",
		"action.runWithCodex": "AIに編集を依頼",
		"action.codexRunning": "AI編集中...",
		"action.stopCodex": "AI編集を停止",
		"action.stoppingCodex": "停止中...",
		"preview.heading": "生成物プレビュー",
		"preview.outputTitle": "出力フォルダ",
		"preview.waiting": "確認したい生成物を選んでください。",
		"preview.loading": "フォルダを読み込んでいます...",
		"preview.empty": "このフォルダには表示できるファイルがありません。",
		"preview.summary": "{count}件を表示中",
		"preview.folder": "フォルダ",
		"preview.file": "ファイル",
		"preview.video": "動画",
		"preview.image": "画像",
		"preview.audio": "音声",
		"preview.subtitle": "字幕",
		"preview.other": "その他",
		"preview.folderCounts": "ファイル {files} / フォルダ {folders}",
		"preview.mediaCount": "メディア {count}",
		"preview.missing": "指定パスが見つからないため、近いフォルダを表示しています。",
		"project.heading": "プロジェクト",
		"project.noProjectSelected": "プロジェクト未選択",
		"project.current": "現在のプロジェクト",
		"project.ready": "{name} を編集中",
		"project.name": "プロジェクト名",
		"project.id": "プロジェクト ID",
		"project.folder": "プロジェクトフォルダ",
		"project.source": "プロジェクト素材",
		"project.output": "プロジェクト出力",
		"project.createSelect": "新しいプロジェクトを作成",
		"project.change": "プロジェクトを選択",
		"project.copySelectedSources": "選択素材を保存",
		"project.delete": "プロジェクト削除",
		"project.dialogTitle": "プロジェクトを選択",
		"project.dialogDescription": "既存プロジェクトを開くか、新しいプロジェクトを作成します。",
		"project.dialogCreateName": "新しいプロジェクト名",
		"project.dialogCreate": "作成",
		"project.dialogExisting": "プロジェクト一覧",
		"project.dialogClose": "閉じる",
		"project.dialogCancel": "キャンセル",
		"project.dialogLoading": "プロジェクトを読み込んでいます...",
		"project.dialogEmpty": "プロジェクトはまだありません。",
		"project.dialogActive": "選択中",
		"project.dialogUpdated": "更新: {date}",
		"project.dialogMediaCount": "素材 {count} 件",
		"project.dialogNoManifest": "素材解析なし",
		"placeholder.projectName": "例: interview-client-a",
		"placeholder.autoFromName": "名前から自動生成",
		"materials.heading": "素材",
		"materials.notAnalyzed": "素材未解析",
		"materials.folderNotAnalyzed": "素材フォルダ未解析",
		"materials.selectedWaiting": "素材選択済み / 解析待ち",
		"materials.dropTitle": "素材",
		"materials.dropDescription": "フォルダ・単体ファイル・複数ファイルをまとめて自動分類します",
		"materials.noManifest": "素材マニフェストはありません。",
		"materials.manifestHint": "解析ボタンを押すと分類結果がここに表示されます。",
		"materials.analysisEmpty": "解析結果はまだありません。",
		"materials.unselected": "未選択",
		"materials.noAnalyzedAssets": "解析済み素材はまだありません。",
		"materials.selectedRole": "選択中: {role}",
		"materials.manualSlots": "手動で指定する素材",
		"reason.filenameMainCamera": "ファイル名からメインカメラとして判定",
		"reason.likelyMaster": "タイムラインの基準動画として自動選択",
		"reason.cameraOrder": "ファイル名からカメラ順を判定",
		"reason.additionalVideo": "追加動画としてメタ情報/名前から並び順を判定",
		"reason.audioSource": "別録り音声として判定",
		"reason.logo": "ファイル名からロゴとして判定",
		"reason.still": "静止画・挿入素材として判定",
		"reason.subtitle": "字幕ファイルとして判定",
		"reason.unsupported": "未対応のファイル形式",
		"action.folder": "フォルダ",
		"action.files": "ファイル",
		"action.analyze": "解析",
		"action.cancel": "キャンセル",
		"progress.waitingAnalysis": "解析待ち",
		"progress.pressAnalyze": "解析ボタンを押してください",
		"progress.analyzingMaterial": "素材を解析しています",
		"progress.startingAnalysis": "解析を開始しています",
		"progress.materialClassified": "素材分類が完了しました",
		"progress.allAnalysisComplete": "全解析が完了しました",
		"progress.analysisCompleteWithErrors": "解析は完了しましたが、一部エラーがあります",
		"progress.analysisCanceled": "解析をキャンセルしました",
		"progress.analysisFailed": "解析に失敗しました",
		"progress.renderStarting": "レンダーを開始しています",
		"progress.processStarting": "処理を開始しています",
		"progress.renderPreparing": "レンダー準備中です",
		"progress.processing": "処理中です",
		"progress.timeout": "実行がタイムアウトしました",
		"progress.processComplete": "処理が完了しました",
		"progress.processError": "処理でエラーが発生しました",
		"asset.master": "日の動画・マスター",
		"asset.masterDescription": "1cam / ベースタイムライン",
		"asset.rightClose": "右からのアップ",
		"asset.rightCloseDescription": "人物 1 のアップ",
		"asset.leftClose": "左からのアップ",
		"asset.leftCloseDescription": "人物 2 / 別アングル",
		"asset.referenceVideo": "参考動画",
		"asset.referenceDescription": "手動選択 / 60秒以内のスタイル参考",
		"asset.externalAudio": "別録り音声",
		"asset.audioDescription": "wav / mp3 / mp4",
		"asset.logo": "右上ロゴ",
		"asset.logoDescription": "png / jpg",
		"asset.stillImages": "静止画インサート",
		"asset.stillDescription": "png / jpg / webp を複数追加",
		"asset.noStillInserts": "静止画インサートなし",
		"action.select": "選択",
		"action.add": "追加",
		"action.remove": "削除",
		"action.choose": "選択",
		"action.chooseOutput": "保存先を選ぶ",
		"field.output": "作成する動画",
		"field.outputHint": "編集後の動画はここに保存されます。",
		"output.pending": "作成予定",
		"output.destination": "保存先: {folder}",
		"edit.heading": "編集",
		"edit.rules": "編集設定",
		"edit.preset": "編集プリセット",
		"edit.multicamSwitching": "マルチカム切り替え",
		"edit.audioSource": "音声ソース",
		"edit.reduceNoise": "背景ノイズを低減",
		"edit.matchCameraColor": "カメラ間の色味を合わせる",
		"edit.encoderPreset": "エンコード速度",
		"edit.videoQuality": "画質 (CRF、低いほど高画質)",
		"edit.noiseStrength": "ノイズ低減の強さ",
		"edit.musicEnabled": "BGMを生成してミックス",
		"edit.musicPlacement": "BGMを入れる場所",
		"edit.musicWhole": "動画全体",
		"edit.musicOmission": "省略テロップの範囲だけ",
		"edit.musicRangeSource": "省略範囲の検出",
		"edit.musicRangeAuto": "自動検出 + 手入力",
		"edit.musicRangeManual": "手入力のみ",
		"edit.musicLevel": "BGM音量",
		"edit.musicDirection": "BGMの方向性",
		"edit.musicRanges": "省略テロップ範囲",
		"edit.omissionCardEnabled": "省略区間を要約カードに置換",
		"edit.omissionCardDuration": "カードの長さ",
		"edit.omissionCardLabel": "カードラベル",
		"edit.omissionCardText": "要約カードの文言",
		"edit.omissionCardRanges": "置換する省略区間",
		"placeholder.musicPrompt": "静かで清潔感のある、インタビュー向けのドキュメンタリー調BGM",
		"placeholder.musicRanges": "00:12-00:18 省略テロップ",
		"placeholder.omissionCardText": "質問を要約\n聞き手の長い質問を短く整理",
		"placeholder.omissionCardRanges": "00:12-00:30 | 質問を要約 | 聞き手の質問を短く整理",
		"edit.start": "開始位置",
		"edit.outputDuration": "出力尺",
		"edit.shortenSilence": "長い無音を詰める",
		"edit.keepUncut": "未カットの下書き動画を残す",
		"edit.minSilence": "詰める無音の長さ",
		"edit.keepSilence": "残す無音",
		"edit.noise": "無音判定の音量",
		"option.newInterview": "選択素材から新規インタビュー編集",
		"option.speakerAware": "話者に合わせたインタビューカット",
		"option.dynamicCuts": "短めのリズムカット",
		"option.manualPlan": "保存済みの手動プランを使用",
		"option.masterFirst": "マスター優先、強調時にアップ",
		"option.externalIfSelected": "別録り音声があれば使用",
		"option.masterAudio": "マスター動画の音声を使用",
		"option.rightAudio": "右アップの音声を使用",
		"option.leftAudio": "左アップの音声を使用",
		"option.encoderUltrafast": "最速プレビュー (ultrafast)",
		"option.encoderSuperfast": "高速プレビュー (superfast)",
		"option.encoderVeryfast": "高速下書き (veryfast)",
		"option.encoderFaster": "やや高速 (faster)",
		"option.encoderFast": "高速エンコード (fast)",
		"option.encoderMedium": "品質バランス (medium)",
		"option.encoderSlow": "高画質 (slow)",
		"option.encoderSlower": "さらに高画質 (slower)",
		"option.encoderVeryslow": "最高画質 (veryslow)",
		"style.heading": "字幕",
		"style.overlays": "字幕とロゴ設定",
		"style.subtitleMode": "字幕モード",
		"style.full": "全文",
		"style.catchy": "見せ場",
		"style.none": "なし",
		"style.subtitleSize": "字幕サイズ",
		"style.highlightColor": "強調色",
		"style.boxOpacity": "字幕の背景",
		"style.topLeftText": "コーナータイトル",
		"style.titleSize": "タイトルサイズ",
		"style.logoHeight": "ロゴ高さ",
		"style.punchlineLines": "見せ場字幕の行",
		"glossary.heading": "専門用語解説",
		"glossary.description": "字幕から候補を読み込み、表示する用語を調整",
		"glossary.loadCandidates": "候補を読み込み",
		"glossary.show": "専門用語解説を表示",
		"glossary.notLoaded": "候補未読み込み",
		"glossary.termLabel": "用語ラベル",
		"glossary.termPatterns": "検出語",
		"glossary.termDescription": "解説",
		"placeholder.glossaryLabel": "用語 例: EDM",
		"placeholder.glossaryPatterns": "検出語 例: EDM,イーディーエム",
		"placeholder.glossaryDescription": "短い解説",
		"workflow.heading": "工程",
		"workflow.actions": "実行する作業",
		"workflow.directAction": "実行する工程",
		"workflow.advancedSettings": "詳細設定",
		"workflow.analysisSettings": "解析の詳細設定",
		"workflow.renderScript": "レンダー方式",
		"workflow.transcribeModel": "文字起こし品質",
		"workflow.language": "言語",
		"workflow.beam": "聞き取り精度",
		"workflow.temperature": "表記の揺れ",
		"workflow.promptTerms": "聞き取りで優先する語句",
		"workflow.loudnessNormalize": "文字起こし前に音量を整える",
		"workflow.filterLowConfidence": "空白に見える文字起こしを除外",
		"workflow.previousText": "前後の字幕文脈を使う",
		"workflow.runtimePaths": "実行環境のパス",
		"workflow.pythonPath": "Python 実行ファイル",
		"workflow.ffmpegPath": "FFmpeg 実行ファイル",
		"workflow.ffprobePath": "FFprobe 実行ファイル",
		"workflow.verificationInput": "処理対象の動画",
		"workflow.selectInputVideo": "入力動画を選択",
		"workflow.thumbnailQaSettings": "サムネイル / 字幕QA",
		"workflow.thumbnailTime": "サムネイル時刻",
		"workflow.thumbnailTitle": "サムネイルタイトル",
		"workflow.thumbnailSubtitle": "サムネイル補足",
		"workflow.thumbnailCandidates": "候補数",
		"workflow.thumbnailLayout": "サムネイル構図",
		"workflow.thumbnailMainColor": "メイン色",
		"workflow.thumbnailCandidateTimes": "候補に使う時刻",
		"workflow.thumbnailDebugFaces": "候補に顔検出枠を描画",
		"workflow.naturalDialogueCuts": "会話の谷間へカメラ切替を寄せる",
		"workflow.audioMastering": "オンライン動画向けに音声を整える",
		"workflow.subtitleReviewMaxDuration": "字幕1区間の最大秒数",
		"workflow.subtitleReviewMaxCharsPerSecond": "字幕の最大読上げ速度",
		"workflow.subtitleSuspiciousPatterns": "疑わしい字幕パターン",
		"workflow.subtitleReviewExtractClips": "怪しい字幕の音声クリップを書き出す",
		"workflow.subtitleReviewTranscribeClips": "怪しい字幕クリップを再文字起こし",
		"workflow.subtitleCorrections": "字幕修正",
		"workflow.subtitleInterviewerRanges": "聞き手/省略扱いの範囲",
		"workflow.subtitleInterviewerPatterns": "聞き手/省略扱いの語句",
		"workflow.subtitleManualRoles": "字幕ごとの話者ロール",
		"workflow.subtitleMouthMotionDiagnostics": "口元動き診断を追加",
		"workflow.stillTime": "静止画にする時刻",
		"workflow.personSampleFps": "人物解析の細かさ",
		"workflow.yoloModel": "人物検出モデル",
		"workflow.personConfidence": "人物検出のしきい値",
		"workflow.analysisMaxSeconds": "テスト解析の秒数",
		"workflow.videoLimit": "解析する動画数",
		"workflow.personNoMulticamRoot": "選択したプロジェクト動画だけ解析",
		"workflow.syncScore": "同期スコア",
		"action.refresh": "更新",
		"option.renderSelected": "選択した設定で動画を作成",
		"option.generatePunchlines": "見せ場字幕画像を作成",
		"option.generateFullOverlays": "全文字幕画像を作成",
		"option.generateGlossaryOverlays": "専門用語解説画像を作成",
		"option.generateMusicBed": "BGMを生成",
		"option.replaceAudio": "動画の音声を差し替え",
		"option.generateThumbnail": "サムネイル画像を作成",
		"option.generateThumbnailCandidates": "サムネイル候補を作成",
		"option.reviewSubtitles": "字幕品質をレビュー",
		"option.applySubtitleCorrections": "字幕修正を適用",
		"option.classifySubtitleSpeakers": "字幕の話者ロールを分類",
		"option.compareTranscripts": "素材ごとの文字起こしを比較",
		"option.analyzeBlocking": "カメラ構図を解析",
		"option.analyzePersonEdit": "人物とカット候補を解析",
		"option.analyzeReference": "参考動画を解析",
		"option.autoSyncDropped": "選択したカメラ素材を同期",
		"option.transcribeDropped": "選択素材を文字起こし",
		"option.shortenInput": "選択入力動画の無音を詰める",
		"option.extractStill": "静止画を書き出す",
		"option.verifyDuration": "動画の長さを確認",
		"option.verifyAudio": "動画の音声を確認",
		"option.renderAppInterview": "選択素材からインタビュー編集",
		"Place camera cuts in dialogue gaps": "会話の谷間へカメラ切替を寄せる",
		"Use person analysis for crops": "人物解析をクロップへ反映",
		"Use transcript comparison for sync fallback": "文字起こし比較を同期補正に使う",
		"Master audio for online video": "オンライン動画向けに音声を整える",
		"Extract flagged subtitle audio clips": "怪しい字幕の音声クリップを書き出す",
		"Re-transcribe flagged subtitle clips": "怪しい字幕クリップを再文字起こし",
		"action.file": "ファイル",
		"placeholder.projectTitle": "プロジェクトタイトル",
		"placeholder.thumbnailSubtitle": "短い補足テキスト",
		"placeholder.thumbnailCandidateTimes": "00:00:03 | フック | タイトル | 補足",
		"placeholder.subtitleSuspiciousPatterns": "誤認識語句または正規表現",
		"placeholder.subtitleCorrections": "12 | 修正後の字幕テキスト | 理由",
		"placeholder.subtitleInterviewerRanges": "00:12-00:18 | 聞き手の質問",
		"placeholder.subtitleInterviewerPatterns": "インタビュアー|聞き手|質問",
		"placeholder.subtitleManualRoles": "12 | interviewer | 画面外の質問",
		"placeholder.all": "すべて",
		"codex.heading": "AIへの依頼",
		"codex.prompt": "AIに送る内容",
		"codex.details": "依頼内容と実行内容を確認",
		"codex.reviewBeforeRunning": "実行前に確認",
		"codex.directCommand": "実行内容",
		"codex.model": "AIモデル",
		"codex.modelDefault": "Codex標準",
		"codex.refreshModels": "モデルを更新",
		"codex.modelNotLoaded": "モデル一覧は未取得",
		"codex.modelLoading": "モデル一覧を取得中",
		"codex.modelLoaded": "{count}件のモデルを取得",
		"codex.modelLoadFailed": "モデル一覧の取得に失敗",
		"codex.modelDefaultSuffix": "標準",
		"codex.modelCustomSuffix": "保存済み",
		"action.refreshCommand": "実行内容を更新",
		"action.refreshPrompt": "依頼内容を更新",
		"action.interrupt": "AI編集を停止",
		"progress.heading": "進捗",
		"progress.streamedEvents": "実行ログ",
		"busy.processing": "処理中",
		"busy.wait": "しばらくお待ちください",
		"label.notSelected": "未選択",
		"label.none": "なし",
		"label.notLoaded": "未読み込み",
		"label.offsetUnknown": "オフセット不明",
		"label.confidence": "信頼度",
		"label.selectedItems": "{count}件を選択中",
		"label.imageCount": "{count}枚の画像",
		"label.filesSummary": "{files}件 / カメラ{cameras}本 / 音声{audio}件 / 静止画{stills}枚 / 字幕{subtitles}件",
		"role.master": "Camera 1 / マスター",
		"role.camera2": "Camera 2",
		"role.camera3": "Camera 3",
		"role.camera4": "Camera 4",
		"role.camera5": "Camera 5",
		"role.externalAudio": "別録り音声",
		"role.externalAudio2": "別録り音声 2",
		"role.stillInsert": "静止画インサート",
		"role.logo": "ロゴ",
		"role.subtitle": "字幕",
		"role.ignore": "無視",
		"role.overrideReason": "オペレーター上書き",
		"dialog.selectStillImages": "静止画を選択",
		"dialog.selectSlot": "{slot}を選択",
		"dialog.selectTool": "{id}を選択",
		"dialog.selectMaterialFolder": "素材フォルダを選択",
		"dialog.selectMaterialFiles": "素材ファイルを選択",
		"dialog.selectOutputVideo": "出力動画を選択",
		"dialog.selectProjectFolder": "プロジェクトフォルダを選択",
		"dialog.deleteProjectTitle": "プロジェクト削除",
		"dialog.deleteProjectMessage": "プロジェクト「{name}」を削除しますか？",
		"dialog.deleteProjectDetail": "この操作は取り消せません。\n{path}",
		"dialog.deleteProjectConfirm": "削除する",
		"filter.video": "動画",
		"filter.audioOrVideo": "音声または動画",
		"filter.image": "画像",
		"filter.stillImages": "静止画",
		"filter.mediaAndSubtitles": "メディアと字幕",
		"filter.allFiles": "すべてのファイル",
		"filter.mp4Video": "MP4 動画",
		"runLabel.render": "レンダー",
		"runLabel.sync": "同期",
		"runLabel.transcribe": "文字起こし",
		"runLabel.analyze": "解析",
		"runLabel.run": "実行",
		"format.runningButton": "{label}中...",
		"format.runningMessage": "{label}を実行しています",
		"format.startingMessage": "{label}を開始しています",
		"format.completeMessage": "{label}が完了しました",
		"format.errorMessage": "{label}でエラーがありました",
		"analysis.materialClassification": "素材分類",
		"analysis.syncCamerasAudio": "カメラ・音声同期",
		"analysis.transcription": "文字起こし",
		"analysis.transcriptComparison": "素材字幕比較",
		"analysis.subtitleUi": "字幕UI反映",
		"analysis.personOpenCv": "OpenCV人物解析",
		"analysis.blockingOpenCv": "OpenCV構図解析",
		"analysis.referenceVideo": "参考動画解析",
		"analysis.updatedOutput": "出力を更新しました",
		"analysis.checkLogs": "実行ログを確認してください",
		"analysis.singleCameraSkipped": "1カメラ素材のためスキップ",
		"analysis.noSubtitleCandidates": "字幕ファイルまたは文字起こし結果が見つかりません",
		"analysis.statusDone": "完了",
		"analysis.statusError": "エラー",
		"analysis.statusRunning": "実行中",
		"sync.noReport": "カメラ同期レポートはまだありません。",
		"validation.outputRequired": "出力先を指定してください。",
		"validation.projectRequired": "先にプロジェクトを作成または選択してください。",
		"validation.output": "出力: {path}",
		"validation.masterRequiredForInterview":
			"Interview render には Camera 1 / master が必要です。素材フォルダを取り込むか、手動で指定してください。",
		"validation.singleCameraWarning": "アップ素材が未指定なので、実質1カメラのレンダーになります。",
		"validation.syncFirstWarning":
			"新規マルチカム素材は、先に Auto-sync dropped cameras を実行して app_sync_offsets.json を作ってください。",
		"validation.shortenSilenceWarning":
			"無音詰めONの場合、指定した出力尺からさらに短くなります。尺を固定したい場合はOFFにしてください。",
		"validation.masterRequiredForSync": "自動同期には Camera 1 / master が必要です。",
		"validation.syncTargetsRequired": "自動同期には Camera 2 以降、または別録り音声が必要です。",
		"validation.syncSaved": "カメラ/別録り音声の同期結果を保存します。",
		"validation.stillCount": "静止画インサート: {count}枚",
		"validation.stillMotion": "文字/図解系はズームなし、写真系は薄いズーム/パンで挿入します。",
		"validation.preview": "確認用: {path}",
		"validation.personBbox": "人物bbox: {path}",
		"validation.editPlan": "編集プラン: {path}",
		"validation.analysisFps": "解析間隔: {fps} fps",
		"validation.selectedVideos": "解析対象: 選択済み動画 {count}本",
		"validation.sourceRoots": "解析対象: 選択プロジェクトの動画",
		"validation.testAnalysis": "テスト解析の秒数が入っているため、全尺ではなく一部だけ解析します。",
		"validation.referenceRequired": "参考動画を1本ドラッグ&ドロップしてください。",
		"validation.referenceShort": "参考動画は60秒以内として解析します。超えている場合は実行時に止めます。",
		"validation.referenceProfile": "参考プロファイル: {path}",
		"validation.referenceBbox": "参考人物bbox: {path}",
		"validation.referenceEditPlan": "参考編集プラン: {path}",
		"validation.shortenNeedsInputOutput": "無音詰めには入力動画と出力先が必要です。",
		"validation.verificationNeedsInput": "この工程には処理対象の動画が必要です。",
		"validation.thumbnailNeedsInput":
			"サムネイル作成には、入力動画・Camera 1 / master・解析済みカメラのいずれかが必要です。",
		"validation.thumbnailOutput": "サムネイル: {path}",
		"validation.thumbnailCandidatesNeedsInput":
			"サムネイル候補作成には、入力動画・解析済みカメラ・プロジェクト画像のいずれかが必要です。",
		"validation.thumbnailCandidatesOutput": "サムネイル候補: {path}",
		"validation.thumbnailCandidateSettings": "サムネイル候補: {count}枚 / {mode} / {color}",
		"validation.thumbnailDebugFaces": "サムネイル候補: 顔検出デバッグON",
		"validation.subtitleReviewNeedsProject":
			"字幕レビューにはプロジェクト出力と文字起こし結果が必要です。先に文字起こしを実行してください。",
		"validation.subtitleReviewOutput": "字幕QA: {path}",
		"validation.subtitleReviewClips": "字幕QA音声クリップ: {path}",
		"validation.subtitleReviewRetranscribe": "字幕QA: フラグ箇所を再文字起こし",
		"validation.subtitleCorrectionsMissing": "字幕修正を適用するには、修正行を入力してください。",
		"validation.subtitleCorrectionsOutput": "字幕修正レポート: {path}",
		"validation.subtitleSpeakerRolesOutput": "字幕話者ロール: {path}",
		"validation.subtitleSpeakerManualRoles": "字幕話者ロール: 手動指定あり",
		"validation.subtitleSpeakerMouthMotion": "字幕話者ロール: 口元動き診断ON",
		"validation.transcriptComparisonOutput": "素材字幕比較: {path}",
		"validation.replaceAudioNeedsInputOutput": "音声差し替えには、処理対象の動画と保存先が必要です。",
		"validation.replaceAudioNeedsExternal": "音声差し替えには、別録り音声を選択してください。",
		"validation.replaceAudioSamePath": "音声差し替えでは、入力動画と別の保存先を選んでください。",
		"validation.replaceAudioOutput": "音声差し替え: {path}",
		"validation.replaceAudioSource": "差し替え音声: {path}",
		"validation.subtitleSpeakerRulesMissing": "話者ロール分類には、聞き手/省略扱いの範囲または語句を入力してください。",
		"validation.audioExternal": "音声: 別録り {path}",
		"validation.audioFallbackMaster": "別録り音声が未指定なので、レンダーはマスター動画音声にフォールバックします。",
		"validation.rightAudioFallback": "右アップ音声が未指定なので、レンダーはマスター動画音声にフォールバックします。",
		"validation.leftAudioFallback": "左アップ音声が未指定なので、レンダーはマスター動画音声にフォールバックします。",
		"validation.workflow": "工程: {label}",
		"validation.transcribe": "文字起こし: {model} / {language}",
		"validation.subtitle": "字幕: {mode}",
		"validation.termsOn": "用語解説: ON ({count}語)",
		"validation.termsOff": "用語解説: OFF",
		"validation.denoiseOn": "ノイズ低減: ON ({strength})",
		"validation.denoiseOff": "ノイズ低減: OFF",
		"validation.colorMatchOn": "カメラ色合わせ: ON",
		"validation.colorMatchOff": "カメラ色合わせ: OFF",
		"validation.personCropOn": "人物クロップ: 解析結果を使用",
		"validation.personCropOff": "人物クロップ: OFF",
		"validation.transcriptSyncOn": "同期補正: 文字起こし比較を低スコア時に使用",
		"validation.transcriptSyncOff": "同期補正: 文字起こし比較は未使用",
		"validation.naturalCutsOn": "カメラ切替: 会話の谷間へ調整",
		"validation.naturalCutsOff": "カメラ切替: 自動境界のまま",
		"validation.audioMasteringOn": "音声整音: ON",
		"validation.audioMasteringOff": "音声整音: OFF",
		"validation.encoder": "エンコード: {preset} / CRF {crf}",
		"validation.musicFull": "BGM: ON / 動画全体 / 音量 {volume}%",
		"validation.musicOmission": "BGM: ON / 省略テロップ範囲のみ / 音量 {volume}%",
		"validation.musicAutoRanges": "省略範囲: オーバーレイから自動検出し、手入力範囲も追加します。",
		"validation.musicManualRanges": "省略範囲: 手入力のみ",
		"validation.musicRangesMissing": "手入力のみの場合は、省略範囲を入力してください。",
		"validation.musicOff": "BGM: OFF",
		"validation.omissionCardOn": "省略カード: ON / {duration}秒",
		"validation.omissionCardMissingRanges":
			"省略カードを使うには、置換する範囲または省略テロップ範囲を入力してください。",
		"validation.omissionCardOff": "省略カード: OFF",
		"validation.silenceOn": "無音詰め: ON",
		"validation.silenceOff": "無音詰め: OFF",
		"validation.previousSync": "前回同期: {role} score {score}",
		"validation.lowSyncScore": "前回の自動同期スコアが低い素材があります。短尺QAで音ズレ確認してください。",
		"notification.renderComplete": "レンダーが完了しました。",
		"notification.analysisComplete": "素材解析・文字起こし・OpenCV解析が完了しました。",
		"notification.analysisCompleteCheck": "解析は完了しました。一部の結果を確認してください。",
		"log.projectNotSelected": "プロジェクトが選択されていません",
		"log.cannotDeleteDuringIngest": "素材解析中は削除できません",
		"log.cannotSwitchDuringIngest": "素材解析中はプロジェクトを切り替えられません",
		"log.selectMaterialFirst": "素材フォルダまたはファイルを選択してください",
		"log.glossaryRequired": "用語・検出語・解説を入力してください",
	},
	en: {
		"app.title": "Video Edit",
		"language.display": "Display language",
		"language.aria.display": "Display language",
		"language.aria.group": "Language",
		"nav.aria.workflow": "Workflow",
		"nav.assets": "Assets",
		"nav.edit": "Edit",
		"nav.style": "Subtitles / Logo",
		"nav.workflow": "Workflow",
		"nav.codex": "AI request",
		"status.codexIdle": "AI idle",
		"status.codexReady": "AI ready",
		"status.codexError": "AI error",
		"status.codexExited": "AI stopped",
		"status.codexRunning": "AI running",
		"status.codexStopping": "Stopping AI",
		"status.codexStopped": "AI stopped",
		"status.projectError": "Project error",
		"status.projectRequired": "Create a project first",
		"status.checkRequiredFields": "Check required fields",
		"status.rendering": "Rendering",
		"status.presetRunning": "Preset running",
		"status.runComplete": "Run complete",
		"status.commandFailed": "Command failed",
		"status.commandError": "Command error",
		"status.analyzingMaterial": "Analyzing material",
		"status.analysisComplete": "Analysis complete",
		"status.analysisCompletedWithErrors": "Analysis completed with errors",
		"status.ingestFailed": "Ingest failed",
		"summary.precheck": "Pre-run check",
		"app.workspaceLabel": "Local video editing",
		"topbar.title": "Video editing workspace",
		"topbar.description": "Add media, choose edit settings, and run the job.",
		"action.openSelectedOutput": "Review generated video",
		"action.openInExplorer": "Open in Explorer",
		"action.refreshPreview": "Refresh",
		"action.runPresetScript": "Run selected workflow step",
		"action.runWithCodex": "Ask AI to edit",
		"action.codexRunning": "AI editing...",
		"action.stopCodex": "Stop AI edit",
		"action.stoppingCodex": "Stopping...",
		"preview.heading": "Generated file preview",
		"preview.outputTitle": "Output folder",
		"preview.waiting": "Choose which generated files to review.",
		"preview.loading": "Loading folder...",
		"preview.empty": "This folder has no displayable files.",
		"preview.summary": "Showing {count} item(s)",
		"preview.folder": "Folder",
		"preview.file": "File",
		"preview.video": "Video",
		"preview.image": "Image",
		"preview.audio": "Audio",
		"preview.subtitle": "Subtitle",
		"preview.other": "Other",
		"preview.folderCounts": "{files} file(s) / {folders} folder(s)",
		"preview.mediaCount": "{count} media item(s)",
		"preview.missing": "The requested path was missing, so the nearest folder is shown.",
		"project.heading": "Project",
		"project.noProjectSelected": "No project selected",
		"project.current": "Current project",
		"project.ready": "Editing {name}",
		"project.name": "Project name",
		"project.id": "Project ID",
		"project.folder": "Project folder",
		"project.source": "Project source",
		"project.output": "Project output",
		"project.createSelect": "Create new project",
		"project.change": "Select project",
		"project.copySelectedSources": "Save selected material",
		"project.delete": "Delete project",
		"project.dialogTitle": "Select project",
		"project.dialogDescription": "Open an existing project or create a new one.",
		"project.dialogCreateName": "New project name",
		"project.dialogCreate": "Create",
		"project.dialogExisting": "Project list",
		"project.dialogClose": "Close",
		"project.dialogCancel": "Cancel",
		"project.dialogLoading": "Loading projects...",
		"project.dialogEmpty": "No projects yet.",
		"project.dialogActive": "Active",
		"project.dialogUpdated": "Updated: {date}",
		"project.dialogMediaCount": "{count} material files",
		"project.dialogNoManifest": "No material analysis",
		"placeholder.projectName": "e.g. interview-client-a",
		"placeholder.autoFromName": "auto from name",
		"materials.heading": "Assets",
		"materials.notAnalyzed": "Assets not analyzed",
		"materials.folderNotAnalyzed": "Material folder not analyzed",
		"materials.selectedWaiting": "Assets selected / waiting for analysis",
		"materials.dropTitle": "Assets",
		"materials.dropDescription": "Automatically classify folders, single files, or multiple files together.",
		"materials.noManifest": "No material manifest.",
		"materials.manifestHint": "Classification results will appear here after analysis.",
		"materials.analysisEmpty": "No analysis results yet.",
		"materials.unselected": "Not selected",
		"materials.noAnalyzedAssets": "No analyzed assets yet.",
		"materials.selectedRole": "Selected as {role}",
		"materials.manualSlots": "Manual material overrides",
		"reason.filenameMainCamera": "filename indicates the main/wide camera",
		"reason.likelyMaster": "chosen as the most likely timeline master",
		"reason.cameraOrder": "filename indicates camera order",
		"reason.additionalVideo": "additional video source ordered by metadata/name",
		"reason.audioSource": "standalone audio source",
		"reason.logo": "filename indicates a logo/brand mark",
		"reason.still": "image asset for inserts or visual material",
		"reason.subtitle": "subtitle file",
		"reason.unsupported": "unsupported file type",
		"action.folder": "Folder",
		"action.files": "Files",
		"action.analyze": "Analyze",
		"action.cancel": "Cancel",
		"progress.waitingAnalysis": "Waiting for analysis",
		"progress.pressAnalyze": "Click Analyze to start",
		"progress.analyzingMaterial": "Analyzing assets",
		"progress.startingAnalysis": "Starting analysis",
		"progress.materialClassified": "Asset classification complete",
		"progress.allAnalysisComplete": "All analysis complete",
		"progress.analysisCompleteWithErrors": "Analysis completed with some errors",
		"progress.analysisCanceled": "Analysis canceled",
		"progress.analysisFailed": "Analysis failed",
		"progress.renderStarting": "Starting render",
		"progress.processStarting": "Starting process",
		"progress.renderPreparing": "Preparing render",
		"progress.processing": "Processing",
		"progress.timeout": "Run timed out",
		"progress.processComplete": "Process complete",
		"progress.processError": "Process failed",
		"asset.master": "Day video / master",
		"asset.masterDescription": "1cam / base timeline",
		"asset.rightClose": "Right close-up",
		"asset.rightCloseDescription": "person 1 close-up",
		"asset.leftClose": "Left close-up",
		"asset.leftCloseDescription": "person 2 / alternate",
		"asset.referenceVideo": "Reference video",
		"asset.referenceDescription": "manual selection / style reference under 60s",
		"asset.externalAudio": "External audio",
		"asset.audioDescription": "wav / mp3 / mp4",
		"asset.logo": "Top-right logo",
		"asset.logoDescription": "png / jpg",
		"asset.stillImages": "Still inserts",
		"asset.stillDescription": "drop multiple png / jpg / webp",
		"asset.noStillInserts": "No still inserts.",
		"action.select": "Select",
		"action.add": "Add",
		"action.remove": "Remove",
		"action.choose": "Choose",
		"action.chooseOutput": "Choose save location",
		"field.output": "Video to create",
		"field.outputHint": "This is where the edited video will be saved.",
		"output.pending": "Ready to create",
		"output.destination": "Save folder: {folder}",
		"edit.heading": "Edit",
		"edit.rules": "edit settings",
		"edit.preset": "Edit preset",
		"edit.multicamSwitching": "Multicam switching",
		"edit.audioSource": "Audio source",
		"edit.reduceNoise": "Reduce background noise",
		"edit.matchCameraColor": "Match camera color",
		"edit.encoderPreset": "Encoder preset",
		"edit.videoQuality": "Video quality (CRF, lower is better)",
		"edit.noiseStrength": "Noise reduction strength",
		"edit.musicEnabled": "Generate and mix background music",
		"edit.musicPlacement": "Music placement",
		"edit.musicWhole": "Whole video",
		"edit.musicOmission": "Omission title ranges only",
		"edit.musicRangeSource": "Omission range source",
		"edit.musicRangeAuto": "Auto + manual ranges",
		"edit.musicRangeManual": "Manual ranges only",
		"edit.musicLevel": "Music level",
		"edit.musicDirection": "Music direction",
		"edit.musicRanges": "Omission title ranges",
		"edit.omissionCardEnabled": "Replace omission ranges with a summary card",
		"edit.omissionCardDuration": "Card duration",
		"edit.omissionCardLabel": "Card label",
		"edit.omissionCardText": "Summary card text",
		"edit.omissionCardRanges": "Replacement ranges",
		"placeholder.musicPrompt": "quiet, clean, documentary-like bed for a reflective interview",
		"placeholder.musicRanges": "00:12-00:18 omission title",
		"placeholder.omissionCardText": "Question summary\nCondense the interviewer question here",
		"placeholder.omissionCardRanges": "00:12-00:30 | Question summary | Condensed interviewer question",
		"edit.start": "Start",
		"edit.outputDuration": "Output duration",
		"edit.shortenSilence": "Shorten long silence",
		"edit.keepUncut": "Keep uncut draft video",
		"edit.minSilence": "Silence to shorten",
		"edit.keepSilence": "Silence to keep",
		"edit.noise": "Silence threshold",
		"option.newInterview": "New interview edit from selected media",
		"option.speakerAware": "Speaker-aware interview cuts",
		"option.dynamicCuts": "Rhythmic punch-in cuts",
		"option.manualPlan": "Use saved manual plan",
		"option.masterFirst": "Master first, close-ups for emphasis",
		"option.externalIfSelected": "Use external audio if selected",
		"option.masterAudio": "Use master video audio",
		"option.rightAudio": "Use right close-up audio",
		"option.leftAudio": "Use left close-up audio",
		"option.encoderUltrafast": "Fastest preview (ultrafast)",
		"option.encoderSuperfast": "Very fast preview (superfast)",
		"option.encoderVeryfast": "Fast draft (veryfast)",
		"option.encoderFaster": "Faster encode (faster)",
		"option.encoderFast": "Fast encode (fast)",
		"option.encoderMedium": "Balanced quality (medium)",
		"option.encoderSlow": "High quality (slow)",
		"option.encoderSlower": "Higher quality (slower)",
		"option.encoderVeryslow": "Maximum quality (veryslow)",
		"style.heading": "Subtitles",
		"style.overlays": "subtitle and logo settings",
		"style.subtitleMode": "Subtitle mode",
		"style.full": "Full",
		"style.catchy": "Catchy",
		"style.none": "None",
		"style.subtitleSize": "Subtitle size",
		"style.highlightColor": "Highlight color",
		"style.boxOpacity": "Subtitle background",
		"style.topLeftText": "Corner title",
		"style.titleSize": "Title size",
		"style.logoHeight": "Logo height",
		"style.punchlineLines": "Catchy subtitle lines",
		"glossary.heading": "Glossary explanations",
		"glossary.description": "Load candidate terms from subtitles and adjust which terms appear.",
		"glossary.loadCandidates": "Load candidates",
		"glossary.show": "Show glossary explanations",
		"glossary.notLoaded": "Candidates not loaded",
		"glossary.termLabel": "term label",
		"glossary.termPatterns": "term patterns",
		"glossary.termDescription": "term description",
		"placeholder.glossaryLabel": "Term, e.g. EDM",
		"placeholder.glossaryPatterns": "Detection terms, e.g. EDM,イーディーエム",
		"placeholder.glossaryDescription": "Short explanation",
		"workflow.heading": "Workflow",
		"workflow.actions": "Choose what to run",
		"workflow.directAction": "Step to run",
		"workflow.advancedSettings": "Advanced settings",
		"workflow.analysisSettings": "Analysis settings",
		"workflow.renderScript": "Render method",
		"workflow.transcribeModel": "Transcription quality",
		"workflow.language": "Language",
		"workflow.beam": "Accuracy",
		"workflow.temperature": "Wording variation",
		"workflow.promptTerms": "Terms to prioritize in transcription",
		"workflow.loudnessNormalize": "Normalize volume before transcription",
		"workflow.filterLowConfidence": "Remove obvious empty transcription segments",
		"workflow.previousText": "Use previous subtitle text as context",
		"workflow.runtimePaths": "Runtime paths",
		"workflow.pythonPath": "Python executable",
		"workflow.ffmpegPath": "FFmpeg executable",
		"workflow.ffprobePath": "FFprobe executable",
		"workflow.verificationInput": "Input video to process",
		"workflow.selectInputVideo": "Select input video",
		"workflow.thumbnailQaSettings": "Thumbnail / subtitle QA",
		"workflow.thumbnailTime": "Thumbnail time",
		"workflow.thumbnailTitle": "Thumbnail title",
		"workflow.thumbnailSubtitle": "Thumbnail subtitle",
		"workflow.thumbnailCandidates": "Thumbnail candidates",
		"workflow.thumbnailLayout": "Thumbnail layout",
		"workflow.thumbnailMainColor": "Main color",
		"workflow.thumbnailCandidateTimes": "Candidate times",
		"workflow.thumbnailDebugFaces": "Draw detected face boxes on candidates",
		"workflow.naturalDialogueCuts": "Place camera cuts in dialogue gaps",
		"workflow.audioMastering": "Master audio for online video",
		"workflow.subtitleReviewMaxDuration": "Max subtitle duration",
		"workflow.subtitleReviewMaxCharsPerSecond": "Max reading speed",
		"workflow.subtitleSuspiciousPatterns": "Suspicious subtitle patterns",
		"workflow.subtitleReviewExtractClips": "Extract flagged subtitle audio clips",
		"workflow.subtitleReviewTranscribeClips": "Re-transcribe flagged subtitle clips",
		"workflow.subtitleCorrections": "Subtitle corrections",
		"workflow.subtitleInterviewerRanges": "Interviewer ranges",
		"workflow.subtitleInterviewerPatterns": "Interviewer patterns",
		"workflow.subtitleManualRoles": "Manual speaker roles",
		"workflow.subtitleMouthMotionDiagnostics": "Add mouth-motion diagnostic",
		"workflow.stillTime": "Still image time",
		"workflow.personSampleFps": "Person analysis detail",
		"workflow.yoloModel": "Person detection model",
		"workflow.personConfidence": "Person detection threshold",
		"workflow.analysisMaxSeconds": "Test analysis length",
		"workflow.videoLimit": "Videos to analyze",
		"workflow.personNoMulticamRoot": "Analyze only selected project videos",
		"workflow.syncScore": "Sync score",
		"action.refresh": "Refresh",
		"option.renderSelected": "Create video from selected settings",
		"option.generatePunchlines": "Create catchy subtitle images",
		"option.generateFullOverlays": "Create full subtitle images",
		"option.generateGlossaryOverlays": "Create glossary explanation images",
		"option.generateMusicBed": "Generate background music",
		"option.replaceAudio": "Replace video audio",
		"option.generateThumbnail": "Generate thumbnail image",
		"option.generateThumbnailCandidates": "Generate thumbnail candidates",
		"option.reviewSubtitles": "Review subtitle quality",
		"option.applySubtitleCorrections": "Apply subtitle corrections",
		"option.classifySubtitleSpeakers": "Classify subtitle speakers",
		"option.compareTranscripts": "Compare source transcripts",
		"option.analyzeBlocking": "Analyze camera framing",
		"option.analyzePersonEdit": "Analyze people for camera cuts",
		"option.analyzeReference": "Analyze reference video",
		"option.autoSyncDropped": "Sync selected camera files",
		"option.transcribeDropped": "Transcribe selected media",
		"option.shortenInput": "Shorten silence in selected video",
		"option.extractStill": "Save a still image",
		"option.verifyDuration": "Check output duration",
		"option.verifyAudio": "Check output audio",
		"option.renderAppInterview": "Interview edit from selected media",
		"Place camera cuts in dialogue gaps": "Place camera cuts in dialogue gaps",
		"Use person analysis for crops": "Use person analysis for crops",
		"Use transcript comparison for sync fallback": "Use transcript comparison for sync fallback",
		"Master audio for online video": "Master audio for online video",
		"Extract flagged subtitle audio clips": "Extract flagged subtitle audio clips",
		"Re-transcribe flagged subtitle clips": "Re-transcribe flagged subtitle clips",
		"action.file": "File",
		"placeholder.projectTitle": "Project title",
		"placeholder.thumbnailSubtitle": "Short supporting line",
		"placeholder.thumbnailCandidateTimes": "00:00:03 | Hook | Title | Subtitle",
		"placeholder.subtitleSuspiciousPatterns": "misheard phrase or regex",
		"placeholder.subtitleCorrections": "12 | corrected subtitle text | reason",
		"placeholder.subtitleInterviewerRanges": "00:12-00:18 | interviewer question",
		"placeholder.subtitleInterviewerPatterns": "interviewer|host|question",
		"placeholder.subtitleManualRoles": "12 | interviewer | offscreen question",
		"placeholder.all": "all",
		"codex.heading": "AI editing request",
		"codex.prompt": "Request text sent to AI",
		"codex.details": "Review request details",
		"codex.reviewBeforeRunning": "Review before running",
		"codex.directCommand": "Execution details",
		"codex.model": "AI model",
		"codex.modelDefault": "Codex default",
		"codex.refreshModels": "Refresh models",
		"codex.modelNotLoaded": "Model list not loaded",
		"codex.modelLoading": "Loading models",
		"codex.modelLoaded": "Loaded {count} model(s)",
		"codex.modelLoadFailed": "Could not load models",
		"codex.modelDefaultSuffix": "default",
		"codex.modelCustomSuffix": "saved",
		"action.refreshCommand": "Refresh execution details",
		"action.refreshPrompt": "Refresh request text",
		"action.interrupt": "Stop AI edit",
		"progress.heading": "Progress",
		"progress.streamedEvents": "Run log",
		"busy.processing": "Processing",
		"busy.wait": "Please wait",
		"label.notSelected": "not selected",
		"label.none": "none",
		"label.notLoaded": "not loaded",
		"label.offsetUnknown": "offset unknown",
		"label.confidence": "confidence",
		"label.selectedItems": "{count} item(s) selected",
		"label.imageCount": "{count} image(s)",
		"label.filesSummary":
			"{files} files / {cameras} camera(s) / {audio} audio / {stills} still(s) / {subtitles} subtitle(s)",
		"role.master": "Camera 1 / master",
		"role.camera2": "Camera 2",
		"role.camera3": "Camera 3",
		"role.camera4": "Camera 4",
		"role.camera5": "Camera 5",
		"role.externalAudio": "External audio",
		"role.externalAudio2": "External audio 2",
		"role.stillInsert": "Still insert",
		"role.logo": "Logo",
		"role.subtitle": "Subtitle",
		"role.ignore": "Ignore",
		"role.overrideReason": "operator override",
		"dialog.selectStillImages": "Select still images",
		"dialog.selectSlot": "Select {slot}",
		"dialog.selectTool": "Select {id}",
		"dialog.selectMaterialFolder": "Select material folder",
		"dialog.selectMaterialFiles": "Select material files",
		"dialog.selectOutputVideo": "Select output video",
		"dialog.selectProjectFolder": "Select project folder",
		"dialog.deleteProjectTitle": "Delete project",
		"dialog.deleteProjectMessage": 'Delete project "{name}"?',
		"dialog.deleteProjectDetail": "This cannot be undone.\n{path}",
		"dialog.deleteProjectConfirm": "Delete",
		"filter.video": "Video",
		"filter.audioOrVideo": "Audio or video",
		"filter.image": "Image",
		"filter.stillImages": "Still images",
		"filter.mediaAndSubtitles": "Media and subtitles",
		"filter.allFiles": "All files",
		"filter.mp4Video": "MP4 video",
		"runLabel.render": "Render",
		"runLabel.sync": "Sync",
		"runLabel.transcribe": "Transcription",
		"runLabel.analyze": "Analysis",
		"runLabel.run": "Run",
		"format.runningButton": "Running {label}...",
		"format.runningMessage": "Running {label}",
		"format.startingMessage": "Starting {label}",
		"format.completeMessage": "{label} complete",
		"format.errorMessage": "{label} failed",
		"analysis.materialClassification": "Asset classification",
		"analysis.syncCamerasAudio": "Camera / audio sync",
		"analysis.transcription": "Transcription",
		"analysis.transcriptComparison": "Transcript comparison",
		"analysis.subtitleUi": "Subtitle UI refresh",
		"analysis.personOpenCv": "OpenCV person analysis",
		"analysis.blockingOpenCv": "OpenCV composition analysis",
		"analysis.referenceVideo": "Reference video analysis",
		"analysis.updatedOutput": "Output updated",
		"analysis.checkLogs": "Check the run log",
		"analysis.singleCameraSkipped": "Skipped because this is single-camera material",
		"analysis.noSubtitleCandidates": "No subtitle file or transcription result was found",
		"analysis.statusDone": "Done",
		"analysis.statusError": "Error",
		"analysis.statusRunning": "Running",
		"sync.noReport": "No camera sync report yet.",
		"validation.outputRequired": "Choose an output path.",
		"validation.projectRequired": "Create or select a project first.",
		"validation.output": "Output: {path}",
		"validation.masterRequiredForInterview":
			"Interview render requires Camera 1 / master. Ingest a material folder or set it manually.",
		"validation.singleCameraWarning": "No close-up material is set, so this will effectively render as one camera.",
		"validation.syncFirstWarning":
			"For new multicam material, run Auto-sync dropped cameras first to create app_sync_offsets.json.",
		"validation.shortenSilenceWarning":
			"When silence shortening is on, the output may become shorter than the selected duration. Turn it off if duration must stay fixed.",
		"validation.masterRequiredForSync": "Auto-sync requires Camera 1 / master.",
		"validation.syncTargetsRequired": "Auto-sync requires Camera 2 or later, or external audio.",
		"validation.syncSaved": "Camera/external-audio sync results will be saved.",
		"validation.stillCount": "Still inserts: {count}",
		"validation.stillMotion": "Text/diagram stills are inserted without zoom; photos use subtle zoom/pan.",
		"validation.preview": "Preview: {path}",
		"validation.personBbox": "Person bbox: {path}",
		"validation.editPlan": "Edit plan: {path}",
		"validation.analysisFps": "Analysis interval: {fps} fps",
		"validation.selectedVideos": "Analysis target: {count} selected video(s)",
		"validation.sourceRoots": "Analysis target: selected project videos",
		"validation.testAnalysis": "A test analysis length is set, so only part of the video will be analyzed.",
		"validation.referenceRequired": "Drag and drop one reference video.",
		"validation.referenceShort": "Reference video is analyzed as under 60 seconds. Longer videos stop at run time.",
		"validation.referenceProfile": "Reference profile: {path}",
		"validation.referenceBbox": "Reference person bbox: {path}",
		"validation.referenceEditPlan": "Reference edit plan: {path}",
		"validation.shortenNeedsInputOutput": "Silence shortening requires an input video and output path.",
		"validation.verificationNeedsInput": "Choose the video to process for this workflow.",
		"validation.thumbnailNeedsInput":
			"Thumbnail generation needs an input video, Camera 1 / master, or an analyzed camera source.",
		"validation.thumbnailOutput": "Thumbnail: {path}",
		"validation.thumbnailCandidatesNeedsInput":
			"Thumbnail candidate generation needs an input video, analyzed camera, or project image.",
		"validation.thumbnailCandidatesOutput": "Thumbnail candidates: {path}",
		"validation.thumbnailCandidateSettings": "Thumbnail candidates: {count} image(s) / {mode} / {color}",
		"validation.thumbnailDebugFaces": "Thumbnail candidates: face debug boxes ON",
		"validation.subtitleReviewNeedsProject":
			"Subtitle review needs a project output and current transcription result. Run transcription first.",
		"validation.subtitleReviewOutput": "Subtitle QA: {path}",
		"validation.subtitleReviewClips": "Subtitle QA clips: {path}",
		"validation.subtitleReviewRetranscribe": "Subtitle QA: re-transcribe flagged clips",
		"validation.subtitleCorrectionsMissing": "Enter correction rows before applying subtitle corrections.",
		"validation.subtitleCorrectionsOutput": "Subtitle correction report: {path}",
		"validation.subtitleSpeakerRolesOutput": "Subtitle speaker roles: {path}",
		"validation.subtitleSpeakerManualRoles": "Subtitle speaker roles: manual overrides set",
		"validation.subtitleSpeakerMouthMotion": "Subtitle speaker roles: mouth-motion diagnostic ON",
		"validation.transcriptComparisonOutput": "Transcript comparison: {path}",
		"validation.replaceAudioNeedsInputOutput": "Audio replacement needs an input video and output path.",
		"validation.replaceAudioNeedsExternal": "Select an external audio file before replacing video audio.",
		"validation.replaceAudioSamePath": "Choose an output path different from the input video before replacing audio.",
		"validation.replaceAudioOutput": "Audio replacement: {path}",
		"validation.replaceAudioSource": "Replacement audio: {path}",
		"validation.subtitleSpeakerRulesMissing":
			"Enter interviewer/omission ranges or patterns before classifying subtitle speaker roles.",
		"validation.audioExternal": "Audio: external {path}",
		"validation.audioFallbackMaster": "External audio is not set, so rendering will fall back to master video audio.",
		"validation.rightAudioFallback":
			"Right close-up audio is not set, so rendering will fall back to master video audio.",
		"validation.leftAudioFallback":
			"Left close-up audio is not set, so rendering will fall back to master video audio.",
		"validation.workflow": "Workflow: {label}",
		"validation.transcribe": "Transcription: {model} / {language}",
		"validation.subtitle": "Subtitles: {mode}",
		"validation.termsOn": "Glossary explanations: ON ({count} term(s))",
		"validation.termsOff": "Glossary explanations: OFF",
		"validation.denoiseOn": "Noise reduction: ON ({strength})",
		"validation.denoiseOff": "Noise reduction: OFF",
		"validation.colorMatchOn": "Camera color match: ON",
		"validation.colorMatchOff": "Camera color match: OFF",
		"validation.personCropOn": "Person crops: using analysis",
		"validation.personCropOff": "Person crops: OFF",
		"validation.transcriptSyncOn": "Sync fallback: transcript comparison for low scores",
		"validation.transcriptSyncOff": "Sync fallback: transcript comparison OFF",
		"validation.naturalCutsOn": "Camera cuts: adjusted to dialogue gaps",
		"validation.naturalCutsOff": "Camera cuts: generated boundaries",
		"validation.audioMasteringOn": "Audio mastering: ON",
		"validation.audioMasteringOff": "Audio mastering: OFF",
		"validation.encoder": "Encode: {preset} / CRF {crf}",
		"validation.musicFull": "Music: ON / whole video / level {volume}%",
		"validation.musicOmission": "Music: ON / omission ranges only / level {volume}%",
		"validation.musicAutoRanges": "Omission ranges: auto-detect from overlays and also include manual ranges.",
		"validation.musicManualRanges": "Omission ranges: manual only",
		"validation.musicRangesMissing": "Enter ranges when manual-only omission ranges are selected.",
		"validation.musicOff": "Music: OFF",
		"validation.omissionCardOn": "Omission card: ON / {duration}s",
		"validation.omissionCardMissingRanges":
			"Enter replacement ranges or omission title ranges before using omission cards.",
		"validation.omissionCardOff": "Omission card: OFF",
		"validation.silenceOn": "Silence shortening: ON",
		"validation.silenceOff": "Silence shortening: OFF",
		"validation.previousSync": "Previous sync: {role} score {score}",
		"validation.lowSyncScore": "Some previous auto-sync scores are low. Check audio drift with a short QA render.",
		"notification.renderComplete": "Render complete.",
		"notification.analysisComplete": "Asset analysis, transcription, and OpenCV analysis are complete.",
		"notification.analysisCompleteCheck": "Analysis is complete. Check the partial results.",
		"log.projectNotSelected": "No project is selected",
		"log.cannotDeleteDuringIngest": "Cannot delete while asset analysis is running",
		"log.cannotSwitchDuringIngest": "Cannot switch projects while asset analysis is running",
		"log.selectMaterialFirst": "Select a material folder or files first",
		"log.glossaryRequired": "Enter a term, detection pattern, and explanation",
	},
};

const translationKeyByText = new Map<string, string>();
for (const locale of ["ja", "en"] as Locale[]) {
	for (const [key, value] of Object.entries(messages[locale])) {
		if (value && !value.includes("{") && !translationKeyByText.has(value)) {
			translationKeyByText.set(value, key);
		}
	}
}
translationKeyByText.set("手動選択 / style reference under 60s", "asset.referenceDescription");

const translatedTextNodes = new WeakMap<Text, string>();
const translatedAttributes = new WeakMap<Element, Record<string, string>>();

function t(key: string, values: Record<string, string | number> = {}) {
	const template = messages[state.language]?.[key] || messages.en[key] || messages.ja[key] || key;
	return Object.entries(values).reduce(
		(result, [name, value]) => result.replaceAll(`{${name}}`, String(value)),
		template,
	);
}

function localizePlainText(value: any) {
	const text = String(value || "");
	const trimmed = text.trim();
	if (!trimmed) {
		return text;
	}
	const key = translationKeyByText.get(trimmed);
	return key ? text.replace(trimmed, t(key)) : text;
}

function applyTranslations(root: ParentNode = document.body) {
	document.documentElement.lang = state.language;
	document.title = t("app.title");
	const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
	let node = walker.nextNode() as Text | null;
	while (node) {
		const trimmed = node.textContent?.trim() || "";
		const key = translatedTextNodes.get(node) || translationKeyByText.get(trimmed);
		if (key) {
			translatedTextNodes.set(node, key);
			node.textContent = (node.textContent || "").replace(trimmed, t(key));
		}
		node = walker.nextNode() as Text | null;
	}
	const attributes = ["aria-label", "placeholder", "title"];
	(root instanceof Element
		? [root, ...Array.from(root.querySelectorAll("*"))]
		: Array.from(root.querySelectorAll("*"))
	).forEach((element) => {
		const stored = translatedAttributes.get(element) || {};
		for (const attribute of attributes) {
			const value = element.getAttribute(attribute);
			const key = stored[attribute] || (value ? translationKeyByText.get(value.trim()) : "");
			if (key) {
				stored[attribute] = key;
				element.setAttribute(attribute, t(key));
			}
		}
		if (Object.keys(stored).length) {
			translatedAttributes.set(element, stored);
		}
	});
	$$("[data-language]").forEach((button) => {
		button.classList.toggle("selected", button.dataset.language === state.language);
		button.setAttribute("aria-pressed", String(button.dataset.language === state.language));
	});
}

function setLanguageMenuOpen(open: boolean) {
	const popover = $("#languagePopover");
	const button = $("#languageMenuButton");
	if (!popover || !button) {
		return;
	}
	popover.hidden = !open;
	button.setAttribute("aria-expanded", String(open));
}

function setActiveSection(section: string) {
	state.activeSection = section || "assets";
	$$(".step-button").forEach((button) => {
		const active = button.dataset.section === state.activeSection;
		button.classList.toggle("active", active);
		button.setAttribute("aria-selected", String(active));
	});
	$$("[data-panel]").forEach((panel) => {
		panel.hidden = panel.dataset.panel !== state.activeSection;
	});
}

function renderWorkspaceLabel() {
	const label = $("#workspacePath");
	if (!label) {
		return;
	}
	label.textContent = t("app.workspaceLabel");
	label.title = state.env?.videoEditRoot || "";
}

function setLanguage(language: Locale) {
	state.language = normalizeLanguage(language);
	localStorage.setItem(LANGUAGE_STORAGE_KEY, state.language);
	setLanguageMenuOpen(false);
	applyTranslations();
	renderWorkspaceLabel();
	setStatus(state.statusText, state.statusKind);
	setDirectRunRunning(state.directRunRunning, state.runningAction ? directRunLabel(state.runningAction) : "");
	renderGlossaryList();
	renderFileSlots();
	renderWorkflowMediaPreviews();
	renderOutputTargetPreview();
	renderMediaManifest();
	renderStillImageList();
	renderAnalysisResults();
	renderProjectDialogList();
	renderSyncReport();
	renderOutputPreview();
	renderCodexModelOptions();
	renderCodexModelStatus();
	updateRunSummary();
	refreshCommand();
}

function codexModelValue(model: CodexModel) {
	return String(model.model || model.id || "").trim();
}

function normalizeCodexModel(item: any): CodexModel | null {
	const id = String(item?.id || item?.model || "").trim();
	const model = String(item?.model || item?.id || "").trim();
	if (!id || !model) {
		return null;
	}
	return {
		id,
		model,
		displayName: String(item?.displayName || item?.name || model),
		defaultReasoningEffort: item?.defaultReasoningEffort ? String(item.defaultReasoningEffort) : "",
		isDefault: Boolean(item?.isDefault),
		hidden: Boolean(item?.hidden),
	};
}

function renderCodexModelStatus() {
	const status = $("#codexModelStatus");
	if (status) {
		status.textContent = t(state.codexModelStatusKey, state.codexModelStatusValues);
	}
}

function setCodexModelStatus(key: string, values: Record<string, string | number> = {}) {
	state.codexModelStatusKey = key;
	state.codexModelStatusValues = values;
	renderCodexModelStatus();
}

function renderCodexModelOptions() {
	const select = $("#modelName") as HTMLSelectElement | null;
	if (!select) {
		return;
	}
	let selected = state.codexModel || select.value || "";
	select.innerHTML = "";
	const defaultOption = document.createElement("option");
	defaultOption.value = "";
	defaultOption.textContent = t("codex.modelDefault");
	select.appendChild(defaultOption);

	const seen = new Set([""]);
	for (const model of state.codexModels) {
		const value = codexModelValue(model);
		if (!value || seen.has(value)) {
			continue;
		}
		seen.add(value);
		const option = document.createElement("option");
		option.value = value;
		option.textContent = model.isDefault
			? `${model.displayName || value} (${t("codex.modelDefaultSuffix")})`
			: model.displayName || value;
		option.title = value;
		select.appendChild(option);
	}

	if (selected && !seen.has(selected)) {
		if (state.codexModels.length) {
			log("saved model unavailable; using Codex default", { model: selected });
			selected = "";
			state.codexModel = "";
		} else {
			const option = document.createElement("option");
			option.value = selected;
			option.textContent = `${selected} (${t("codex.modelCustomSuffix")})`;
			option.title = selected;
			select.appendChild(option);
		}
	}
	select.value = selected;
	state.codexModel = select.value;
}

async function loadCodexModels() {
	const button = $("#refreshCodexModels") as HTMLButtonElement | null;
	if (button) {
		button.disabled = true;
	}
	setCodexModelStatus("codex.modelLoading");
	try {
		const result = await editApp.listCodexModels({ limit: 100, includeHidden: false });
		state.codexModels = (Array.isArray(result?.data) ? result.data : [])
			.map(normalizeCodexModel)
			.filter((item): item is CodexModel => Boolean(item));
		renderCodexModelOptions();
		setCodexModelStatus("codex.modelLoaded", { count: state.codexModels.length });
	} catch (error) {
		state.codexModels = [];
		renderCodexModelOptions();
		setCodexModelStatus("codex.modelLoadFailed");
		log("model/list error", { message: error.message });
	} finally {
		if (button) {
			button.disabled = false;
		}
	}
}

function selectedCodexReasoningEffort() {
	const selected = state.codexModel || (($("#modelName") as HTMLSelectElement | null)?.value ?? "");
	const model = state.codexModels.find((item) => codexModelValue(item) === selected);
	return model?.defaultReasoningEffort || "medium";
}

function selectedCodexModelForRun() {
	const select = $("#modelName") as HTMLSelectElement | null;
	const selected = String(state.codexModel || select?.value || "").trim();
	if (selected && state.codexModels.length && !state.codexModels.some((item) => codexModelValue(item) === selected)) {
		log("selected model unavailable; using Codex default", { model: selected });
		state.codexModel = "";
		if (select) {
			select.value = "";
		}
		saveState();
		return "";
	}
	return selected;
}

const fileSlotLabelKeys = {
	masterVideo: "asset.master",
	rightCloseVideo: "asset.rightClose",
	leftCloseVideo: "asset.leftClose",
	referenceVideo: "asset.referenceVideo",
	externalAudio: "asset.externalAudio",
	logo: "asset.logo",
	stillImages: "asset.stillImages",
};

function fileSlotLabel(slot: string) {
	return t(fileSlotLabelKeys[slot] || slot);
}

function filtersForSlot(slot: string) {
	const filters = fileFilterSpecs[slot] || [{ nameKey: "filter.allFiles", extensions: ["*"] }];
	return filters.map((filter) => ({
		name: t(filter.nameKey),
		extensions: filter.extensions,
	}));
}

function shortPath(value) {
	if (!value) {
		return t("label.notSelected");
	}
	const parts = value.split(/[\\/]/);
	return parts.length > 2 ? `${parts.at(-2)}\\${parts.at(-1)}` : value;
}

function joinPath(root: string, ...parts: string[]) {
	return [root.replace(/[\\/]+$/, ""), ...parts.map((part) => part.replace(/^[\\/]+|[\\/]+$/g, ""))].join("\\");
}

function formatBytes(value: any) {
	const bytes = Number(value || 0);
	if (!Number.isFinite(bytes) || bytes <= 0) {
		return "";
	}
	const units = ["B", "KB", "MB", "GB", "TB"];
	let size = bytes;
	let unitIndex = 0;
	while (size >= 1024 && unitIndex < units.length - 1) {
		size /= 1024;
		unitIndex += 1;
	}
	return `${size >= 10 || unitIndex === 0 ? size.toFixed(0) : size.toFixed(1)} ${units[unitIndex]}`;
}

function formatDuration(value: any) {
	const seconds = Number(value || 0);
	if (!Number.isFinite(seconds) || seconds <= 0) {
		return "";
	}
	const total = Math.round(seconds);
	const hours = Math.floor(total / 3600);
	const minutes = Math.floor((total % 3600) / 60);
	const rest = total % 60;
	if (hours) {
		return `${hours}:${String(minutes).padStart(2, "0")}:${String(rest).padStart(2, "0")}`;
	}
	return `${minutes}:${String(rest).padStart(2, "0")}`;
}

function outputPreviewTarget(_kind = state.outputPreviewKind) {
	return $("#outputPath")?.value?.trim() || activeOutputRoot();
}

function outputPreviewTitle(kind = state.outputPreviewKind) {
	if (kind === "output") {
		return t("preview.outputTitle");
	}
	return t("preview.heading");
}

function previewKindLabel(kind: string) {
	const key = `preview.${kind}`;
	return messages[state.language]?.[key] || messages.en[key] || t("preview.file");
}

function previewEntryMeta(entry: any) {
	if (entry.kind === "folder") {
		return [
			t("preview.folderCounts", { files: entry.fileCount || 0, folders: entry.folderCount || 0 }),
			entry.mediaCount ? t("preview.mediaCount", { count: entry.mediaCount }) : "",
		].filter(Boolean);
	}
	const resolution = entry.width && entry.height ? `${entry.width}x${entry.height}` : "";
	return [
		entry.duration ? formatDuration(entry.duration) : "",
		entry.extension || previewKindLabel(entry.kind),
		resolution,
		entry.videoCodec || entry.audioCodec || "",
		formatBytes(entry.sizeBytes),
	].filter(Boolean);
}

function mediaRoleLabel(role: string) {
	for (const [value, label] of [
		["master", t("role.master")],
		["camera2", t("role.camera2")],
		["camera3", t("role.camera3")],
		["camera4", t("role.camera4")],
		["camera5", t("role.camera5")],
		["external", t("role.externalAudio")],
		["external2", t("role.externalAudio2")],
		["still", t("role.stillInsert")],
		["logo", t("role.logo")],
		["subtitle", t("role.subtitle")],
		["ignore", t("role.ignore")],
	]) {
		if (value === role) {
			return label;
		}
	}
	return role;
}

function fileNameFromPath(filePath: string) {
	return (
		String(filePath || "")
			.split(/[\\/]/)
			.filter(Boolean)
			.at(-1) || ""
	);
}

function extensionLabel(value: string) {
	const text = String(value || "");
	return (
		text.startsWith(".") ? text.slice(1) : text.includes(".") ? text.split(".").at(-1) || text : text
	).toUpperCase();
}

function extensionFromPath(filePath: string) {
	const name = fileNameFromPath(filePath);
	return name.includes(".") ? name.split(".").at(-1) || "" : "";
}

function previewKindFromPath(filePath: string) {
	const extension = extensionFromPath(filePath).toLowerCase();
	if (["mp4", "mov", "m4v", "mkv", "avi", "mts", "m2ts", "webm"].includes(extension)) {
		return "video";
	}
	if (["png", "jpg", "jpeg", "webp", "gif", "bmp"].includes(extension)) {
		return "image";
	}
	if (["wav", "mp3", "aac", "m4a", "flac", "aiff", "aif"].includes(extension)) {
		return "audio";
	}
	if (["srt", "ass", "vtt"].includes(extension)) {
		return "subtitle";
	}
	return "other";
}

function parentDirectoryFromPath(filePath: string) {
	return String(filePath || "").replace(/[\\/][^\\/]*$/, "");
}

function metadataForPreview(preview: any) {
	return preview?.metadata || preview || {};
}

function mediaMetaBadges(preview: any) {
	const metadata = metadataForPreview(preview);
	const resolution = metadata.width && metadata.height ? `${metadata.width}x${metadata.height}` : "";
	const duration = metadata.duration || preview?.duration;
	return [
		duration ? formatDuration(duration) : "",
		extensionLabel(preview?.extension || preview?.name || ""),
		resolution,
		metadata.videoCodec || preview?.videoCodec || metadata.audioCodec || preview?.audioCodec || "",
		formatBytes(preview?.sizeBytes),
	].filter(Boolean);
}

function mediaThumbnailElement(preview: any) {
	const thumb = document.createElement("div");
	thumb.className = `media-thumb ${preview?.kind || "empty"}`;
	const dataUrl = preview?.thumbnailDataUrl;
	if (dataUrl) {
		const image = document.createElement("img");
		image.src = dataUrl;
		image.alt = "";
		thumb.appendChild(image);
		return thumb;
	}
	const placeholder = document.createElement("span");
	placeholder.textContent = preview?.kind ? extensionLabel(preview.extension) || previewKindLabel(preview.kind) : "-";
	thumb.appendChild(placeholder);
	return thumb;
}

function manifestPreviewForPath(filePath: string) {
	const resolved = String(filePath || "");
	return manifestFiles().find((item) => item.path === resolved || item.originalPath === resolved) || null;
}

function previewForSlot(slot: string) {
	const value = state.files[slot];
	if (!value) {
		return null;
	}
	return (
		manifestPreviewForPath(value) ||
		state.filePreviews[value] || {
			path: value,
			name: fileNameFromPath(value),
			kind: "other",
			extension: value.includes(".") ? value.split(".").at(-1) : "",
		}
	);
}

function renderPreviewThumb(entry: any) {
	const thumb = document.createElement("div");
	thumb.className = `preview-thumb ${entry.kind}`;
	if (entry.kind === "folder" && entry.previewThumbnails?.length) {
		const stack = document.createElement("div");
		stack.className = "folder-preview-stack";
		entry.previewThumbnails.slice(0, 3).forEach((thumbnail) => {
			const image = document.createElement("img");
			image.src = thumbnail;
			image.alt = "";
			stack.appendChild(image);
		});
		thumb.appendChild(stack);
		return thumb;
	}
	if (entry.thumbnailDataUrl) {
		const image = document.createElement("img");
		image.src = entry.thumbnailDataUrl;
		image.alt = "";
		thumb.appendChild(image);
		return thumb;
	}
	const placeholder = document.createElement("span");
	placeholder.textContent = entry.kind === "folder" ? "DIR" : entry.extension || previewKindLabel(entry.kind);
	thumb.appendChild(placeholder);
	return thumb;
}

function renderOutputPreview() {
	const section = $("#outputPreview");
	const title = $("#outputPreviewTitle");
	const summary = $("#outputPreviewSummary");
	const pathLabel = $("#outputPreviewPath");
	const list = $("#outputPreviewList");
	if (!section || !title || !summary || !pathLabel || !list) {
		return;
	}
	if (!state.outputPreview && !state.outputPreviewLoading) {
		section.hidden = true;
		return;
	}
	section.hidden = false;
	title.textContent = outputPreviewTitle();
	list.innerHTML = "";
	if (state.outputPreviewLoading) {
		summary.textContent = t("preview.loading");
		const target = outputPreviewTarget();
		pathLabel.textContent = shortPath(target);
		pathLabel.title = target;
		list.textContent = t("preview.loading");
		return;
	}
	const preview = state.outputPreview || {};
	const entries = preview.entries || [];
	const previewPath = preview.path || preview.targetPath || outputPreviewTarget();
	pathLabel.textContent = shortPath(previewPath);
	pathLabel.title = preview.targetPath || preview.path || "";
	summary.textContent = preview.ok
		? t("preview.summary", { count: entries.length })
		: preview.reason === "missing-path"
			? t("preview.missing")
			: t("preview.empty");
	if (!entries.length) {
		list.textContent = preview.ok ? t("preview.empty") : t("preview.missing");
		return;
	}
	entries.forEach((entry) => {
		const card = document.createElement("button");
		card.type = "button";
		card.className = `preview-card ${entry.kind}`;
		card.dataset.previewPath = entry.path;
		card.title = entry.path;
		const thumb = renderPreviewThumb(entry);
		const detail = document.createElement("div");
		detail.className = "preview-detail";
		const name = document.createElement("strong");
		name.textContent = entry.name;
		const kind = document.createElement("small");
		kind.textContent = previewKindLabel(entry.kind);
		const meta = document.createElement("div");
		meta.className = "preview-meta";
		previewEntryMeta(entry).forEach((item) => {
			const badge = document.createElement("span");
			badge.textContent = item;
			meta.appendChild(badge);
		});
		detail.append(name, kind, meta);
		card.append(thumb, detail);
		list.appendChild(card);
	});
	$$("[data-preview-path]").forEach((button) => {
		button.addEventListener("click", () => {
			editApp.showPath(button.dataset.previewPath);
		});
	});
}

async function loadOutputPreview(kind: string) {
	state.outputPreviewKind = kind;
	state.outputPreviewLoading = true;
	renderOutputPreview();
	try {
		state.outputPreview = await editApp.listDirectory({
			targetPath: outputPreviewTarget(kind),
			maxEntries: 96,
		});
	} catch (error) {
		state.outputPreview = {
			ok: false,
			reason: error.message || "error",
			targetPath: outputPreviewTarget(kind),
			path: "",
			entries: [],
		};
		log("preview error", { message: error.message });
	} finally {
		state.outputPreviewLoading = false;
		renderOutputPreview();
	}
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
	return "";
}

function activeProjectVideoSourceRoot() {
	return state.project ? joinPath(state.project.sourceRoot, "video") : "";
}

function mediaManifestPath() {
	return (
		state.mediaManifest?.manifestPath ||
		(activeOutputRoot() ? joinPath(activeOutputRoot(), "reports", "media_manifest.json") : "")
	);
}

function manifestFiles() {
	return state.mediaManifest?.files || [];
}

function manifestCameras() {
	return state.mediaManifest?.cameras || [];
}

function manifestAudioSources() {
	return state.mediaManifest?.audio || [];
}

function manifestImagesByRole(role: string) {
	return (state.mediaManifest?.images || []).filter((item) => item.role === role);
}

function selectedMasterVideoPath() {
	return manifestCameras().find((item) => item.role === "master")?.path || state.files.masterVideo;
}

function progressPercent(value: any) {
	const number = Number(value);
	if (!Number.isFinite(number)) {
		return 0;
	}
	return Math.max(0, Math.min(100, Math.round(number * 100)));
}

function setIngestProgress(payload: any) {
	const percent = progressPercent(payload?.progress);
	const fill = $("#ingestProgressFill");
	const percentLabel = $("#ingestProgressPercent");
	const text = $("#ingestProgressText");
	const pathLabel = $("#ingestProgressPath");
	const busyFill = $("#appBusyProgressFill");
	const busyPercent = $("#appBusyProgressPercent");
	const busyMessage = $("#appBusyMessage");
	if (fill) {
		fill.style.width = `${percent}%`;
	}
	if (percentLabel) {
		percentLabel.textContent = `${percent}%`;
	}
	if (busyFill) {
		busyFill.style.width = `${percent}%`;
	}
	if (busyPercent) {
		busyPercent.textContent = `${percent}%`;
	}
	if (text) {
		const count = payload?.total && payload.total > 0 ? ` (${payload.current || 0}/${payload.total})` : "";
		text.textContent = `${localizePlainText(payload?.message || t("progress.waitingAnalysis"))}${count}`;
	}
	if (busyMessage && payload?.message) {
		busyMessage.textContent = localizePlainText(payload.message);
	}
	if (pathLabel) {
		pathLabel.textContent = payload?.path ? shortPath(String(payload.path)) : "-";
		pathLabel.title = payload?.path || "";
	}
}

function setDirectRunRunning(running: boolean, label = "") {
	state.directRunRunning = running;
	const runButton = $("#runPreset");
	if (runButton) {
		runButton.disabled = running;
		runButton.textContent = running
			? t("format.runningButton", { label: label || t("runLabel.run") })
			: t("action.runPresetScript");
	}
	updateCodexRunControls();
}

function updateCodexRunControls() {
	const sendButton = $("#sendRequest");
	const stopButtons = [$("#stopCodexTurn"), $("#interrupt")].filter(Boolean);
	if (sendButton) {
		sendButton.disabled = state.directRunRunning || state.codexTurnRunning;
		sendButton.textContent = state.codexTurnRunning ? t("action.codexRunning") : t("action.runWithCodex");
	}
	for (const button of stopButtons) {
		button.disabled = !state.codexTurnRunning || state.codexInterruptRequested;
		button.textContent = state.codexInterruptRequested ? t("action.stoppingCodex") : t("action.stopCodex");
	}
}

function setCodexTurnRunning(running: boolean, interruptRequested = false) {
	state.codexTurnRunning = running;
	state.codexInterruptRequested = running && interruptRequested;
	updateCodexRunControls();
}

function setIngestRunning(running: boolean) {
	state.ingestRunning = running;
	const analyzeButton = $("#analyzeMaterialDirectory");
	const cancelButton = $("#cancelMaterialAnalysis");
	const folderButton = $("#pickMaterialDirectory");
	const filesButton = $("#pickMaterialFiles");
	if (analyzeButton) {
		analyzeButton.disabled = running;
	}
	if (cancelButton) {
		cancelButton.disabled = !running;
	}
	if (folderButton) {
		folderButton.disabled = running;
	}
	if (filesButton) {
		filesButton.disabled = running;
	}
}

function setAppLocked(locked: boolean, message = "", title = t("busy.processing")) {
	state.appLocked = locked;
	const overlay = $("#appBusyOverlay");
	const busyTitle = $("#appBusyTitle");
	const busyMessage = $("#appBusyMessage");
	if (overlay) {
		overlay.hidden = !locked;
	}
	if (busyTitle) {
		busyTitle.textContent = localizePlainText(title);
	}
	if (busyMessage) {
		busyMessage.textContent = message ? localizePlainText(message) : t("busy.wait");
	}
	$$("button, input, select, textarea").forEach((element) => {
		element.disabled = locked;
	});
	if (!locked) {
		setIngestRunning(state.ingestRunning);
	}
}

function setAnalysisResult(key: string, label: string, status: string, detail: string, path = "") {
	const next = { key, label, status, detail, path };
	const index = state.analysisResults.findIndex((item) => item.key === key);
	if (index >= 0) {
		state.analysisResults[index] = next;
	} else {
		state.analysisResults.push(next);
	}
	renderAnalysisResults();
	saveState();
	persistAnalysisStateFile();
}

function normalizeAnalysisResult(item: any): AnalysisResult | null {
	const key = String(item?.key || "").trim();
	if (!key) {
		return null;
	}
	const status = ["done", "error", "running"].includes(String(item?.status)) ? String(item.status) : "done";
	return {
		key,
		label: String(item?.label || ""),
		status,
		detail: String(item?.detail || ""),
		path: String(item?.path || ""),
	};
}

function setAnalysisResults(results: any[], options: { persistFile?: boolean } = {}) {
	state.analysisResults = results.map(normalizeAnalysisResult).filter((item): item is AnalysisResult => Boolean(item));
	renderAnalysisResults();
	saveState();
	if (options.persistFile !== false) {
		persistAnalysisStateFile();
	}
}

function renderAnalysisResults() {
	const list = $("#analysisResultList");
	if (!list) {
		return;
	}
	if (!state.analysisResults.length) {
		list.textContent = t("materials.analysisEmpty");
		return;
	}
	list.innerHTML = "";
	for (const item of state.analysisResults) {
		const row = document.createElement("div");
		row.className = `analysis-result-row ${item.status === "error" ? "error" : item.status === "done" ? "done" : ""}`;
		const label = document.createElement("strong");
		label.textContent = analysisLabel(item.key, item.label);
		const detail = document.createElement("span");
		detail.textContent = localizePlainText(item.detail);
		detail.title = item.path || item.detail;
		const status = document.createElement("span");
		status.className = "status";
		status.textContent =
			item.status === "done"
				? t("analysis.statusDone")
				: item.status === "error"
					? t("analysis.statusError")
					: t("analysis.statusRunning");
		row.append(label, detail, status);
		list.appendChild(row);
	}
}

async function notifyAnalysisComplete(message: string) {
	if (!("Notification" in window)) {
		return;
	}
	try {
		if (Notification.permission === "default") {
			await Notification.requestPermission();
		}
		if (Notification.permission === "granted") {
			new Notification("Video Edit", { body: message });
		}
	} catch (error) {
		log("notification skipped", { message: error.message });
	}
}

function setMaterialSources(paths: string[]) {
	const selected = [
		...new Set(
			paths
				.map(String)
				.map((item) => item.trim())
				.filter(Boolean),
		),
	];
	state.materialPaths = selected;
	state.mediaDirectory = selected[0] || "";
	state.mediaManifest = null;
	setAnalysisResults([]);
	setAnalysisTitleText("");
	setIngestProgress({
		progress: 0,
		message: selected.length ? t("progress.pressAnalyze") : t("progress.waitingAnalysis"),
		path: materialSourceLabel(),
	});
	renderMediaManifest();
	refreshPrompt();
}

function setMaterialDirectory(directoryPath: string) {
	setMaterialSources(directoryPath ? [directoryPath] : []);
}

function addMaterialSources(paths: string[]) {
	setMaterialSources([...state.materialPaths, ...paths]);
}

function materialSourceLabel() {
	if (!state.materialPaths.length) {
		return "";
	}
	return state.materialPaths.length === 1 ? state.materialPaths[0] : `${state.materialPaths.length} selected item(s)`;
}

function formatProjectDate(value: string) {
	const date = new Date(value);
	if (!Number.isFinite(date.getTime())) {
		return "";
	}
	return new Intl.DateTimeFormat(state.language === "ja" ? "ja-JP" : "en-US", {
		year: "numeric",
		month: "2-digit",
		day: "2-digit",
		hour: "2-digit",
		minute: "2-digit",
	}).format(date);
}

function setAnalysisTitleText(title: string) {
	state.analysisTitleText = String(title || "").trim();
	const input = $("#titleText");
	if (input) {
		input.value = state.analysisTitleText;
	}
}

function setProject(project: ProjectInfo | null) {
	const previousProjectId = state.project?.id || "";
	state.project = project;
	state.projectStatePath = project ? joinPath(project.root, "project_state.json") : "";
	if (!project || project.id !== previousProjectId) {
		state.projectStateRevision = 0;
	}
	setAnalysisTitleText("");
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
		label.textContent = project ? t("project.ready", { name: project.name }) : t("project.noProjectSelected");
	}
	const preview = $("#projectNamePreview");
	if (preview) {
		preview.textContent = project ? project.name : t("project.noProjectSelected");
	}
	setDefaultProjectOutput(false);
	renderProjectDialogList();
	refreshPrompt();
}

function setProjectDialogOpen(open: boolean) {
	const dialog = $("#projectDialog");
	if (!dialog) {
		return;
	}
	dialog.hidden = !open;
	if (open) {
		const input = $("#projectDialogName");
		if (input) {
			input.value = formValue("projectName") && !state.project ? formValue("projectName") : "";
		}
		void loadProjectList();
		window.setTimeout(() => {
			($("#projectDialogName") || $("#closeProjectDialog"))?.focus();
		}, 0);
	}
}

function renderProjectDialogList() {
	const list = $("#projectDialogList");
	if (!list) {
		return;
	}
	list.innerHTML = "";
	if (state.projectListLoading) {
		const empty = document.createElement("div");
		empty.className = "project-dialog-empty";
		empty.textContent = t("project.dialogLoading");
		list.appendChild(empty);
		return;
	}
	if (!state.projectList.length) {
		const empty = document.createElement("div");
		empty.className = "project-dialog-empty";
		empty.textContent = t("project.dialogEmpty");
		list.appendChild(empty);
		return;
	}
	for (const entry of state.projectList) {
		const project = entry.project;
		const button = document.createElement("button");
		button.type = "button";
		button.className = `project-list-item ${state.project?.id === project.id ? "active" : ""}`;
		button.addEventListener("click", () => openProject(entry));

		const main = document.createElement("div");
		main.className = "project-list-main";
		const title = document.createElement("strong");
		title.textContent = project.name || project.id;
		title.title = project.root;
		const pathLabel = document.createElement("small");
		pathLabel.textContent = shortPath(project.root);
		pathLabel.title = project.root;
		const meta = document.createElement("div");
		meta.className = "project-list-meta";
		const updated = formatProjectDate(entry.updatedAt || entry.lastModifiedAt);
		for (const text of [
			updated ? t("project.dialogUpdated", { date: updated }) : "",
			entry.hasManifest
				? t("project.dialogMediaCount", { count: entry.mediaCount || 0 })
				: t("project.dialogNoManifest"),
		].filter(Boolean)) {
			const badge = document.createElement("span");
			badge.textContent = text;
			meta.appendChild(badge);
		}
		main.append(title, pathLabel, meta);
		button.appendChild(main);
		if (state.project?.id === project.id) {
			const active = document.createElement("span");
			active.className = "project-active-badge";
			active.textContent = t("project.dialogActive");
			button.appendChild(active);
		}
		list.appendChild(button);
	}
}

async function loadProjectList() {
	state.projectListLoading = true;
	renderProjectDialogList();
	try {
		const result = await editApp.listProjects();
		state.projectList = Array.isArray(result?.projects) ? result.projects : [];
	} catch (error) {
		state.projectList = [];
		log("project list failed", { message: error.message });
	} finally {
		state.projectListLoading = false;
		renderProjectDialogList();
	}
}

async function restoreLatestProjectFromDisk() {
	if (state.project) {
		return false;
	}
	try {
		const result = await editApp.listProjects();
		const entries = Array.isArray(result?.projects) ? result.projects : [];
		state.projectList = entries;
		renderProjectDialogList();
		const entry =
			entries.find((candidate) => candidate?.project?.id && candidate.hasManifest) ||
			entries.find((candidate) => candidate?.project?.id);
		if (!entry?.project) {
			return false;
		}
		const loaded = await editApp.loadProject({ project: entry.project });
		if (!loaded?.project) {
			return false;
		}
		await activateProject(loaded.project, loaded.manifest || null);
		log("project restored from disk", {
			id: loaded.project.id,
			root: loaded.project.root,
			manifest: loaded.manifest?.manifestPath || null,
		});
		return true;
	} catch (error) {
		log("project restore failed", { message: error.message });
		return false;
	}
}

async function activateProject(project: ProjectInfo, manifest: MediaManifest | null = null) {
	setProject(project);
	clearSelectedAssets();
	setAnalysisResults([], { persistFile: false });
	setMediaManifest(manifest || null);
	const loadedProjectState = await loadProjectStateFile(project);
	if (!loadedProjectState) {
		await persistProjectStateFileNow();
	}
	await refreshTextOverlayFromAnalysis(state.mediaManifest || manifest || null);
	if (!(await loadAnalysisStateFile(project))) {
		await restoreAnalysisResultsFromOutputs(state.mediaManifest || manifest || null);
	}
	if (!state.mediaManifest) {
		setIngestProgress({
			progress: 0,
			message: t("materials.folderNotAnalyzed"),
			path: "",
		});
	}
	await refreshSyncReport();
	refreshPrompt();
}

async function openProject(entry: ProjectListEntry) {
	if (state.ingestRunning) {
		log("project switch skipped", { reason: t("log.cannotSwitchDuringIngest") });
		return;
	}
	try {
		const result = await editApp.loadProject({ project: entry.project });
		if (!result?.project) {
			return;
		}
		setProjectDialogOpen(false);
		await activateProject(result.project, result.manifest || null);
		log("project switched", {
			id: result.project.id,
			root: result.project.root,
			manifest: result.manifest?.manifestPath || null,
		});
		void loadProjectList();
	} catch (error) {
		log("project switch failed", { message: error.message });
	}
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
	if (preserveExisting && current) {
		return;
	}
	const mode = state.subtitleMode === "punchline" ? "punchline" : "full_transcript";
	outputPath.value = joinPath(state.project.outputRoot, "videos", `codex_edit_${mode}.mp4`);
	renderOutputTargetPreview();
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
		list.textContent = t("glossary.notLoaded");
		return;
	}
	list.innerHTML = "";
	terms.forEach((term, index) => {
		const row = document.createElement("div");
		row.className = "glossary-row";
		row.innerHTML = `
			<input type="checkbox" data-glossary-enabled="${index}" ${term.enabled ? "checked" : ""} />
			<input data-glossary-label="${index}" value="${escapeHtml(term.label)}" aria-label="${escapeHtml(t("glossary.termLabel"))}" />
			<input data-glossary-patterns="${index}" value="${escapeHtml(term.patterns)}" aria-label="${escapeHtml(t("glossary.termPatterns"))}" />
			<input data-glossary-description="${index}" value="${escapeHtml(term.description)}" aria-label="${escapeHtml(t("glossary.termDescription"))}" />
			<button type="button" data-glossary-remove="${index}" title="${escapeHtml(t("action.remove"))}">×</button>
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
	state.statusText = text;
	state.statusKind = kind;
	const status = $("#serverStatus");
	status.innerHTML = `<span class="status-dot ${kind}"></span><span>${localizePlainText(text)}</span>`;
}

function codexErrorMessage(error: any): string {
	if (!error) {
		return "";
	}
	const raw = typeof error === "string" ? error : error.message || error.error?.message || error.codexErrorInfo || "";
	if (!raw) {
		return "";
	}
	try {
		const parsed = JSON.parse(raw);
		return codexErrorMessage(parsed.error || parsed) || raw;
	} catch {
		return String(raw);
	}
}

function renderFileSlot(slot: string) {
	const label = $(`#${slot}Label`);
	if (!label) {
		return;
	}
	const preview = previewForSlot(slot);
	label.innerHTML = "";
	label.className = "asset-preview";
	if (!preview) {
		label.classList.add("empty");
		label.textContent = t("materials.unselected");
		label.title = "";
		return;
	}
	label.classList.remove("empty");
	label.title = preview.path || state.files[slot] || "";
	const thumb = mediaThumbnailElement(preview);
	const detail = document.createElement("span");
	detail.className = "asset-preview-detail";
	const name = document.createElement("strong");
	name.textContent = preview.name || fileNameFromPath(state.files[slot]);
	const meta = document.createElement("small");
	meta.textContent = mediaMetaBadges(preview).join(" / ") || previewKindLabel(preview.kind || "other");
	detail.append(name, meta);
	label.append(thumb, detail);
}

function renderFileSlots() {
	["masterVideo", "rightCloseVideo", "leftCloseVideo", "referenceVideo", "externalAudio", "logo"].forEach(
		renderFileSlot,
	);
}

function renderWorkflowMediaPreview(id: string) {
	const input = $(`#${id}`);
	const container = $(`#${id}Preview`);
	if (!input || !container) {
		return;
	}
	const filePath = String(input.value || "");
	const preview =
		(filePath && (manifestPreviewForPath(filePath) || state.filePreviews[filePath])) ||
		(filePath
			? {
					path: filePath,
					name: fileNameFromPath(filePath),
					kind: "video",
					extension: filePath.split(".").at(-1) || "",
				}
			: null);
	container.innerHTML = "";
	container.className = "asset-preview workflow-media-preview";
	if (!preview) {
		container.classList.add("empty");
		container.textContent = t("materials.unselected");
		container.title = "";
		return;
	}
	container.title = filePath;
	const thumb = mediaThumbnailElement(preview);
	const detail = document.createElement("span");
	detail.className = "asset-preview-detail";
	const name = document.createElement("strong");
	name.textContent = preview.name || fileNameFromPath(filePath);
	const meta = document.createElement("small");
	meta.textContent = mediaMetaBadges(preview).join(" / ") || previewKindLabel(preview.kind || "video");
	detail.append(name, meta);
	container.append(thumb, detail);
}

function renderWorkflowMediaPreviews() {
	["inputVideoPath"].forEach(renderWorkflowMediaPreview);
}

function loadWorkflowMediaPreviews() {
	const paths = ["inputVideoPath"].map((id) => String($(`#${id}`)?.value || "")).filter(Boolean);
	loadFilePreviews(paths);
	renderWorkflowMediaPreviews();
}

function renderOutputTargetPreview() {
	const input = $("#outputPath");
	const container = $("#outputPathPreview");
	if (!input || !container) {
		return;
	}
	const filePath = String(input.value || "").trim();
	container.innerHTML = "";
	container.className = "asset-preview output-target-preview";
	if (!filePath) {
		container.classList.add("empty");
		container.textContent = t("materials.unselected");
		container.title = "";
		return;
	}
	const preview = state.filePreviews[filePath] || {
		path: filePath,
		name: fileNameFromPath(filePath),
		kind: previewKindFromPath(filePath),
		extension: extensionFromPath(filePath),
	};
	container.title = filePath;
	const thumb = mediaThumbnailElement(preview);
	const detail = document.createElement("span");
	detail.className = "asset-preview-detail";
	const name = document.createElement("strong");
	name.textContent = preview.name || fileNameFromPath(filePath);
	const folder = parentDirectoryFromPath(filePath);
	const metaItems = [
		...mediaMetaBadges(preview),
		preview.sizeBytes ? "" : t("output.pending"),
		folder ? t("output.destination", { folder: shortPath(folder) }) : "",
	].filter(Boolean);
	const meta = document.createElement("small");
	meta.textContent = metaItems.join(" / ") || previewKindLabel(preview.kind || "video");
	detail.append(name, meta);
	container.append(thumb, detail);
}

function loadOutputTargetPreview() {
	const path = String($("#outputPath")?.value || "").trim();
	if (path) {
		loadFilePreviews([path]);
	}
	renderOutputTargetPreview();
}

async function loadFilePreviews(paths: string[]) {
	const missing = [...new Set(paths.filter(Boolean))].filter(
		(filePath) => !state.filePreviews[filePath] && !manifestPreviewForPath(filePath),
	);
	if (!missing.length) {
		return;
	}
	try {
		const previews = await editApp.describeMediaPaths({ paths: missing });
		for (const preview of previews || []) {
			if (preview?.path) {
				state.filePreviews[preview.path] = preview;
			}
		}
		renderFileSlots();
		renderStillImageList();
		renderWorkflowMediaPreviews();
		renderOutputTargetPreview();
	} catch (error) {
		log("media preview failed", { message: error.message });
	}
}

function setFile(slot, filePath) {
	state.files[slot] = filePath || "";
	renderFileSlot(slot);
	if (filePath) {
		loadFilePreviews([filePath]);
	}
	refreshPrompt();
}

function clearSelectedAssets() {
	setFile("masterVideo", "");
	setFile("rightCloseVideo", "");
	setFile("leftCloseVideo", "");
	setFile("referenceVideo", "");
	setFile("externalAudio", "");
	setFile("logo", "");
	setStillImages([]);
}

function setStillImages(paths: string[]) {
	state.files.stillImages = [...new Set(paths.filter(Boolean))];
	const label = $("#stillImagesLabel");
	if (label) {
		label.textContent = state.files.stillImages.length
			? t("label.imageCount", { count: state.files.stillImages.length })
			: t("materials.unselected");
		label.title = state.files.stillImages.join("\n");
	}
	renderStillImageList();
	loadFilePreviews(state.files.stillImages);
	refreshPrompt();
}

function addStillImages(paths: string[]) {
	setStillImages([...state.files.stillImages, ...paths]);
}

function roleSortValue(role: string) {
	if (role === "master") {
		return 1;
	}
	if (role.startsWith("camera")) {
		return Number(role.replace("camera", "")) || 50;
	}
	return 100;
}

function rebuildMediaManifestGroups() {
	if (!state.mediaManifest) {
		return;
	}
	const files = state.mediaManifest.files || [];
	for (const item of files) {
		if (item.kind === "video" && item.role === "reference") {
			item.role = "ignore";
			item.label = t("role.ignore");
			item.reason = "reference video is selected manually outside the material folder";
		}
	}
	const cameraRoles = new Set(["master", "camera2", "camera3", "camera4", "camera5", "camera6"]);
	state.mediaManifest.cameras = files
		.filter((item) => item.kind === "video" && cameraRoles.has(item.role))
		.sort((a, b) => roleSortValue(a.role) - roleSortValue(b.role));
	state.mediaManifest.audio = files.filter((item) => item.kind === "audio" && item.role.startsWith("external"));
	state.mediaManifest.images = files.filter((item) => item.kind === "image" && ["logo", "still"].includes(item.role));
	state.mediaManifest.subtitles = files.filter((item) => item.kind === "subtitle" && item.role === "subtitle");
	state.mediaManifest.other = files.filter(
		(item) =>
			!state.mediaManifest.cameras.includes(item) &&
			!state.mediaManifest.audio.includes(item) &&
			!state.mediaManifest.images.includes(item) &&
			!state.mediaManifest.subtitles.includes(item),
	);
	state.mediaManifest.selected = {
		masterVideo: state.mediaManifest.cameras.find((item) => item.role === "master")?.path || "",
		rightCloseVideo: state.mediaManifest.cameras.find((item) => item.role === "camera2")?.path || "",
		leftCloseVideo: state.mediaManifest.cameras.find((item) => item.role === "camera3")?.path || "",
		externalAudio: state.mediaManifest.audio[0]?.path || "",
		logo: manifestImagesByRole("logo")[0]?.path || "",
		stillImages: manifestImagesByRole("still").map((item) => item.path),
	};
}

function applyManifestSelections() {
	if (!state.mediaManifest) {
		return;
	}
	rebuildMediaManifestGroups();
	const selected = state.mediaManifest.selected || {};
	setFile("masterVideo", selected.masterVideo || "");
	setFile("rightCloseVideo", selected.rightCloseVideo || "");
	setFile("leftCloseVideo", selected.leftCloseVideo || "");
	setFile("externalAudio", selected.externalAudio || "");
	setFile("logo", selected.logo || "");
	setStillImages(Array.isArray(selected.stillImages) ? selected.stillImages.map(String) : []);
}

function roleOptionsFor(item: MediaItem) {
	if (item.kind === "video") {
		return [
			["master", t("role.master")],
			["camera2", t("role.camera2")],
			["camera3", t("role.camera3")],
			["camera4", t("role.camera4")],
			["camera5", t("role.camera5")],
			["ignore", t("role.ignore")],
		];
	}
	if (item.kind === "audio") {
		return [
			["external", t("role.externalAudio")],
			["external2", t("role.externalAudio2")],
			["ignore", t("role.ignore")],
		];
	}
	if (item.kind === "image") {
		return [
			["still", t("role.stillInsert")],
			["logo", t("role.logo")],
			["ignore", t("role.ignore")],
		];
	}
	if (item.kind === "subtitle") {
		return [
			["subtitle", t("role.subtitle")],
			["ignore", t("role.ignore")],
		];
	}
	return [["ignore", t("role.ignore")]];
}

function renderMediaManifest() {
	const directoryLabel = $("#mediaDirectoryLabel");
	if (directoryLabel) {
		directoryLabel.textContent = state.materialPaths.length
			? state.materialPaths.length === 1
				? shortPath(state.materialPaths[0])
				: t("label.selectedItems", { count: state.materialPaths.length })
			: t("label.notSelected");
		directoryLabel.title = state.materialPaths.join("\n");
	}
	const summary = $("#mediaManifestSummary");
	const list = $("#mediaManifestList");
	if (!summary || !list) {
		return;
	}
	if (!state.mediaManifest) {
		summary.textContent = state.materialPaths.length ? t("materials.selectedWaiting") : t("materials.notAnalyzed");
		list.innerHTML = "";
		const empty = document.createElement("div");
		empty.className = "empty-material-state";
		empty.textContent = state.materialPaths.length ? t("materials.manifestHint") : t("materials.noAnalyzedAssets");
		list.appendChild(empty);
		return;
	}
	const cameras = manifestCameras().length;
	const audio = manifestAudioSources().length;
	const stills = manifestImagesByRole("still").length;
	const subtitles = state.mediaManifest.subtitles?.length || 0;
	summary.textContent = t("label.filesSummary", {
		files: state.mediaManifest.files.length,
		cameras,
		audio,
		stills,
		subtitles,
	});
	list.innerHTML = "";
	state.mediaManifest.files.forEach((item) => {
		const row = document.createElement("div");
		row.className = `material-card ${item.kind} ${item.role === "ignore" ? "muted" : ""}`;
		const thumb = mediaThumbnailElement(item);
		const detail = document.createElement("div");
		detail.className = "material-detail";
		const title = document.createElement("span");
		title.textContent = item.relativePath || item.name;
		title.title = item.path;
		const roleText = document.createElement("strong");
		roleText.textContent =
			item.role === "ignore"
				? t("materials.unselected")
				: t("materials.selectedRole", { role: mediaRoleLabel(item.role) });
		const meta = document.createElement("div");
		meta.className = "material-meta";
		for (const badgeText of [
			previewKindLabel(item.kind),
			...mediaMetaBadges(item),
			Number(item.confidence || 0) > 0 ? `${t("label.confidence")} ${Number(item.confidence || 0).toFixed(2)}` : "",
		].filter(Boolean)) {
			const badge = document.createElement("span");
			badge.textContent = badgeText;
			meta.appendChild(badge);
		}
		const reason = document.createElement("small");
		reason.textContent = item.reason ? localizePlainText(item.reason) : "";
		detail.append(title, roleText, meta, reason);
		const role = document.createElement("select");
		role.dataset.mediaRole = item.id;
		for (const [value, label] of roleOptionsFor(item)) {
			const option = document.createElement("option");
			option.value = value;
			option.textContent = label;
			option.selected = item.role === value;
			role.appendChild(option);
		}
		row.append(thumb, detail, role);
		list.appendChild(row);
	});
	$$("[data-media-role]").forEach((select) => {
		select.addEventListener("change", () => {
			const item = manifestFiles().find((candidate) => candidate.id === select.dataset.mediaRole);
			if (!item) {
				return;
			}
			item.role = select.value;
			item.label = select.selectedOptions?.[0]?.textContent || select.value;
			item.reason = t("role.overrideReason");
			item.confidence = 1.0;
			applyManifestSelections();
			renderMediaManifest();
			refreshPrompt();
		});
	});
}

function setMediaManifest(manifest: MediaManifest | null) {
	state.mediaManifest = manifest;
	state.mediaDirectory = manifest?.sourceDirectory || "";
	state.materialPaths = manifest?.sourcePaths?.length
		? manifest.sourcePaths
		: manifest?.sourceDirectory
			? [manifest.sourceDirectory]
			: [];
	applyManifestSelections();
	renderMediaManifest();
	refreshPrompt();
}

function renderStillImageList() {
	const list = $("#stillImagesList");
	if (!list) {
		return;
	}
	list.innerHTML = "";
	if (!state.files.stillImages.length) {
		list.textContent = t("materials.unselected");
		return;
	}
	state.files.stillImages.forEach((path, index) => {
		const row = document.createElement("div");
		row.className = "still-card";
		const preview = manifestPreviewForPath(path) ||
			state.filePreviews[path] || {
				path,
				name: fileNameFromPath(path),
				kind: "image",
				extension: path.split(".").at(-1) || "",
			};
		const thumb = mediaThumbnailElement(preview);
		const detail = document.createElement("div");
		detail.className = "asset-preview-detail";
		const name = document.createElement("strong");
		name.textContent = `${index + 1}. ${preview.name || shortPath(path)}`;
		name.title = path;
		const meta = document.createElement("small");
		meta.textContent = mediaMetaBadges(preview).join(" / ") || previewKindLabel(preview.kind || "image");
		detail.append(name, meta);
		const remove = document.createElement("button");
		remove.type = "button";
		remove.textContent = t("action.remove");
		remove.addEventListener("click", () => {
			setStillImages(state.files.stillImages.filter((_, itemIndex) => itemIndex !== index));
		});
		row.append(thumb, detail, remove);
		list.appendChild(row);
	});
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
		if (element.id === "titleText") {
			return;
		}
		fields[element.id] = element.type === "checkbox" ? element.checked : element.value;
	});
	localStorage.setItem(
		STORAGE_KEY,
		JSON.stringify({
			project: state.project,
			mediaManifest: state.mediaManifest,
			mediaDirectory: state.mediaDirectory,
			materialPaths: state.materialPaths,
			files: state.files,
			subtitleMode: state.subtitleMode,
			analysisResults: state.analysisResults,
			glossaryTerms: state.glossaryTerms,
			language: state.language,
			fields,
		}),
	);
	schedulePersistProjectStateFile();
}

function loadState() {
	const raw = localStorage.getItem(STORAGE_KEY);
	if (!raw) {
		return;
	}
	try {
		const saved = JSON.parse(raw);
		if (saved.language) {
			state.language = normalizeLanguage(saved.language);
			localStorage.setItem(LANGUAGE_STORAGE_KEY, state.language);
		}
		if (saved.project) {
			setProject(saved.project);
		}
		if (saved.mediaManifest) {
			state.mediaManifest = saved.mediaManifest;
			state.mediaDirectory = saved.mediaDirectory || saved.mediaManifest.sourceDirectory || "";
			state.materialPaths =
				saved.materialPaths || saved.mediaManifest.sourcePaths || (state.mediaDirectory ? [state.mediaDirectory] : []);
			applyManifestSelections();
			renderMediaManifest();
		} else if (saved.materialPaths?.length || saved.mediaDirectory) {
			state.mediaDirectory = saved.mediaDirectory;
			state.materialPaths = saved.materialPaths || (saved.mediaDirectory ? [saved.mediaDirectory] : []);
			setIngestProgress({
				progress: 0,
				message: t("progress.pressAnalyze"),
				path: materialSourceLabel(),
			});
			renderMediaManifest();
		}
		if (saved.files) {
			Object.entries(saved.files).forEach(([slot, filePath]) => {
				if (slot === "stillImages" && Array.isArray(filePath)) {
					setStillImages(filePath.map(String));
					return;
				}
				if (slot in state.files) {
					setFile(slot, filePath);
				}
			});
		}
		if (saved.fields) {
			Object.entries(saved.fields).forEach(([id, value]) => {
				if (id === "titleText") {
					return;
				}
				const element = $(`#${id}`);
				if (!element) {
					return;
				}
				if (element.type === "checkbox") {
					element.checked = Boolean(value);
				} else {
					element.value = String(value ?? "");
				}
				if (id === "modelName") {
					state.codexModel = String(value ?? "");
					renderCodexModelOptions();
				}
			});
			loadWorkflowMediaPreviews();
			loadOutputTargetPreview();
		}
		if (saved.subtitleMode) {
			state.subtitleMode = saved.subtitleMode;
			$$("[data-subtitle-mode]").forEach((button) => {
				button.classList.toggle("selected", button.dataset.subtitleMode === state.subtitleMode);
			});
		}
		if (Array.isArray(saved.analysisResults)) {
			setAnalysisResults(saved.analysisResults, { persistFile: false });
		}
		if (Array.isArray(saved.glossaryTerms)) {
			state.glossaryTerms = saved.glossaryTerms;
			renderGlossaryList();
		}
	} catch (error) {
		log("saved state ignored", { message: error.message });
	}
}

const projectStateFieldMap = [
	["render", "editPreset", "editPreset"],
	["render", "workflowAction", "workflowAction"],
	["render", "renderScript", "renderScript"],
	["render", "outputPath", "outputPath"],
	["render", "multicamMode", "multicamMode"],
	["render", "audioSource", "audioSource"],
	["render", "audioDenoise", "audioDenoise"],
	["render", "audioDenoiseStrength", "audioDenoiseStrength"],
	["render", "audioMastering", "audioMastering"],
	["render", "encoderPreset", "encoderPreset"],
	["render", "crf", "renderCrf"],
	["render", "colorMatchCameras", "colorMatchCameras"],
	["render", "usePersonEditPlans", "usePersonEditPlans"],
	["render", "useTranscriptComparisonSync", "useTranscriptComparisonSync"],
	["render", "naturalDialogueCuts", "naturalDialogueCuts"],
	["render", "previewStart", "previewStart"],
	["render", "previewDuration", "previewDuration"],
	["render", "termExplanations", "termExplanations"],
	["render", "shortenSilence", "shortenSilence"],
	["render", "minSilence", "minSilence"],
	["render", "keepSilence", "keepSilence"],
	["render", "silenceNoise", "silenceNoise"],
	["render", "keepUncut", "keepUncut"],
	["music", "enabled", "musicEnabled"],
	["music", "scope", "musicScope"],
	["music", "rangeSource", "musicRangeSource"],
	["music", "prompt", "musicPrompt"],
	["music", "volume", "musicVolume"],
	["music", "rangesText", "musicRangesText"],
	["omissionCard", "enabled", "omissionCardEnabled"],
	["omissionCard", "duration", "omissionCardDuration"],
	["omissionCard", "label", "omissionCardLabel"],
	["omissionCard", "text", "omissionCardText"],
	["omissionCard", "rangesText", "omissionCardRangesText"],
	["thumbnail", "inputVideoPath", "inputVideoPath"],
	["thumbnail", "time", "thumbnailTime"],
	["thumbnail", "title", "thumbnailTitle"],
	["thumbnail", "subtitle", "thumbnailSubtitle"],
	["thumbnail", "candidateCount", "thumbnailCandidateCount"],
	["thumbnail", "mode", "thumbnailMode"],
	["thumbnail", "mainColor", "thumbnailMainColor"],
	["thumbnail", "candidateTimesText", "thumbnailCandidateTimes"],
	["thumbnail", "debugFaces", "thumbnailDebugFaces"],
	["subtitleReview", "maxDuration", "subtitleReviewMaxDuration"],
	["subtitleReview", "maxCharsPerSecond", "subtitleReviewMaxCharsPerSecond"],
	["subtitleReview", "suspiciousPatternsText", "subtitleSuspiciousPatterns"],
	["subtitleReview", "extractAudioClips", "subtitleReviewExtractClips"],
	["subtitleReview", "transcribeReview", "subtitleReviewTranscribeClips"],
	["subtitleReview", "correctionsText", "subtitleCorrectionsText"],
	["subtitleSpeakers", "interviewerRangesText", "subtitleInterviewerRanges"],
	["subtitleSpeakers", "interviewerPatternsText", "subtitleInterviewerPatterns"],
	["subtitleSpeakers", "manualRolesText", "subtitleManualRoles"],
	["subtitleSpeakers", "mouthMotionDiagnostics", "subtitleMouthMotionDiagnostics"],
	["workflow", "inputVideoPath", "inputVideoPath"],
	["workflow", "stillTime", "stillTime"],
	["analysis", "transcribeModel", "transcribeModel"],
	["analysis", "transcribeLanguage", "transcribeLanguage"],
	["analysis", "transcribeBeamSize", "transcribeBeamSize"],
	["analysis", "transcribeTemperature", "transcribeTemperature"],
	["analysis", "transcribePromptTerms", "transcribePromptTerms"],
	["analysis", "transcribeNormalizeAudio", "transcribeNormalizeAudio"],
	["analysis", "transcribeFilterLowConfidence", "transcribeFilterLowConfidence"],
	["analysis", "conditionOnPreviousText", "conditionOnPreviousText"],
	["analysis", "personFpsSample", "personFpsSample"],
	["analysis", "personModel", "personModel"],
	["analysis", "personConfidence", "personConfidence"],
	["analysis", "personMaxSeconds", "personMaxSeconds"],
	["analysis", "personLimit", "personLimit"],
	["analysis", "personNoMulticamRoot", "personNoMulticamRoot"],
	["style", "subtitleSize", "subtitleSize"],
	["style", "highlightColor", "highlightColor"],
	["style", "boxOpacity", "boxOpacity"],
	["style", "titleSize", "titleSize"],
	["style", "logoHeight", "logoHeight"],
	["style", "punchlineText", "punchlineText"],
	["glossary", "enabled", "termExplanations"],
	["tools", "python", "pythonPath"],
	["tools", "ffmpeg", "ffmpegPath"],
	["tools", "ffprobe", "ffprobePath"],
];

function nestedValue(source: any, section: string, key: string) {
	const parent = source?.[section];
	if (!parent || typeof parent !== "object" || !(key in parent)) {
		return undefined;
	}
	return parent[key];
}

function setFormControlValue(id: string, value: any) {
	const element = $(`#${id}`);
	if (!element || value === undefined) {
		return;
	}
	if (element.type === "checkbox") {
		element.checked = Boolean(value);
	} else {
		element.value = value === null ? "" : String(value);
	}
}

function renderSubtitleModeSelection() {
	$$("[data-subtitle-mode]").forEach((button) => {
		button.classList.toggle("selected", button.dataset.subtitleMode === state.subtitleMode);
	});
}

function buildProjectStateSnapshot() {
	return {
		version: 1,
		revision: state.projectStateRevision || 0,
		updatedAt: new Date().toISOString(),
		...buildAppConfig(),
		ui: {
			activeSection: state.activeSection,
			codexModel: state.codexModel,
			language: state.language,
		},
	};
}

let projectStateWriteQueue: Promise<any> = Promise.resolve(null);

function schedulePersistProjectStateFile() {
	if (!state.project || state.projectStateApplying || !state.env) {
		return;
	}
	if (state.projectStatePersistTimer) {
		window.clearTimeout(state.projectStatePersistTimer);
	}
	state.projectStatePersistTimer = window.setTimeout(() => {
		state.projectStatePersistTimer = 0;
		void persistProjectStateFileNow();
	}, 250);
}

async function persistProjectStateFileNow() {
	if (!state.project || state.projectStateApplying || !state.env) {
		return null;
	}
	if (state.projectStatePersistTimer) {
		window.clearTimeout(state.projectStatePersistTimer);
		state.projectStatePersistTimer = 0;
	}
	const project = { ...state.project };
	const snapshot = buildProjectStateSnapshot();
	projectStateWriteQueue = projectStateWriteQueue
		.catch(() => undefined)
		.then(async () => {
			const saved = await editApp.saveProjectState({ project, state: snapshot });
			if (state.project?.id === project.id) {
				state.projectStateRevision = Number(saved?.revision || state.projectStateRevision || 0);
				state.projectStatePath = saved?.path || state.projectStatePath;
			}
			return saved;
		})
		.catch((error) => {
			log("project state save failed", { message: error.message });
			return null;
		});
	return projectStateWriteQueue;
}

function applyProjectStatePayload(payload: any) {
	if (!payload || typeof payload !== "object") {
		return false;
	}
	state.projectStateApplying = true;
	try {
		state.projectStatePath = String(payload.path || state.projectStatePath || "");
		state.projectStateRevision = Number(payload.revision || state.projectStateRevision || 0);
		const assets = payload.assets || {};
		if (Array.isArray(assets.materialPaths)) {
			state.materialPaths = assets.materialPaths.map(String).filter(Boolean);
		}
		state.mediaDirectory = String(assets.mediaDirectory || state.materialPaths[0] || "");
		if (assets.mediaManifest && typeof assets.mediaManifest === "object") {
			state.mediaManifest = assets.mediaManifest;
			if (state.mediaManifest) {
				rebuildMediaManifestGroups();
			}
		}
		const selected = state.mediaManifest?.selected || {};
		state.files.masterVideo = String(assets.masterVideo || selected.masterVideo || "");
		state.files.rightCloseVideo = String(assets.rightCloseVideo || selected.rightCloseVideo || "");
		state.files.leftCloseVideo = String(assets.leftCloseVideo || selected.leftCloseVideo || "");
		state.files.referenceVideo = String(assets.referenceVideo || "");
		state.files.externalAudio = String(assets.externalAudio || selected.externalAudio || "");
		state.files.logo = String(assets.logo || selected.logo || "");
		state.files.stillImages = Array.isArray(assets.stillImages)
			? [...new Set<string>(assets.stillImages.map(String).filter((item) => Boolean(item)))]
			: Array.isArray(selected.stillImages)
				? selected.stillImages.map(String).filter(Boolean)
				: [];

		for (const [section, key, id] of projectStateFieldMap) {
			setFormControlValue(id, nestedValue(payload, section, key));
		}
		if (payload.render?.subtitleMode) {
			state.subtitleMode = String(payload.render.subtitleMode);
			renderSubtitleModeSelection();
		}
		if (payload.style && "titleText" in payload.style) {
			setAnalysisTitleText(String(payload.style.titleText || ""));
		}
		if (Array.isArray(payload.glossary?.terms)) {
			state.glossaryTerms = payload.glossary.terms;
		}
		if (payload.ui?.activeSection) {
			setActiveSection(String(payload.ui.activeSection));
		}
		if (payload.ui?.codexModel !== undefined) {
			state.codexModel = String(payload.ui.codexModel || "");
			renderCodexModelOptions();
		}
		if (payload.ui?.language) {
			setLanguage(normalizeLanguage(payload.ui.language));
		}

		renderFileSlots();
		renderStillImageList();
		renderMediaManifest();
		renderGlossaryList();
		loadFilePreviews([
			state.files.masterVideo,
			state.files.rightCloseVideo,
			state.files.leftCloseVideo,
			state.files.referenceVideo,
			state.files.externalAudio,
			state.files.logo,
			...state.files.stillImages,
		]);
		loadWorkflowMediaPreviews();
		loadOutputTargetPreview();
		updateRunSummary();
		refreshCommand();
		refreshPrompt();
		return true;
	} finally {
		state.projectStateApplying = false;
	}
}

async function loadProjectStateFile(project: ProjectInfo | null = state.project) {
	if (!project) {
		return false;
	}
	try {
		const payload = await editApp.loadProjectState({ project });
		if (!payload) {
			return false;
		}
		const applied = applyProjectStatePayload(payload);
		if (applied) {
			log("project state loaded", {
				path: payload.path || "",
				revision: payload.revision || 0,
			});
		}
		return applied;
	} catch (error) {
		log("project state load failed", { message: error.message });
		return false;
	}
}

let analysisStateWriteQueue: Promise<void> = Promise.resolve();

function analysisStateSnapshot() {
	return {
		version: 1,
		updatedAt: new Date().toISOString(),
		mediaManifestPath: mediaManifestPath(),
		mediaManifestGeneratedAt: state.mediaManifest?.generatedAt || "",
		mediaManifestFileCount: state.mediaManifest?.files?.length || 0,
		results: state.analysisResults.map((item) => ({ ...item })),
	};
}

function persistAnalysisStateFile() {
	if (!state.project) {
		return;
	}
	const project = { ...state.project };
	const snapshot = analysisStateSnapshot();
	analysisStateWriteQueue = analysisStateWriteQueue
		.catch(() => undefined)
		.then(async () => {
			await editApp.saveAnalysisState({ project, state: snapshot });
		})
		.catch((error) => {
			log("analysis state save failed", { message: error.message });
		});
}

async function loadAnalysisStateFile(project: ProjectInfo | null = state.project) {
	if (!project) {
		return false;
	}
	try {
		const payload = await editApp.loadAnalysisState({ project });
		if (!Array.isArray(payload?.results)) {
			return false;
		}
		setAnalysisResults(payload.results, { persistFile: false });
		log("analysis state loaded", {
			path: payload.path || "",
			results: state.analysisResults.length,
		});
		return state.analysisResults.length > 0;
	} catch (error) {
		log("analysis state load failed", { message: error.message });
		return false;
	}
}

async function pickFile(slot) {
	if (slot === "stillImages") {
		const selected = await editApp.pickFile({
			title: t("dialog.selectStillImages"),
			filters: filtersForSlot("stillImages"),
			multi: true,
		});
		if (Array.isArray(selected)) {
			addStillImages(selected);
		} else if (selected) {
			addStillImages([selected]);
		}
		return;
	}
	const selected = await editApp.pickFile({
		title: t("dialog.selectSlot", { slot: fileSlotLabel(slot) }),
		filters: filtersForSlot(slot),
	});
	if (selected) {
		setFile(slot, selected);
	}
}

async function pickTool(id) {
	const selected = await editApp.pickFile({
		title: t("dialog.selectTool", { id }),
		filters: [{ name: t("filter.allFiles"), extensions: ["*"] }],
	});
	if (selected) {
		$(`#${id}`).value = selected;
		if (id === "inputVideoPath") {
			loadWorkflowMediaPreviews();
		}
		refreshPrompt();
	}
}

async function pickDirectory(id) {
	const selected = await editApp.pickDirectory({ title: t("dialog.selectTool", { id }) });
	if (selected) {
		$(`#${id}`).value = selected;
		refreshPrompt();
	}
}

async function pickOutput() {
	const mode = state.subtitleMode === "punchline" ? "punchline" : "full_transcript";
	const selected = await editApp.pickOutput({
		title: t("dialog.selectOutputVideo"),
		suggestedName: `codex_edit_${mode}.mp4`,
		outputRoot: activeOutputRoot(),
		filterName: t("filter.mp4Video"),
		language: state.language,
	});
	if (selected) {
		$("#outputPath").value = selected;
		loadOutputTargetPreview();
		refreshPrompt();
	}
}

async function pickMaterialDirectory() {
	const selected = await editApp.pickDirectory({ title: t("dialog.selectMaterialFolder") });
	if (selected) {
		setMaterialDirectory(selected);
	}
}

async function pickMaterialFiles() {
	const selected = await editApp.pickFile({
		title: t("dialog.selectMaterialFiles"),
		filters: [
			{
				name: t("filter.mediaAndSubtitles"),
				extensions: [
					"mp4",
					"mov",
					"m4v",
					"mkv",
					"avi",
					"mts",
					"m2ts",
					"wav",
					"mp3",
					"aac",
					"m4a",
					"flac",
					"aiff",
					"aif",
					"png",
					"jpg",
					"jpeg",
					"webp",
					"srt",
					"ass",
					"vtt",
				],
			},
			{ name: t("filter.allFiles"), extensions: ["*"] },
		],
		multi: true,
	});
	if (Array.isArray(selected)) {
		addMaterialSources(selected);
	} else if (selected) {
		addMaterialSources([selected]);
	}
}

async function createProjectFromForm() {
	const name = formValue("projectName") || `project-${new Date().toISOString().slice(0, 10)}`;
	const id = formValue("projectId") || projectIdFromName(name);
	try {
		const project = await editApp.createProject({ name, id });
		setProject(project);
		await persistProjectStateFileNow();
		void loadProjectList();
		log("project ready", { id: project.id, root: project.root });
	} catch (error) {
		log("project create failed", { message: error.message });
	}
}

async function changeProject() {
	setProjectDialogOpen(true);
}

async function createProjectFromDialog() {
	if (state.ingestRunning) {
		log("project create skipped", { reason: t("log.cannotSwitchDuringIngest") });
		return;
	}
	const input = $("#projectDialogName");
	const formName = String(input?.value || "").trim();
	const name = formName || formValue("projectName") || `project-${new Date().toISOString().slice(0, 10)}`;
	const id = projectIdFromName(name);
	try {
		const project = await editApp.createProject({ name, id });
		setProjectDialogOpen(false);
		await activateProject(project, null);
		log("project ready", { id: project.id, root: project.root });
		void loadProjectList();
	} catch (error) {
		log("project create failed", { message: error.message });
	}
}

async function deleteCurrentProject() {
	if (!state.project) {
		log("project delete skipped", { reason: t("log.projectNotSelected") });
		return;
	}
	if (state.ingestRunning) {
		log("project delete skipped", { reason: t("log.cannotDeleteDuringIngest") });
		return;
	}
	const deletedProject = state.project;
	try {
		const result = await editApp.deleteProject({ project: deletedProject, language: state.language });
		if (!result?.deleted) {
			log(result?.canceled ? "project delete canceled" : "project delete skipped", {
				id: deletedProject.id,
				missing: Boolean(result?.missing),
			});
			return;
		}
		setProject(null);
		clearSelectedAssets();
		setMediaManifest(null);
		setAnalysisResults([]);
		setIngestProgress({
			progress: 0,
			message: t("progress.waitingAnalysis"),
			path: "",
		});
		$("#outputPath").value = "";
		$("#inputVideoPath").value = "";
		loadWorkflowMediaPreviews();
		loadOutputTargetPreview();
		log("project deleted", { id: deletedProject.id, root: deletedProject.root });
		await refreshSyncReport();
		refreshPrompt();
	} catch (error) {
		log("project delete failed", { message: error.message });
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
			if (slot === "stillImages" && Array.isArray(filePath)) {
				setStillImages(filePath.map(String));
				return;
			}
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

async function runAnalysisAction(
	action: string,
	label: string,
	progress: number,
	resultPath: string,
	timeoutMs = 6 * 60 * 60 * 1000,
) {
	setAppLocked(true, label);
	setStatus(label, "busy");
	setAnalysisResult(action, label, "running", t("analysis.statusRunning"), resultPath);
	setIngestProgress({
		progress,
		message: t("format.runningMessage", { label }),
		path: resultPath,
	});
	const command = buildActionCommand(action);
	log("analysis/exec", { action, command });
	try {
		const result = await editApp.runWorkflowAction({
			action,
			timeoutMs,
			appConfig: buildAppConfig(),
		});
		if (result?.stdout) {
			log("stdout", { action, text: compactOutput(result.stdout) });
		}
		if (result?.stderr) {
			log("stderr", { action, text: compactOutput(result.stderr) });
		}
		const ok = result?.exitCode === 0;
		setAnalysisResult(
			action,
			label,
			ok ? "done" : "error",
			ok ? t("analysis.updatedOutput") : t("analysis.checkLogs"),
			resultPath,
		);
		setIngestProgress({
			progress,
			message: ok ? t("format.completeMessage", { label }) : t("format.errorMessage", { label }),
			path: resultPath,
		});
		return ok;
	} catch (error) {
		setAnalysisResult(action, label, "error", error.message, resultPath);
		setIngestProgress({
			progress,
			message: t("format.errorMessage", { label }),
			path: resultPath,
		});
		log("analysis failed", { action, message: error.message });
		return false;
	}
}

async function ingestMaterialDirectory(directoryPath = "") {
	const selectedSources = directoryPath
		? [directoryPath]
		: state.materialPaths.length
			? state.materialPaths
			: state.mediaDirectory
				? [state.mediaDirectory]
				: [];
	const sourceLabel =
		selectedSources.length === 1 ? selectedSources[0] : t("label.selectedItems", { count: selectedSources.length });
	if (!selectedSources.length) {
		log("ingest skipped", { reason: t("log.selectMaterialFirst") });
		return false;
	}
	if (!state.project) {
		const nameInput = $("#projectName");
		if (nameInput && !nameInput.value) {
			const parts = selectedSources[0].split(/[\\/]/).filter(Boolean);
			nameInput.value =
				selectedSources.length === 1
					? parts.at(-1) || `project-${new Date().toISOString().slice(0, 10)}`
					: `materials-${new Date().toISOString().slice(0, 10)}`;
			$("#projectId").value = projectIdFromName(nameInput.value);
		}
		await createProjectFromForm();
	}
	if (!state.project) {
		return false;
	}
	state.fullAnalysisRunning = true;
	state.analysisResults = [];
	renderAnalysisResults();
	setStatus(t("status.analyzingMaterial"), "busy");
	setIngestRunning(true);
	setAppLocked(true, t("progress.analyzingMaterial"));
	setIngestProgress({
		progress: 0,
		message: t("progress.startingAnalysis"),
		path: sourceLabel,
	});
	log("ingest material", { paths: selectedSources });
	try {
		const result = await editApp.ingestDirectory({
			project: state.project,
			directory: selectedSources.length === 1 ? selectedSources[0] : "",
			paths: selectedSources,
			tools: {
				ffprobe: ffprobeExe(),
			},
		});
		setProject(result.project);
		setMediaManifest(result.manifest);
		$("#editPreset").value = "new-interview";
		$("#renderScript").value = "render_app_interview.py";
		$("#workflowAction").value = "auto-sync-dropped";
		setDefaultProjectOutput(false);
		setAnalysisResult(
			"ingest",
			t("analysis.materialClassification"),
			"done",
			`${result.manifest?.files?.length || 0} files / ${result.manifest?.cameras?.length || 0} camera(s)`,
			result.manifest?.manifestPath || sourceLabel,
		);
		setIngestProgress({
			progress: 0.22,
			message: t("progress.materialClassified"),
			path: result.manifest?.manifestPath || sourceLabel,
		});
		log("material manifest ready", {
			manifest: result.manifest?.manifestPath,
			files: result.manifest?.files?.length || 0,
			cameras: result.manifest?.cameras?.length || 0,
			audio: result.manifest?.audio?.length || 0,
		});
		refreshPrompt();
		const checks: boolean[] = [];
		if (hasSyncTargets(result.manifest)) {
			checks.push(
				await runAnalysisAction(
					"auto-sync-dropped",
					t("analysis.syncCamerasAudio"),
					0.34,
					syncReportPath(),
					2 * 60 * 60 * 1000,
				),
			);
			await refreshSyncReport();
		} else {
			setAnalysisResult(
				"auto-sync-dropped",
				t("analysis.syncCamerasAudio"),
				"done",
				t("analysis.singleCameraSkipped"),
				syncReportPath(),
			);
		}
		checks.push(
			await runAnalysisAction("transcribe-dropped", t("analysis.transcription"), 0.58, transcriptManifestOutputPath()),
		);
		const textOverlayResult = await refreshTextOverlayFromAnalysis(result.manifest);
		setAnalysisResult(
			"text-overlays",
			t("analysis.subtitleUi"),
			textOverlayResult?.captionCount ? "done" : "error",
			textOverlayResult?.captionCount
				? `${textOverlayResult.captionCount} captions`
				: t("analysis.noSubtitleCandidates"),
			textOverlayResult?.subtitlePath || "",
		);
		checks.push(
			await runAnalysisAction(
				"compare-transcripts",
				t("analysis.transcriptComparison"),
				0.68,
				transcriptComparisonOutputPath(),
			),
		);
		checks.push(
			await runAnalysisAction("analyze-person-edit-metadata", t("analysis.personOpenCv"), 0.8, personEditPlansDir()),
		);
		checks.push(
			await runAnalysisAction("analyze-blocking", t("analysis.blockingOpenCv"), 0.9, blockingMetricsOutputPath()),
		);
		if (state.files.referenceVideo) {
			checks.push(
				await runAnalysisAction(
					"analyze-reference-video",
					t("analysis.referenceVideo"),
					0.95,
					referenceEditProfilePath(),
				),
			);
		}
		await refreshTextOverlayFromAnalysis(result.manifest);
		await refreshSyncReport();
		$("#editPreset").value = "new-interview";
		$("#renderScript").value = "render_app_interview.py";
		$("#workflowAction").value = "render-selected";
		refreshPrompt();
		const allOk = checks.every(Boolean);
		setIngestProgress({
			progress: 1,
			message: allOk ? t("progress.allAnalysisComplete") : t("progress.analysisCompleteWithErrors"),
			path: result.manifest?.manifestPath || sourceLabel,
		});
		setStatus(allOk ? t("status.analysisComplete") : t("status.analysisCompletedWithErrors"), allOk ? "ready" : "idle");
		state.fullAnalysisRunning = false;
		await notifyAnalysisComplete(allOk ? t("notification.analysisComplete") : t("notification.analysisCompleteCheck"));
		return allOk;
	} catch (error) {
		setStatus(t("status.ingestFailed"), "idle");
		setIngestProgress({
			progress: 0,
			message: String(error.message || "").includes("キャンセル")
				? t("progress.analysisCanceled")
				: t("progress.analysisFailed"),
			path: sourceLabel,
		});
		log("ingest failed", { message: error.message });
		return false;
	} finally {
		state.fullAnalysisRunning = false;
		setIngestRunning(false);
		setAppLocked(false);
	}
}

async function cancelMaterialAnalysis() {
	if (!state.ingestRunning) {
		return;
	}
	try {
		await editApp.cancelIngest();
	} catch (error) {
		log("ingest cancel failed", { message: error.message });
	}
}

async function prepareProjectForRun() {
	if (!state.project && !formValue("projectName") && !formValue("projectId")) {
		log("project required before run");
		setStatus(t("status.projectRequired"), "idle");
		return false;
	}
	if (!state.project) {
		await createProjectFromForm();
	}
	if (state.mediaManifest) {
		return true;
	}
	if (state.project) {
		return copyAssetsToProject();
	}
	return false;
}

function formValue(id) {
	const element = $(`#${id}`);
	if (!element) {
		return "";
	}
	if (element.type === "checkbox") {
		return element.checked;
	}
	return element.value;
}

function selectedLabel(id) {
	const element = $(`#${id}`);
	return element?.selectedOptions?.[0]?.textContent?.trim() || formValue(id);
}

function subtitleModeLabel() {
	if (state.subtitleMode === "punchline") {
		return t("style.catchy");
	}
	if (state.subtitleMode === "none") {
		return t("style.none");
	}
	return t("style.full");
}

function analysisLabel(key: string, fallback = "") {
	const labels = {
		ingest: "analysis.materialClassification",
		"auto-sync-dropped": "analysis.syncCamerasAudio",
		"transcribe-dropped": "analysis.transcription",
		"compare-transcripts": "analysis.transcriptComparison",
		"text-overlays": "analysis.subtitleUi",
		"analyze-person-edit-metadata": "analysis.personOpenCv",
		"analyze-blocking": "analysis.blockingOpenCv",
		"analyze-reference-video": "analysis.referenceVideo",
	};
	return labels[key] ? t(labels[key]) : localizePlainText(fallback || key);
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
		container.textContent = t("sync.noReport");
		return;
	}
	container.innerHTML = "";
	rows.forEach((row) => {
		const element = document.createElement("div");
		element.className = `sync-row ${scoreKind(row.score)}`;
		const role = document.createElement("strong");
		role.textContent = row.role;
		const detail = document.createElement("span");
		detail.textContent = `${
			Number.isFinite(row.offset) ? `${row.offset.toFixed(3)}s` : t("label.offsetUnknown")
		} · ${shortPath(row.path)}`;
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
		let candidates = termsFromGlossaryManifest(manifest);
		if (!candidates.length) {
			const overlayCandidates = await editApp.loadTextOverlayCandidates({
				manifest: state.mediaManifest,
				appConfig: buildAppConfig(),
			});
			candidates = overlayCandidates?.glossaryTerms || [];
		}
		setGlossaryTerms(candidates);
		log("glossary candidates loaded", { count: candidates.length });
	} catch (error) {
		try {
			const overlayCandidates = await editApp.loadTextOverlayCandidates({
				manifest: state.mediaManifest,
				appConfig: buildAppConfig(),
			});
			const candidates = overlayCandidates?.glossaryTerms || [];
			setGlossaryTerms(candidates);
			log("glossary candidates loaded from subtitles", { count: candidates.length });
		} catch (fallbackError) {
			log("glossary load failed", { message: fallbackError.message || error.message });
		}
	}
}

async function refreshTextOverlayFromAnalysis(manifest: MediaManifest | null) {
	try {
		const result = await editApp.loadTextOverlayCandidates({
			manifest,
			appConfig: buildAppConfig(),
		});
		setAnalysisTitleText(result?.titleText || "");
		const punchlineInput = $("#punchlineText");
		if (punchlineInput) {
			punchlineInput.value = result?.punchlineText || "";
		}
		setGlossaryTerms(Array.isArray(result?.glossaryTerms) ? result.glossaryTerms : []);
		log("text overlays refreshed", {
			subtitle: result?.subtitlePath || null,
			captions: result?.captionCount || 0,
			title: result?.titleText || "",
			glossary: result?.glossaryTerms?.length || 0,
		});
		refreshPrompt();
		return result;
	} catch (error) {
		log("text overlay refresh failed", { message: error.message });
		return null;
	}
}

async function refreshAnalysisTitleFromAnalysis(manifest: MediaManifest | null) {
	try {
		const result = await editApp.loadTextOverlayCandidates({
			manifest,
			appConfig: buildAppConfig(),
		});
		setAnalysisTitleText(result?.titleText || "");
		log("analysis title refreshed", {
			subtitle: result?.subtitlePath || null,
			captions: result?.captionCount || 0,
			title: result?.titleText || "",
		});
		refreshPrompt();
	} catch (error) {
		setAnalysisTitleText("");
		log("analysis title refresh failed", { message: error.message });
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
		log("glossary add skipped", { reason: t("log.glossaryRequired") });
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

function ffmpegExe() {
	return formValue("ffmpegPath") || state.env?.ffmpegExe || DEFAULT_FFMPEG_EXE;
}

function ffprobeExe() {
	return formValue("ffprobePath") || state.env?.ffprobeExe || DEFAULT_FFPROBE_EXE;
}

function stillOutputPath(inputVideo, outputPath) {
	if (outputPath && /\.(png|jpg|jpeg)$/i.test(outputPath)) {
		return outputPath;
	}
	const source = inputVideo || outputPath || "preview";
	return `${source.replace(/\.[^.\\/]+$/, "")}_still.png`;
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

function musicBedPath() {
	return activeOutputRoot() ? joinPath(activeOutputRoot(), "audio", "music_bed.wav") : "";
}

function omissionCardOutputPath() {
	return activeOutputRoot() ? joinPath(activeOutputRoot(), "overlays", "omission_card.png") : "";
}

function thumbnailOutputPath() {
	return activeOutputRoot() ? joinPath(activeOutputRoot(), "images", "thumbnail.png") : "";
}

function thumbnailCandidatesOutputPath() {
	return activeOutputRoot() ? joinPath(activeOutputRoot(), "images", "thumbnail_candidates") : "";
}

function subtitleReviewOutputPath() {
	return activeOutputRoot() ? joinPath(activeOutputRoot(), "reports", "subtitle_review.json") : "";
}

function subtitleReviewClipsPath() {
	return activeOutputRoot() ? joinPath(activeOutputRoot(), "diagnostics", "subtitle_review", "clips") : "";
}

function subtitleCorrectionsOutputPath() {
	return activeOutputRoot() ? joinPath(activeOutputRoot(), "reports", "subtitle_corrections_applied.json") : "";
}

function subtitleSpeakerRolesOutputPath() {
	return activeOutputRoot() ? joinPath(activeOutputRoot(), "reports", "full_transcript_speaker_roles.json") : "";
}

function transcriptComparisonOutputPath() {
	return activeOutputRoot() ? joinPath(activeOutputRoot(), "reports", "transcript_comparison.json") : "";
}

function transcriptManifestOutputPath() {
	return activeOutputRoot()
		? joinPath(activeOutputRoot(), "transcripts", "manifest_sources", "manifest_transcripts.json")
		: "";
}

function blockingMetricsOutputPath() {
	return activeOutputRoot()
		? joinPath(activeOutputRoot(), "diagnostics", "opencv_blocking_analysis", "clip_metrics.json")
		: "";
}

function analysisOutputCandidates(manifest: MediaManifest | null = state.mediaManifest) {
	const candidates: Array<AnalysisResult & { requirePath?: boolean }> = [];
	if (!activeOutputRoot()) {
		return candidates;
	}
	const manifestPath = mediaManifestPath();
	if (manifestPath) {
		candidates.push({
			key: "ingest",
			label: t("analysis.materialClassification"),
			status: "done",
			detail: manifest?.files
				? `${manifest.files.length || 0} files / ${manifest.cameras?.length || 0} camera(s)`
				: t("analysis.updatedOutput"),
			path: manifestPath,
			requirePath: true,
		});
	}
	if (manifest && !hasSyncTargets(manifest)) {
		candidates.push({
			key: "auto-sync-dropped",
			label: t("analysis.syncCamerasAudio"),
			status: "done",
			detail: t("analysis.singleCameraSkipped"),
			path: syncReportPath(),
			requirePath: false,
		});
	} else if (syncReportPath()) {
		candidates.push({
			key: "auto-sync-dropped",
			label: t("analysis.syncCamerasAudio"),
			status: "done",
			detail: t("analysis.updatedOutput"),
			path: syncReportPath(),
			requirePath: true,
		});
	}
	const transcriptPath = transcriptManifestOutputPath();
	if (transcriptPath) {
		candidates.push(
			{
				key: "transcribe-dropped",
				label: t("analysis.transcription"),
				status: "done",
				detail: t("analysis.updatedOutput"),
				path: transcriptPath,
				requirePath: true,
			},
			{
				key: "text-overlays",
				label: t("analysis.subtitleUi"),
				status: "done",
				detail: t("analysis.updatedOutput"),
				path: transcriptPath,
				requirePath: true,
			},
		);
	}
	for (const item of [
		["compare-transcripts", t("analysis.transcriptComparison"), transcriptComparisonOutputPath()],
		["analyze-person-edit-metadata", t("analysis.personOpenCv"), personEditPlansDir()],
		["analyze-blocking", t("analysis.blockingOpenCv"), blockingMetricsOutputPath()],
	] as const) {
		if (item[2]) {
			candidates.push({
				key: item[0],
				label: item[1],
				status: "done",
				detail: t("analysis.updatedOutput"),
				path: item[2],
				requirePath: true,
			});
		}
	}
	if (state.files.referenceVideo && referenceEditProfilePath()) {
		candidates.push({
			key: "analyze-reference-video",
			label: t("analysis.referenceVideo"),
			status: "done",
			detail: t("analysis.updatedOutput"),
			path: referenceEditProfilePath(),
			requirePath: true,
		});
	}
	return candidates;
}

async function restoreAnalysisResultsFromOutputs(
	manifest: MediaManifest | null = state.mediaManifest,
	options: { preserveExisting?: boolean } = {},
) {
	if (options.preserveExisting && state.analysisResults.length) {
		renderAnalysisResults();
		return;
	}
	const candidates = analysisOutputCandidates(manifest);
	if (!candidates.length) {
		setAnalysisResults([]);
		return;
	}
	const paths = [
		...new Set(
			candidates
				.filter((item) => item.requirePath !== false)
				.map((item) => item.path)
				.filter(Boolean),
		),
	];
	let existing = new Set<string>();
	if (paths.length) {
		try {
			const entries = await editApp.describeMediaPaths({ paths });
			existing = new Set((entries || []).map((entry) => String(entry.path || "").toLowerCase()));
		} catch (error) {
			log("analysis restore failed", { message: error.message });
		}
	}
	setAnalysisResults(
		candidates.filter(
			(item) => item.requirePath === false || (item.path && existing.has(String(item.path).toLowerCase())),
		),
	);
}

function hasMusicRanges() {
	return Boolean(String(formValue("musicRangesText") || "").trim());
}

function hasOmissionCardRanges() {
	return Boolean(
		String(formValue("omissionCardRangesText") || "").trim() || String(formValue("musicRangesText") || "").trim(),
	);
}

function hasSubtitleCorrections() {
	return Boolean(String(formValue("subtitleCorrectionsText") || "").trim());
}

function hasSubtitleSpeakerRules() {
	return Boolean(
		String(formValue("subtitleInterviewerRanges") || "").trim() ||
			String(formValue("subtitleInterviewerPatterns") || "").trim() ||
			String(formValue("subtitleManualRoles") || "").trim(),
	);
}

function thumbnailInputPath() {
	return (
		formValue("inputVideoPath") ||
		selectedMasterVideoPath() ||
		manifestCameras()[0]?.path ||
		$("#outputPath")?.value?.trim() ||
		""
	);
}

function thumbnailCandidateImageCount() {
	const paths = new Set<string>();
	(state.mediaManifest?.images || []).forEach((item) => {
		if (item.role !== "logo") {
			paths.add(item.path);
		}
	});
	state.files.stillImages.forEach((path) => {
		paths.add(path);
	});
	return paths.size;
}

function hasThumbnailCandidateSource() {
	return Boolean(thumbnailInputPath() || thumbnailCandidateImageCount());
}

function selectedAnalysisVideos() {
	const manifestVideos = manifestCameras()
		.map((item) => item.path)
		.filter(Boolean);
	return manifestVideos.length
		? manifestVideos
		: [state.files.masterVideo, state.files.rightCloseVideo, state.files.leftCloseVideo].filter(Boolean);
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

function buildActionCommand(action: string) {
	return withRuntimeConfig([pythonExe(), scriptPath("video_edit_run.py"), "--action", action]);
}

function hasSyncTargets(manifest: MediaManifest | null) {
	const cameraCount = (manifest?.cameras || []).filter((item) => item.role !== "master").length;
	const audioCount = manifest?.audio?.length || 0;
	return (
		cameraCount + audioCount > 0 ||
		Boolean(state.files.rightCloseVideo || state.files.leftCloseVideo || state.files.externalAudio)
	);
}

function compactOutput(value: string) {
	const text = String(value || "");
	return text.length > 4000 ? `${text.slice(0, 1200)}\n...\n${text.slice(-2400)}` : text;
}

function directRunLabel(action: string) {
	if (action === "render-selected") {
		return t("runLabel.render");
	}
	if (action === "auto-sync-dropped") {
		return t("runLabel.sync");
	}
	if (action.startsWith("transcribe")) {
		return t("runLabel.transcribe");
	}
	if (action === "generate-music-bed") {
		return t("option.generateMusicBed");
	}
	if (action === "replace-audio") {
		return t("option.replaceAudio");
	}
	if (action === "generate-thumbnail") {
		return t("option.generateThumbnail");
	}
	if (action === "generate-thumbnail-candidates") {
		return t("option.generateThumbnailCandidates");
	}
	if (action === "review-subtitles") {
		return t("option.reviewSubtitles");
	}
	if (action === "apply-subtitle-corrections") {
		return t("option.applySubtitleCorrections");
	}
	if (action === "classify-subtitle-speakers") {
		return t("option.classifySubtitleSpeakers");
	}
	if (action === "compare-transcripts") {
		return t("option.compareTranscripts");
	}
	if (action.startsWith("analyze-")) {
		return t("runLabel.analyze");
	}
	return selectedLabel("workflowAction") || t("runLabel.run");
}

function directRunOutputPath(action: string) {
	if (action === "analyze-person-edit-metadata") {
		return personEditPlansDir();
	}
	if (action === "analyze-reference-video") {
		return referenceEditProfilePath();
	}
	if (action === "auto-sync-dropped") {
		return syncReportPath();
	}
	if (action === "transcribe-dropped") {
		return joinPath(activeOutputRoot() || "output", "transcripts", "manifest_sources");
	}
	if (action === "generate-music-bed") {
		return musicBedPath();
	}
	if (action === "replace-audio") {
		return $("#outputPath")?.value?.trim() || activeOutputRoot();
	}
	if (action === "generate-thumbnail") {
		return thumbnailOutputPath();
	}
	if (action === "generate-thumbnail-candidates") {
		return thumbnailCandidatesOutputPath();
	}
	if (action === "review-subtitles") {
		return subtitleReviewOutputPath();
	}
	if (action === "apply-subtitle-corrections") {
		return subtitleCorrectionsOutputPath();
	}
	if (action === "classify-subtitle-speakers") {
		return subtitleSpeakerRolesOutputPath();
	}
	if (action === "compare-transcripts") {
		return transcriptComparisonOutputPath();
	}
	return $("#outputPath")?.value?.trim() || activeOutputRoot();
}

function handleWorkflowProgress(payload: any) {
	if (!state.directRunRunning || payload?.action !== state.runningAction) {
		return;
	}
	const path = directRunOutputPath(state.runningAction);
	setIngestProgress({
		progress: Number(payload.progress) || 0,
		message: payload.message || t("format.runningMessage", { label: directRunLabel(state.runningAction) }),
		path,
	});
	const progress = Number(payload.progress) || 0;
	if (payload.stage !== state.lastWorkflowStage || progress - state.lastWorkflowProgressLog >= 0.05 || progress >= 1) {
		state.lastWorkflowStage = payload.stage || "";
		state.lastWorkflowProgressLog = progress;
		log("workflow progress", {
			action: payload.action,
			stage: payload.stage,
			progress: progressPercent(progress),
			message: payload.message,
		});
	}
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
	const cameras = manifestCameras();
	const audioSources = manifestAudioSources();
	const masterVideo = selectedMasterVideoPath();

	if (!state.project && !formValue("projectName") && !formValue("projectId")) {
		errors.push(t("validation.projectRequired"));
	}

	if (action === "render-selected") {
		if (!outputPath) {
			errors.push(t("validation.outputRequired"));
		} else {
			ok.push(t("validation.output", { path: shortPath(outputPath) }));
		}
		if (script === "render_app_interview.py") {
			if (!masterVideo) {
				errors.push(t("validation.masterRequiredForInterview"));
			}
			if (cameras.length <= 1 && !state.files.rightCloseVideo && !state.files.leftCloseVideo) {
				warnings.push(t("validation.singleCameraWarning"));
			}
			if (cameras.length > 1 || state.files.rightCloseVideo || state.files.leftCloseVideo) {
				warnings.push(t("validation.syncFirstWarning"));
			}
		}
		if (formValue("shortenSilence")) {
			warnings.push(t("validation.shortenSilenceWarning"));
		}
	}

	if (action === "auto-sync-dropped") {
		if (!masterVideo) {
			errors.push(t("validation.masterRequiredForSync"));
		}
		if (
			cameras.length <= 1 &&
			!state.files.rightCloseVideo &&
			!state.files.leftCloseVideo &&
			!state.files.externalAudio &&
			!audioSources.length
		) {
			errors.push(t("validation.syncTargetsRequired"));
		}
		ok.push(t("validation.syncSaved"));
	}

	if (state.files.stillImages.length) {
		ok.push(t("validation.stillCount", { count: state.files.stillImages.length }));
		ok.push(t("validation.stillMotion"));
	}

	if (action === "analyze-person-edit-metadata") {
		const videos = selectedAnalysisVideos();
		ok.push(t("validation.personBbox", { path: shortPath(personBboxesDir()) }));
		ok.push(t("validation.editPlan", { path: shortPath(personEditPlansDir()) }));
		ok.push(t("validation.analysisFps", { fps: formValue("personFpsSample") }));
		if (videos.length) {
			ok.push(t("validation.selectedVideos", { count: videos.length }));
		} else {
			ok.push(t("validation.sourceRoots"));
		}
		if (formValue("personMaxSeconds")) {
			warnings.push(t("validation.testAnalysis"));
		}
	}

	if (action === "analyze-reference-video") {
		if (!state.files.referenceVideo) {
			errors.push(t("validation.referenceRequired"));
		}
		ok.push(t("validation.referenceShort"));
		ok.push(t("validation.referenceProfile", { path: shortPath(referenceEditProfilePath()) }));
		ok.push(t("validation.referenceBbox", { path: shortPath(referencePersonBboxesDir()) }));
		ok.push(t("validation.referenceEditPlan", { path: shortPath(referenceEditPlansDir()) }));
	}

	if (action === "shorten-input" && (!inputVideo || !outputPath)) {
		errors.push(t("validation.shortenNeedsInputOutput"));
	}
	if (["extract-still", "verify-duration", "verify-audio"].includes(action) && !inputVideo) {
		errors.push(t("validation.verificationNeedsInput"));
	}
	if (action === "generate-thumbnail") {
		if (!thumbnailInputPath()) {
			errors.push(t("validation.thumbnailNeedsInput"));
		}
		if (thumbnailOutputPath()) {
			ok.push(t("validation.thumbnailOutput", { path: shortPath(thumbnailOutputPath()) }));
		}
	}
	if (action === "generate-thumbnail-candidates") {
		if (!hasThumbnailCandidateSource()) {
			errors.push(t("validation.thumbnailCandidatesNeedsInput"));
		}
		if (thumbnailCandidatesOutputPath()) {
			ok.push(t("validation.thumbnailCandidatesOutput", { path: shortPath(thumbnailCandidatesOutputPath()) }));
			ok.push(
				t("validation.thumbnailCandidateSettings", {
					count: formValue("thumbnailCandidateCount") || 6,
					mode: selectedLabel("thumbnailMode") || formValue("thumbnailMode"),
					color: selectedLabel("thumbnailMainColor") || formValue("thumbnailMainColor"),
				}),
			);
			if (formValue("thumbnailDebugFaces")) {
				ok.push(t("validation.thumbnailDebugFaces"));
			}
		}
	}
	if (action === "review-subtitles") {
		if (!activeOutputRoot()) {
			errors.push(t("validation.subtitleReviewNeedsProject"));
		} else {
			ok.push(t("validation.subtitleReviewOutput", { path: shortPath(subtitleReviewOutputPath()) }));
			if (formValue("subtitleReviewExtractClips") || formValue("subtitleReviewTranscribeClips")) {
				ok.push(t("validation.subtitleReviewClips", { path: shortPath(subtitleReviewClipsPath()) }));
			}
			if (formValue("subtitleReviewTranscribeClips")) {
				ok.push(t("validation.subtitleReviewRetranscribe"));
			}
		}
	}
	if (action === "apply-subtitle-corrections") {
		if (!activeOutputRoot()) {
			errors.push(t("validation.subtitleReviewNeedsProject"));
		}
		if (!hasSubtitleCorrections()) {
			errors.push(t("validation.subtitleCorrectionsMissing"));
		}
		if (subtitleCorrectionsOutputPath()) {
			ok.push(t("validation.subtitleCorrectionsOutput", { path: shortPath(subtitleCorrectionsOutputPath()) }));
		}
	}
	if (action === "classify-subtitle-speakers") {
		if (!activeOutputRoot()) {
			errors.push(t("validation.subtitleReviewNeedsProject"));
		}
		if (!hasSubtitleSpeakerRules()) {
			warnings.push(t("validation.subtitleSpeakerRulesMissing"));
		}
		if (subtitleSpeakerRolesOutputPath()) {
			ok.push(t("validation.subtitleSpeakerRolesOutput", { path: shortPath(subtitleSpeakerRolesOutputPath()) }));
		}
		if (String(formValue("subtitleManualRoles") || "").trim()) {
			ok.push(t("validation.subtitleSpeakerManualRoles"));
		}
		if (formValue("subtitleMouthMotionDiagnostics")) {
			ok.push(t("validation.subtitleSpeakerMouthMotion"));
		}
	}
	if (action === "compare-transcripts") {
		if (!activeOutputRoot()) {
			errors.push(t("validation.subtitleReviewNeedsProject"));
		}
		if (transcriptComparisonOutputPath()) {
			ok.push(t("validation.transcriptComparisonOutput", { path: shortPath(transcriptComparisonOutputPath()) }));
		}
	}
	if (action === "replace-audio") {
		const replacementAudio = audioSources[0]?.path || state.files.externalAudio;
		if (!inputVideo || !outputPath) {
			errors.push(t("validation.replaceAudioNeedsInputOutput"));
		} else {
			ok.push(t("validation.replaceAudioOutput", { path: shortPath(outputPath) }));
			if (inputVideo === outputPath) {
				errors.push(t("validation.replaceAudioSamePath"));
			}
		}
		if (!replacementAudio) {
			errors.push(t("validation.replaceAudioNeedsExternal"));
		} else {
			ok.push(t("validation.replaceAudioSource", { path: shortPath(replacementAudio) }));
		}
	}

	const audioSource = formValue("audioSource");
	if (audioSource === "external-if-selected") {
		const external = audioSources[0]?.path || state.files.externalAudio;
		if (external) {
			ok.push(t("validation.audioExternal", { path: shortPath(external) }));
		} else {
			warnings.push(t("validation.audioFallbackMaster"));
		}
	}
	if (audioSource === "rightCloseVideo" && !state.files.rightCloseVideo) {
		warnings.push(t("validation.rightAudioFallback"));
	}
	if (audioSource === "leftCloseVideo" && !state.files.leftCloseVideo) {
		warnings.push(t("validation.leftAudioFallback"));
	}

	ok.push(t("validation.workflow", { label: selectedLabel("workflowAction") }));
	ok.push(
		t("validation.transcribe", {
			model: formValue("transcribeModel") || "large-v3",
			language: formValue("transcribeLanguage") || "ja",
		}),
	);
	ok.push(t("validation.subtitle", { mode: subtitleModeLabel() }));
	ok.push(
		formValue("termExplanations")
			? t("validation.termsOn", { count: glossaryTerms().filter((term) => term.enabled).length })
			: t("validation.termsOff"),
	);
	ok.push(
		formValue("audioDenoise")
			? t("validation.denoiseOn", { strength: formValue("audioDenoiseStrength") })
			: t("validation.denoiseOff"),
	);
	ok.push(formValue("colorMatchCameras") ? t("validation.colorMatchOn") : t("validation.colorMatchOff"));
	ok.push(formValue("usePersonEditPlans") ? t("validation.personCropOn") : t("validation.personCropOff"));
	ok.push(
		formValue("useTranscriptComparisonSync") ? t("validation.transcriptSyncOn") : t("validation.transcriptSyncOff"),
	);
	ok.push(formValue("naturalDialogueCuts") ? t("validation.naturalCutsOn") : t("validation.naturalCutsOff"));
	ok.push(formValue("audioMastering") ? t("validation.audioMasteringOn") : t("validation.audioMasteringOff"));
	ok.push(
		t("validation.encoder", {
			preset: selectedLabel("encoderPreset") || formValue("encoderPreset") || "veryfast",
			crf: formValue("renderCrf") || 18,
		}),
	);
	if (formValue("musicEnabled")) {
		const volume = Number(formValue("musicVolume") || 14);
		if (formValue("musicScope") === "omission") {
			ok.push(t("validation.musicOmission", { volume }));
			if (formValue("musicRangeSource") === "manual") {
				ok.push(t("validation.musicManualRanges"));
			} else {
				ok.push(t("validation.musicAutoRanges"));
			}
			if (formValue("musicRangeSource") === "manual" && !hasMusicRanges()) {
				warnings.push(t("validation.musicRangesMissing"));
			}
		} else {
			ok.push(t("validation.musicFull", { volume }));
		}
	} else {
		ok.push(t("validation.musicOff"));
	}
	if (formValue("omissionCardEnabled")) {
		ok.push(t("validation.omissionCardOn", { duration: formValue("omissionCardDuration") || 5 }));
		if (!hasOmissionCardRanges()) {
			warnings.push(t("validation.omissionCardMissingRanges"));
		}
	} else {
		ok.push(t("validation.omissionCardOff"));
	}
	ok.push(formValue("shortenSilence") ? t("validation.silenceOn") : t("validation.silenceOff"));
	const syncRows = describeSyncReport();
	if (syncRows.length) {
		const weakest = syncRows.reduce((min, row) => (row.score < min.score ? row : min), syncRows[0]);
		ok.push(t("validation.previousSync", { role: weakest.role, score: weakest.score.toFixed(3) }));
		if (weakest.score < 0.65) {
			warnings.push(t("validation.lowSyncScore"));
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
		"- Use the selected media manifest as the source of truth for cameras, audio, images, and subtitles.",
		"- Use scripts\\render_app_interview.py for renders from selected media.",
		"- Use scripts\\analyze_person_edit_metadata.py before edit planning when person position/crop decisions matter.",
		"- If a reference video is selected, analyze it first and use output\\reports\\reference_edit_profile.json as the style/layout target.",
		"- Treat the material directory as cameras/audio/images/logo/subtitles only; reference video is selected separately.",
		"- Keep existing user changes in the repo; do not revert unrelated files.",
		"",
		"Operator selections:",
		`- Edit preset: ${formValue("editPreset")}`,
		`- Direct workflow action: ${formValue("workflowAction")}`,
		`- Transcribe settings: model ${formValue("transcribeModel") || "large-v3"}, language ${formValue("transcribeLanguage") || "ja"}, beam ${formValue("transcribeBeamSize") || "5"}, temperature ${formValue("transcribeTemperature") || "0"}, loudnorm ${formValue("transcribeNormalizeAudio")}, low-confidence filter ${formValue("transcribeFilterLowConfidence")}, previous-text context ${formValue("conditionOnPreviousText")}`,
		`- Transcribe prompt terms: ${formValue("transcribePromptTerms") || "(use glossary terms only)"}`,
		`- Person analysis: ${formValue("personFpsSample")} fps, model ${formValue("personModel")}, confidence ${formValue("personConfidence")}, max seconds ${formValue("personMaxSeconds") || "all"}, limit ${formValue("personLimit") || "all"}`,
		`- Reference video: ${state.files.referenceVideo || "(not selected)"}`,
		`- Reference profile: ${referenceEditProfilePath()}`,
		`- Render script: ${formValue("renderScript")}`,
		`- Multicam mode: ${formValue("multicamMode")}`,
		`- Subtitle mode: ${state.subtitleMode}`,
		`- Audio source: ${formValue("audioSource")}`,
		`- Audio denoise: ${formValue("audioDenoise")} strength ${formValue("audioDenoiseStrength")}`,
		`- Audio mastering: ${formValue("audioMastering")}`,
		`- Encoder: preset ${formValue("encoderPreset") || "veryfast"}, CRF ${formValue("renderCrf") || "18"}`,
		`- Camera color match: ${formValue("colorMatchCameras")}`,
		`- Person-aware crop from analysis: ${formValue("usePersonEditPlans")}`,
		`- Transcript comparison sync fallback: ${formValue("useTranscriptComparisonSync")}`,
		`- Natural dialogue camera cuts: ${formValue("naturalDialogueCuts")}`,
		`- Music: enabled ${formValue("musicEnabled")}, placement ${formValue("musicScope")}, range source ${formValue("musicRangeSource") || "auto"}, level ${formValue("musicVolume")}%, direction ${formValue("musicPrompt") || "(auto from title/transcript)"}`,
		`- Music omission ranges: ${formValue("musicRangesText") || "(none)"}`,
		`- Omission card replacement: enabled ${formValue("omissionCardEnabled")}, duration ${formValue("omissionCardDuration") || "5"}s, label ${formValue("omissionCardLabel") || "SUMMARY"}`,
		`- Omission card text: ${formValue("omissionCardText") || "(default)"}`,
		`- Omission card replacement ranges: ${formValue("omissionCardRangesText") || formValue("musicRangesText") || "(none)"}`,
		`- Thumbnail: input ${thumbnailInputPath() || "(auto from current project)"}, time ${formValue("thumbnailTime") || formValue("stillTime") || "00:00:25"}, title ${formValue("thumbnailTitle") || state.analysisTitleText || "(analysis empty)"}, subtitle ${formValue("thumbnailSubtitle") || "(none)"}`,
		`- Thumbnail candidates: count ${formValue("thumbnailCandidateCount") || "6"}, mode ${formValue("thumbnailMode") || "standard"}, color ${formValue("thumbnailMainColor") || "yellow"}, debug faces ${formValue("thumbnailDebugFaces")}, times ${formValue("thumbnailCandidateTimes") || "(auto from project images/video)"}`,
		`- Subtitle QA thresholds: max segment ${formValue("subtitleReviewMaxDuration") || "8"}s, max reading speed ${formValue("subtitleReviewMaxCharsPerSecond") || "18"} chars/s`,
		`- Subtitle suspicious patterns: ${formValue("subtitleSuspiciousPatterns") || "(none)"}`,
		`- Subtitle QA audio clips: extract ${formValue("subtitleReviewExtractClips")}, re-transcribe ${formValue("subtitleReviewTranscribeClips")}`,
		`- Subtitle corrections: ${formValue("subtitleCorrectionsText") || "(none)"}`,
		`- Subtitle interviewer ranges: ${formValue("subtitleInterviewerRanges") || "(none)"}`,
		`- Subtitle interviewer patterns: ${formValue("subtitleInterviewerPatterns") || "(none)"}`,
		`- Subtitle manual speaker roles: ${formValue("subtitleManualRoles") || "(none)"}`,
		`- Subtitle mouth-motion diagnostic: ${formValue("subtitleMouthMotionDiagnostics")}`,
		`- Transcript comparison report: ${transcriptComparisonOutputPath() || "(project output not set)"}`,
		`- Preview start: ${formValue("previewStart")} seconds`,
		`- Output duration: ${formValue("previewDuration")} seconds`,
		`- Shorten long silence: ${formValue("shortenSilence")}`,
		`- Silence options: min ${formValue("minSilence")}s, keep ${formValue("keepSilence")}s, noise ${formValue("silenceNoise")}, keep uncut ${formValue("keepUncut")}`,
		"- Regenerate text overlays from current analysis: true",
		`- Term explanations: ${formValue("termExplanations")} (${
			glossaryTerms()
				.filter((term) => term.enabled)
				.map((term) => term.label)
				.join(", ") || "none"
		})`,
		`- Output path: ${outputPath}`,
		`- Active project: ${state.project ? `${state.project.name} (${state.project.root})` : "(none; using workspace defaults)"}`,
		`- AI-editable project state: ${state.projectStatePath || "(project not saved yet)"}`,
		`- Project source root: ${activeSourceRoot() || "(not set)"}`,
		`- Project output root: ${activeOutputRoot() || "(not set)"}`,
		`- Material sources: ${state.materialPaths.length ? state.materialPaths.join("; ") : state.mediaDirectory || "(not ingested)"}`,
		`- Media manifest: ${mediaManifestPath() || "(not generated)"}`,
		`- Manifest cameras: ${
			manifestCameras()
				.map((item) => `${item.role}=${item.path}`)
				.join("; ") || "(none)"
		}`,
		`- Manifest audio: ${
			manifestAudioSources()
				.map((item) => `${item.role}=${item.path}`)
				.join("; ") || "(none)"
		}`,
		`- Still extraction time: ${formValue("stillTime") || "00:00:25"}`,
		`- Person bbox output: ${personBboxesDir()}`,
		`- Person edit plan output: ${personEditPlansDir()}`,
		`- Reference person edit plan output: ${referenceEditPlansDir()}`,
		`- Python: ${pythonExe()}`,
		`- FFmpeg: ${ffmpegExe()}`,
		`- FFprobe: ${ffprobeExe()}`,
		"",
		"Dropped assets:",
		`- Master/day video: ${state.files.masterVideo || "(none)"}`,
		`- Right close-up/person 1: ${state.files.rightCloseVideo || "(none)"}`,
		`- Left close-up/person 2: ${state.files.leftCloseVideo || "(none)"}`,
		`- Reference style video: ${state.files.referenceVideo || "(not selected)"}`,
		`- External audio: ${state.files.externalAudio || "(not selected)"}`,
		`- Logo: ${state.files.logo || "(none)"}`,
		`- Still image inserts: ${state.files.stillImages.length ? state.files.stillImages.join(", ") : "(none)"}`,
		"",
		"Style selections:",
		`- Subtitle font size target: ${formValue("subtitleSize")}`,
		`- Subtitle highlight color: ${formValue("highlightColor")}`,
		`- Subtitle box opacity: ${formValue("boxOpacity")} percent`,
		`- Top-left text: ${state.analysisTitleText}`,
		`- Top-left text size: ${formValue("titleSize")}`,
		`- Right-top logo height: ${formValue("logoHeight")} px`,
		`- Punchline list:\n${formValue("punchlineText") || "(empty)"}`,
		"",
		"Expected behavior:",
		"- To change operator options, update the AI-editable project_state.json file. The app treats it as the project-level source of truth and reloads it while this project is active.",
		"- Keep generated reports, transcripts, and media files in their existing output folders; keep project_state.json focused on options and selected project state.",
		"- If external audio is selected, sync it or clearly report if existing offset data cannot be reused.",
		"- If no external audio is selected, use the selected camera audio source.",
		"- Prefer the media manifest for source roles. Support variable interview/multicam camera roles: master, camera2, camera3, camera4+.",
		"- For person-aware crop/cut planning, analyze source videos first, then use output\\reports\\person_edit_plans as metadata for camera/crop decisions.",
		"- When multicam mode is dynamic-cuts, build short current-project camera segments and punch-in reframes; do not use historical fixed camera timings.",
		"- Respect each camera source's synced coverage; do not use alternate-camera clips outside their valid timeline range.",
		"- For weak or missing waveform sync, use only the current transcript comparison report when its media-manifest fingerprint matches the active project.",
		"- When natural dialogue cuts are enabled, move camera boundaries only to nearby low-energy dialogue gaps; do not change audio timing.",
		"- When audio mastering is enabled, apply the common high-pass, noise reduction, dynamics, and loudness chain to the selected project audio.",
		"- When replacing video audio, copy the selected input video's video stream and use only the current project external audio plus current sync report.",
		"- Reflect the reference profile in the edit: match person size, layout, face direction when possible, and visual tone (brightness, contrast, saturation, warmth).",
		"- For full subtitles, use only the current transcription result for the selected media manifest.",
		"- For source transcript comparison, compare only the current project transcript manifest and write the report under output\\reports.",
		"- For subtitle QA audio clips, use only the current project primary transcript/audio and write clips under output\\diagnostics.",
		"- For catchy subtitles, use the punchline overlay mode.",
		"- Make minimal script changes needed for this request, then render or provide the exact command if rendering is blocked.",
		"- Report the output file path and any limitations.",
	];
	return lines.join("\n");
}

function buildAppConfig() {
	const analysisTitleText = state.analysisTitleText;
	return {
		project: {
			id: state.project?.id || "",
			name: state.project?.name || "",
			root: state.project?.root || "",
			sourceRoot: activeSourceRoot(),
			outputRoot: activeOutputRoot(),
		},
		assets: {
			mediaDirectory: state.mediaDirectory,
			materialPaths: state.materialPaths,
			mediaManifestPath: mediaManifestPath(),
			mediaManifest: state.mediaManifest,
			masterVideo: state.files.masterVideo,
			rightCloseVideo: state.files.rightCloseVideo,
			leftCloseVideo: state.files.leftCloseVideo,
			referenceVideo: state.files.referenceVideo,
			externalAudio: state.files.externalAudio,
			logo: state.files.logo,
			stillImages: state.files.stillImages,
			sourceRoot: activeProjectVideoSourceRoot(),
		},
		render: {
			editPreset: formValue("editPreset"),
			workflowAction: formValue("workflowAction"),
			renderScript: formValue("renderScript"),
			outputPath: $("#outputPath").value,
			syncOffsetsPath: syncReportPath(),
			subtitleMode: state.subtitleMode,
			multicamMode: formValue("multicamMode"),
			audioSource: formValue("audioSource"),
			audioDenoise: formValue("audioDenoise"),
			audioDenoiseStrength: Number(formValue("audioDenoiseStrength") || 10),
			audioMastering: formValue("audioMastering"),
			encoderPreset: formValue("encoderPreset") || "veryfast",
			crf: Number(formValue("renderCrf") || 18),
			colorMatchCameras: formValue("colorMatchCameras"),
			usePersonEditPlans: formValue("usePersonEditPlans"),
			useTranscriptComparisonSync: formValue("useTranscriptComparisonSync"),
			naturalDialogueCuts: formValue("naturalDialogueCuts"),
			previewStart: Number(formValue("previewStart") || 0),
			previewDuration: Number(formValue("previewDuration") || 60),
			termExplanations: formValue("termExplanations"),
			shortenSilence: formValue("shortenSilence"),
			minSilence: Number(formValue("minSilence") || 3),
			keepSilence: Number(formValue("keepSilence") || 2),
			silenceNoise: formValue("silenceNoise") || "-30dB",
			keepUncut: formValue("keepUncut"),
		},
		music: {
			enabled: formValue("musicEnabled"),
			scope: formValue("musicScope") || "full",
			rangeSource: formValue("musicRangeSource") || "auto",
			prompt: formValue("musicPrompt"),
			mood: "auto",
			volume: Number(formValue("musicVolume") || 14),
			rangesText: formValue("musicRangesText"),
			regenerate: true,
			outputPath: musicBedPath(),
		},
		omissionCard: {
			enabled: formValue("omissionCardEnabled"),
			duration: Number(formValue("omissionCardDuration") || 5),
			label: formValue("omissionCardLabel") || "SUMMARY",
			text: formValue("omissionCardText"),
			rangesText: formValue("omissionCardRangesText") || formValue("musicRangesText"),
			useMusicRanges: true,
			outputPath: omissionCardOutputPath(),
		},
		thumbnail: {
			inputVideoPath: thumbnailInputPath(),
			time: formValue("thumbnailTime") || formValue("stillTime") || "00:00:25",
			title: formValue("thumbnailTitle") || analysisTitleText,
			subtitle: formValue("thumbnailSubtitle"),
			outputPath: thumbnailOutputPath(),
			candidatesOutputDir: thumbnailCandidatesOutputPath(),
			candidateCount: Number(formValue("thumbnailCandidateCount") || 6),
			mode: formValue("thumbnailMode") || "standard",
			mainColor: formValue("thumbnailMainColor") || "yellow",
			candidateTimesText: formValue("thumbnailCandidateTimes"),
			debugFaces: formValue("thumbnailDebugFaces"),
		},
		subtitleReview: {
			outputPath: subtitleReviewOutputPath(),
			maxDuration: Number(formValue("subtitleReviewMaxDuration") || 8),
			maxCharsPerSecond: Number(formValue("subtitleReviewMaxCharsPerSecond") || 18),
			suspiciousPatternsText: formValue("subtitleSuspiciousPatterns"),
			extractAudioClips: formValue("subtitleReviewExtractClips") || formValue("subtitleReviewTranscribeClips"),
			transcribeReview: formValue("subtitleReviewTranscribeClips"),
			reviewModel: formValue("transcribeModel") || "large-v3",
			correctionsText: formValue("subtitleCorrectionsText"),
			correctionsOutputPath: subtitleCorrectionsOutputPath(),
		},
		subtitleSpeakers: {
			outputPath: subtitleSpeakerRolesOutputPath(),
			interviewerRangesText: formValue("subtitleInterviewerRanges"),
			interviewerPatternsText: formValue("subtitleInterviewerPatterns"),
			manualRolesText: formValue("subtitleManualRoles"),
			mouthMotionDiagnostics: formValue("subtitleMouthMotionDiagnostics"),
			motionVideoPath: formValue("inputVideoPath") || $("#outputPath").value || selectedMasterVideoPath(),
		},
		transcriptComparison: {
			outputPath: transcriptComparisonOutputPath(),
			strongThreshold: 0.82,
			usableThreshold: 0.7,
			matchLimit: 12,
		},
		workflow: {
			inputVideoPath: formValue("inputVideoPath"),
			stillTime: formValue("stillTime") || "00:00:25",
			stillOutputPath: stillOutputPath(formValue("inputVideoPath") || $("#outputPath").value, $("#outputPath").value),
		},
		replaceAudio: {
			inputVideoPath: formValue("inputVideoPath"),
			audioPath: state.files.externalAudio || manifestAudioSources()[0]?.path || "",
			outputPath: $("#outputPath").value,
			syncOffsetsPath: syncReportPath(),
		},
		analysis: {
			transcribeModel: formValue("transcribeModel") || "large-v3",
			transcribeLanguage: formValue("transcribeLanguage") || "ja",
			transcribeBeamSize: Number(formValue("transcribeBeamSize") || 5),
			transcribeTemperature: Number(formValue("transcribeTemperature") || 0),
			transcribePromptTerms: formValue("transcribePromptTerms"),
			transcribeNormalizeAudio: formValue("transcribeNormalizeAudio"),
			transcribeFilterLowConfidence: formValue("transcribeFilterLowConfidence"),
			conditionOnPreviousText: formValue("conditionOnPreviousText"),
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
			titleText: analysisTitleText,
			titleSize: Number(formValue("titleSize") || 64),
			logoHeight: Number(formValue("logoHeight") || 48),
			punchlineText: formValue("punchlineText"),
		},
		glossary: {
			enabled: formValue("termExplanations"),
			terms: glossaryTerms(),
		},
		tools: {
			python: pythonExe(),
			ffmpeg: ffmpegExe(),
			ffprobe: ffprobeExe(),
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
		setStatus(t("status.projectError"), "idle");
		return false;
	}
	refreshCommand();
	const validation = validateSelections();
	if (validation.errors.length) {
		updateRunSummary();
		setStatus(t("status.checkRequiredFields"), "idle");
		log("direct run blocked", { errors: validation.errors });
		return false;
	}
	const { command, reason } = buildPresetCommand();
	if (!command) {
		log("direct run unavailable", { reason });
		return false;
	}
	await persistProjectStateFileNow();
	const action = formValue("workflowAction");
	const label = directRunLabel(action);
	state.runningAction = action;
	state.lastWorkflowProgressLog = 0;
	state.lastWorkflowStage = "";
	setDirectRunRunning(true, label);
	setAppLocked(
		true,
		t("format.runningMessage", { label }),
		action === "render-selected" ? t("status.rendering") : t("analysis.statusRunning"),
	);
	setStatus(action === "render-selected" ? t("status.rendering") : t("status.presetRunning"), "busy");
	setIngestProgress({
		progress: 0.01,
		message: t("format.startingMessage", { label }),
		path: directRunOutputPath(action),
	});
	log("command/exec", { command });
	try {
		const result = await editApp.runWorkflowAction({
			action,
			timeoutMs: 6 * 60 * 60 * 1000,
			appConfig: buildAppConfig(),
		});
		if (result?.stdout) {
			log("stdout", { text: compactOutput(result.stdout) });
		}
		if (result?.stderr) {
			log("stderr", { text: compactOutput(result.stderr) });
		}
		log("command completed", { exitCode: result?.exitCode });
		if (action === "auto-sync-dropped" && result?.exitCode === 0) {
			await refreshSyncReport();
		}
		if (action === "analyze-person-edit-metadata" && result?.exitCode === 0) {
			log("person analysis outputs", { bboxes: personBboxesDir(), plans: personEditPlansDir() });
		}
		if (action === "analyze-reference-video" && result?.exitCode === 0) {
			log("reference analysis output", { profile: referenceEditProfilePath() });
		}
		const ok = result?.exitCode === 0;
		if (
			ok &&
			[
				"auto-sync-dropped",
				"transcribe-dropped",
				"compare-transcripts",
				"analyze-person-edit-metadata",
				"analyze-blocking",
				"analyze-reference-video",
			].includes(action)
		) {
			await restoreAnalysisResultsFromOutputs(state.mediaManifest);
		}
		setIngestProgress({
			progress: ok ? 1 : state.lastWorkflowProgressLog || 0,
			message: ok ? t("format.completeMessage", { label }) : t("format.errorMessage", { label }),
			path: directRunOutputPath(action),
		});
		setStatus(ok ? t("status.runComplete") : t("status.commandFailed"), ok ? "ready" : "idle");
		if (ok && action === "render-selected") {
			await notifyAnalysisComplete(t("notification.renderComplete"));
		}
		return ok;
	} catch (error) {
		setStatus(t("status.commandError"), "idle");
		setIngestProgress({
			progress: state.lastWorkflowProgressLog || 0,
			message: t("format.errorMessage", { label }),
			path: directRunOutputPath(action),
		});
		log("command error", { message: error.message });
		return false;
	} finally {
		setAppLocked(false);
		setDirectRunRunning(false);
		state.runningAction = "";
	}
}

async function sendRequest() {
	if (!(await prepareProjectForRun())) {
		setStatus(t("status.projectError"), "idle");
		return;
	}
	refreshPrompt();
	await persistProjectStateFileNow();
	setStatus(t("status.codexRunning"), "busy");
	setCodexTurnRunning(true);
	log("turn/start");
	try {
		state.codexModel = selectedCodexModelForRun();
		await editApp.startCodexTurn({
			settings: {
				model: state.codexModel,
				effort: selectedCodexReasoningEffort(),
			},
			prompt: $("#promptPreview").value,
		});
	} catch (error) {
		setCodexTurnRunning(false);
		setStatus(t("status.codexError"), "idle");
		log("error", { message: error.message });
	}
}

async function stopCodexTurn() {
	if (!state.codexTurnRunning || state.codexInterruptRequested) {
		return;
	}
	state.codexInterruptRequested = true;
	updateCodexRunControls();
	setStatus(t("status.codexStopping"), "busy");
	try {
		await editApp.interruptCodex();
		log("turn/interrupt requested");
	} catch (error) {
		state.codexInterruptRequested = false;
		updateCodexRunControls();
		setStatus(t("status.codexError"), "idle");
		log("turn/interrupt failed", { message: error.message });
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
	if (method === "thread/status/changed" && params.status?.type === "systemError") {
		setCodexTurnRunning(false);
		setStatus(t("status.codexError"), "idle");
		log(method, params);
		return;
	}
	if (method === "turn/completed") {
		const turn = params.turn || {};
		setCodexTurnRunning(false);
		if (turn.status === "failed") {
			setStatus(t("status.codexError"), "idle");
			log("turn failed", { message: codexErrorMessage(turn.error) || "Codex turn failed" });
			return;
		}
		if (turn.status === "interrupted") {
			setStatus(t("status.codexStopped"), "ready");
			log(method, params);
			return;
		}
		setStatus(t("status.codexIdle"), "ready");
		log(method, params);
		return;
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
			const files = Array.from((event as DragEvent).dataTransfer?.files || []) as File[];
			if (slot === "mediaDirectory") {
				const droppedPaths = files.map((file) => editApp.filePath(file)).filter(Boolean);
				if (droppedPaths.length) {
					addMaterialSources(droppedPaths);
				}
				return;
			}
			if (slot === "stillImages") {
				addStillImages(files.map((file) => editApp.filePath(file)).filter(Boolean));
				return;
			}
			if (files[0]) {
				setFile(slot, editApp.filePath(files[0]));
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
	$("#changeProject").addEventListener("click", changeProject);
	$("#closeProjectDialog").addEventListener("click", () => setProjectDialogOpen(false));
	$("#cancelProjectDialog").addEventListener("click", () => setProjectDialogOpen(false));
	$("#createProjectFromDialog").addEventListener("click", createProjectFromDialog);
	$("#projectDialog").addEventListener("click", (event) => {
		if (event.target === $("#projectDialog")) {
			setProjectDialogOpen(false);
		}
	});
	$("#projectDialogName").addEventListener("keydown", (event) => {
		if (event.key === "Enter") {
			event.preventDefault();
			void createProjectFromDialog();
		}
	});
	$("#copyProjectAssets").addEventListener("click", copyAssetsToProject);
	$("#deleteProject").addEventListener("click", deleteCurrentProject);
	$("#pickMaterialDirectory").addEventListener("click", pickMaterialDirectory);
	$("#pickMaterialFiles").addEventListener("click", pickMaterialFiles);
	$("#analyzeMaterialDirectory").addEventListener("click", () => ingestMaterialDirectory());
	$("#cancelMaterialAnalysis").addEventListener("click", cancelMaterialAnalysis);
	$("#projectName").addEventListener("input", () => {
		if (!formValue("projectId")) {
			$("#projectId").value = projectIdFromName(formValue("projectName"));
		}
		refreshPrompt();
	});
	$("#refreshCommand").addEventListener("click", refreshCommand);
	$("#refreshPrompt").addEventListener("click", refreshPrompt);
	$("#refreshCodexModels").addEventListener("click", loadCodexModels);
	$("#modelName").addEventListener("change", () => {
		state.codexModel = ($("#modelName") as HTMLSelectElement | null)?.value || "";
	});
	$("#refreshSyncReport").addEventListener("click", refreshSyncReport);
	$("#loadGlossaryCandidates").addEventListener("click", loadGlossaryCandidates);
	$("#addGlossaryTerm").addEventListener("click", addGlossaryTerm);
	$("#runPreset").addEventListener("click", runPreset);
	$("#sendRequest").addEventListener("click", sendRequest);
	$("#stopCodexTurn").addEventListener("click", stopCodexTurn);
	$("#interrupt").addEventListener("click", stopCodexTurn);
	$("#openOutput").addEventListener("click", () => loadOutputPreview("output"));
	$("#refreshOutputPreview").addEventListener("click", () => {
		if (state.outputPreviewKind) {
			loadOutputPreview(state.outputPreviewKind);
		}
	});
	$("#openPreviewFolder").addEventListener("click", () => {
		const previewPath = state.outputPreview?.path || outputPreviewTarget();
		if (previewPath) {
			editApp.showPath(previewPath);
		}
	});
	$("#languageMenuButton").addEventListener("click", (event) => {
		event.stopPropagation();
		setLanguageMenuOpen(Boolean($("#languagePopover")?.hidden));
	});
	document.addEventListener("click", (event) => {
		const switcher = $(".language-switcher");
		if (switcher && !switcher.contains(event.target as Node)) {
			setLanguageMenuOpen(false);
		}
	});
	document.addEventListener("keydown", (event) => {
		if (event.key === "Escape" && !$("#projectDialog")?.hidden) {
			setProjectDialogOpen(false);
		}
	});
	$$("[data-language]").forEach((button) => {
		button.addEventListener("click", (event) => {
			event.stopPropagation();
			setLanguage(normalizeLanguage(button.dataset.language));
		});
	});
	$$("input, select, textarea").forEach((element) => {
		element.addEventListener("input", refreshPrompt);
		element.addEventListener("change", refreshPrompt);
	});
	$("#editPreset").addEventListener("change", () => {
		const mapping = {
			"new-interview": "render_app_interview.py",
		};
		const durations = {
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
			setActiveSection(button.dataset.section);
			if (button.dataset.section === "run" && !state.codexModels.length) {
				void loadCodexModels();
			}
			window.scrollTo({ top: 0, behavior: "smooth" });
		});
	});
}

async function init() {
	state.env = await editApp.getEnvironment();
	renderWorkspaceLabel();
	$("#outputPath").value = state.env.knownOutputs?.[0] || "";
	$("#inputVideoPath").value = state.env.knownOutputs?.[0] || "";
	loadWorkflowMediaPreviews();
	loadOutputTargetPreview();
	const pythonPathInput = $("#pythonPath");
	if (pythonPathInput) {
		pythonPathInput.value = state.env.pythonExe;
	}
	const ffmpegPathInput = $("#ffmpegPath");
	if (ffmpegPathInput) {
		ffmpegPathInput.value = state.env.ffmpegExe;
	}
	const ffprobePathInput = $("#ffprobePath");
	if (ffprobePathInput) {
		ffprobePathInput.value = state.env.ffprobeExe;
	}
	$("#punchlineText").value = defaultPunchlines;
	state.glossaryTerms = defaultGlossaryTerms;
	loadState();
	const restoredProject = await restoreLatestProjectFromDisk();
	if (!restoredProject) {
		await loadProjectStateFile();
	}
	renderGlossaryList();
	renderMediaManifest();
	initDropZones();
	bindEvents();
	applyTranslations();
	renderCodexModelOptions();
	renderCodexModelStatus();
	updateCodexRunControls();
	setActiveSection(state.activeSection);
	setStatus(state.statusText, state.statusKind);
	refreshPrompt();

	editApp.onServerReady(() => {
		setStatus(t("status.codexReady"), "ready");
		log("server ready");
	});
	editApp.onServerError((payload) => {
		setCodexTurnRunning(false);
		setStatus(t("status.codexError"), "idle");
		log("server error", payload);
	});
	editApp.onServerExit((payload) => {
		setCodexTurnRunning(false);
		setStatus(t("status.codexExited"), "idle");
		log("server exit", payload);
	});
	editApp.onServerStderr((payload) => log("stderr", payload));
	editApp.onServerNotification(handleNotification);
	editApp.onWorkflowProgress(handleWorkflowProgress);
	editApp.onProjectStateChanged(async (payload) => {
		if (!state.project || payload?.project?.id !== state.project.id) {
			return;
		}
		await loadProjectStateFile(state.project);
	});
	editApp.onIngestProgress((payload) => {
		const progressPayload =
			state.fullAnalysisRunning && payload?.stage !== "canceled"
				? {
						...payload,
						progress: 0.02 + Math.min(1, Math.max(0, Number(payload?.progress || 0))) * 0.18,
					}
				: payload;
		setIngestProgress(progressPayload);
		if (state.appLocked && payload?.message) {
			const busyMessage = $("#appBusyMessage");
			if (busyMessage) {
				busyMessage.textContent = localizePlainText(payload.message);
			}
		}
		if (payload?.stage === "canceled") {
			setIngestRunning(false);
		}
		const shouldLog = payload?.stage && !["probe", "copy"].includes(payload.stage);
		if (shouldLog && payload?.message) {
			log("ingest progress", {
				stage: payload.stage,
				current: payload.current,
				total: payload.total,
				message: payload.message,
				path: payload.path,
			});
		}
	});
	refreshSyncReport();
	if (state.activeSection === "run") {
		void loadCodexModels();
	}
	const loadedAnalysisState = await loadAnalysisStateFile();
	if (!loadedAnalysisState) {
		await restoreAnalysisResultsFromOutputs(state.mediaManifest);
	}
	if (state.mediaManifest) {
		await refreshAnalysisTitleFromAnalysis(state.mediaManifest);
	}
}

init().catch((error) => {
	log("init error", { message: error.message });
});
