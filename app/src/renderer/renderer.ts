type Unsubscribe = () => void;

type EditAppApi = {
	getEnvironment: () => Promise<any>;
	createProject: (payload: any) => Promise<ProjectInfo>;
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
	execCodexCommand: (payload: any) => Promise<any>;
	runWorkflowAction: (payload: any) => Promise<any>;
	interruptCodex: () => Promise<any>;
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
};

const editApp = (window as unknown as { editApp: EditAppApi }).editApp;

type ProjectInfo = {
	id: string;
	name: string;
	root: string;
	sourceRoot: string;
	outputRoot: string;
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
	mediaManifest: null as MediaManifest | null,
	mediaDirectory: "",
	materialPaths: [] as string[],
	ingestRunning: false,
	fullAnalysisRunning: false,
	directRunRunning: false,
	runningAction: "",
	lastWorkflowProgressLog: 0,
	lastWorkflowStage: "",
	appLocked: false,
	analysisResults: [] as Array<{ key: string; label: string; status: string; detail: string; path?: string }>,
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
const LEGACY_DEFAULT_TITLE = "AIエンジニアの今";
const thumbnailModes = {
	standard: {
		flag: "",
		labelKey: "option.thumbnailStandard",
	},
	closeup_bottom_title: {
		flag: "--closeup-bottom-title",
		labelKey: "option.thumbnailCloseup",
	},
	right_face_title_stack: {
		flag: "--right-face-title-stack",
		labelKey: "option.thumbnailRightFace",
	},
	left_face_title_stack: {
		flag: "--left-face-title-stack",
		labelKey: "option.thumbnailLeftFace",
	},
};
const thumbnailMainColors = {
	yellow: "color.yellow",
	red: "color.red",
	orange: "color.orange",
	green: "color.green",
	blue: "color.blue",
	cyan: "color.cyan",
	purple: "color.purple",
	pink: "color.pink",
	white: "color.white",
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
		"status.projectError": "プロジェクトエラー",
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
		"action.openThumbnails": "サムネ候補を確認",
		"action.openInExplorer": "Explorerで開く",
		"action.refreshPreview": "更新",
		"action.runPresetScript": "選択中の工程を実行",
		"action.runWithCodex": "AIに編集を依頼",
		"preview.heading": "生成物プレビュー",
		"preview.outputTitle": "出力フォルダ",
		"preview.thumbnailsTitle": "サムネフォルダ",
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
		"project.createSelect": "この名前で開始",
		"project.change": "プロジェクトを切り替え",
		"project.copySelectedSources": "選択素材を保存",
		"project.delete": "プロジェクト削除",
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
		"asset.currentRepoLogo": "現在のリポジトリロゴ",
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
		"edit.noiseStrength": "ノイズ低減の強さ",
		"edit.start": "開始位置",
		"edit.outputDuration": "出力尺",
		"edit.shortenSilence": "長い無音を詰める",
		"edit.keepUncut": "未カットの下書き動画を残す",
		"edit.minSilence": "詰める無音の長さ",
		"edit.keepSilence": "残す無音",
		"edit.noise": "無音判定の音量",
		"option.current1MinColor": "現行 1分カラー調整編集",
		"option.currentOnepass": "現行 1分クイック編集",
		"option.current5Min": "現行 5分仕上げ編集",
		"option.newInterview": "選択素材から新規インタビュー編集",
		"option.speakerAware": "話者に合わせたインタビューカット",
		"option.manualPlan": "保存済みの手動プランを使用",
		"option.masterFirst": "マスター優先、強調時にアップ",
		"option.externalIfSelected": "別録り音声があれば使用",
		"option.masterAudio": "マスター動画の音声を使用",
		"option.rightAudio": "右アップの音声を使用",
		"option.leftAudio": "左アップの音声を使用",
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
		"workflow.thumbnailLayout": "サムネレイアウト",
		"workflow.thumbnailMainColor": "サムネメイン色",
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
		"workflow.verificationInput": "処理対象の動画",
		"workflow.audioReplaceSource": "差し替えに使う音声入り動画",
		"workflow.selectInputVideo": "入力動画を選択",
		"workflow.selectAudioReplaceSource": "差し替え元動画を選択",
		"workflow.stillTime": "静止画にする時刻",
		"workflow.personSampleFps": "人物解析の細かさ",
		"workflow.yoloModel": "人物検出モデル",
		"workflow.personConfidence": "人物検出のしきい値",
		"workflow.analysisMaxSeconds": "テスト解析の秒数",
		"workflow.videoLimit": "解析する動画数",
		"workflow.rebuildBase": "1分の下書き動画を作り直す",
		"workflow.reuseOverlays": "既存の字幕画像を使う",
		"workflow.reclassifySpeakers": "話者を検出し直す",
		"workflow.autoContextCuts": "字幕文脈と話者で自動カット",
		"workflow.naturalDialogueCuts": "自然な会話の間でカットする",
		"workflow.retranscribeReview": "字幕レビュークリップを再文字起こし",
		"workflow.skipReviewAudioClips": "字幕レビュー音声クリップをスキップ",
		"workflow.reviewModel": "字幕レビュー品質",
		"workflow.personNoMulticamRoot": "選択したプロジェクト動画だけ解析",
		"workflow.syncScore": "同期スコア",
		"action.refresh": "更新",
		"option.renderSelected": "選択した設定で動画を作成",
		"option.subtitleReview": "字幕を確認・修正",
		"option.generatePunchlines": "見せ場字幕画像を作成",
		"option.generateFullOverlays": "全文字幕画像を作成",
		"option.generateGlossaryOverlays": "専門用語解説画像を作成",
		"option.generateThumbnails": "サムネ候補を作成",
		"option.analyzeBlocking": "カメラ構図を解析",
		"option.analyzePersonEdit": "人物とカット候補を解析",
		"option.analyzeReference": "参考動画を解析",
		"option.autoSyncDropped": "選択したカメラ素材を同期",
		"option.transcribeDropped": "選択素材を文字起こし",
		"option.transcribeAlign": "文字起こしを使って同期",
		"option.compareAllCameras": "全カメラの文字起こしを比較",
		"option.refineStrongWave": "音声同期をさらに調整",
		"option.buildBase": "マルチカムの下書き動画を作成",
		"option.transcribeSound2": "差し替え音声を文字起こし",
		"option.compareSound2": "差し替え音声の文字起こしを比較",
		"option.refineSound2": "差し替え音声の同期を微調整",
		"option.replaceSound2": "動画の音声を差し替え",
		"option.shortenInput": "選択入力動画の無音を詰める",
		"option.extractStill": "静止画を書き出す",
		"option.verifyDuration": "動画の長さを確認",
		"option.verifyAudio": "動画の音声を確認",
		"option.thumbnailStandard": "標準: 画像ごとに文字配置",
		"option.thumbnailCloseup": "顔中央: 下部1行タイトル",
		"option.thumbnailRightFace": "顔右: 左に積みタイトル",
		"option.thumbnailLeftFace": "顔左: 右に積みタイトル",
		"color.yellow": "黄",
		"color.red": "赤",
		"color.orange": "オレンジ",
		"color.green": "緑",
		"color.blue": "青",
		"color.cyan": "シアン",
		"color.purple": "紫",
		"color.pink": "ピンク",
		"color.white": "白",
		"option.render1MinColor": "1分カラー調整編集",
		"option.render1MinOnepass": "1分クイック編集",
		"option.render5MinOverlays": "5分仕上げ編集",
		"option.renderAppInterview": "選択素材からインタビュー編集",
		"action.file": "ファイル",
		"placeholder.all": "すべて",
		"codex.heading": "AIへの依頼",
		"codex.prompt": "AIに送る内容",
		"codex.details": "依頼内容と実行内容を確認",
		"codex.reviewBeforeRunning": "実行前に確認",
		"codex.directCommand": "実行内容",
		"action.refreshCommand": "実行内容を更新",
		"action.refreshPrompt": "依頼内容を更新",
		"action.interrupt": "実行を停止",
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
		"runLabel.thumbnail": "サムネ生成",
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
		"validation.thumbnailGenerate": "サムネ候補を {mode} / {color} で生成します。",
		"validation.preview": "確認用: {path}",
		"validation.thumbnailImport": "選択した素材からサムネ候補を読み込みます。",
		"validation.personBbox": "人物bbox: {path}",
		"validation.editPlan": "編集プラン: {path}",
		"validation.analysisFps": "解析間隔: {fps} fps",
		"validation.selectedVideos": "解析対象: 選択済み動画 {count}本",
		"validation.sourceRoots": "解析対象: source/video と 2cam/3cam root",
		"validation.testAnalysis": "テスト解析の秒数が入っているため、全尺ではなく一部だけ解析します。",
		"validation.referenceRequired": "参考動画を1本ドラッグ&ドロップしてください。",
		"validation.referenceShort": "参考動画は60秒以内として解析します。超えている場合は実行時に止めます。",
		"validation.referenceProfile": "参考プロファイル: {path}",
		"validation.referenceBbox": "参考人物bbox: {path}",
		"validation.referenceEditPlan": "参考編集プラン: {path}",
		"validation.replaceNeedsOutput": "音声差し替えには出力先が必要です。",
		"validation.shortenNeedsInputOutput": "無音詰めには入力動画と出力先が必要です。",
		"validation.verificationNeedsInput": "この工程には処理対象の動画が必要です。",
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
		"validation.silenceOn": "無音詰め: ON",
		"validation.silenceOff": "無音詰め: OFF",
		"validation.previousSync": "前回同期: {role} score {score}",
		"validation.lowSyncScore": "前回の自動同期スコアが低い素材があります。短尺QAで音ズレ確認してください。",
		"notification.renderComplete": "レンダーが完了しました。",
		"notification.analysisComplete": "素材解析・文字起こし・OpenCV解析が完了しました。",
		"notification.analysisCompleteCheck": "解析は完了しました。一部の結果を確認してください。",
		"log.projectNotSelected": "プロジェクトが選択されていません",
		"log.cannotDeleteDuringIngest": "素材解析中は削除できません",
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
		"status.projectError": "Project error",
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
		"action.openThumbnails": "Review thumbnail candidates",
		"action.openInExplorer": "Open in Explorer",
		"action.refreshPreview": "Refresh",
		"action.runPresetScript": "Run selected workflow step",
		"action.runWithCodex": "Ask AI to edit",
		"preview.heading": "Generated file preview",
		"preview.outputTitle": "Output folder",
		"preview.thumbnailsTitle": "Thumbnail folder",
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
		"project.createSelect": "Start this project",
		"project.change": "Switch project",
		"project.copySelectedSources": "Save selected material",
		"project.delete": "Delete project",
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
		"asset.currentRepoLogo": "current repo logo",
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
		"edit.noiseStrength": "Noise reduction strength",
		"edit.start": "Start",
		"edit.outputDuration": "Output duration",
		"edit.shortenSilence": "Shorten long silence",
		"edit.keepUncut": "Keep uncut draft video",
		"edit.minSilence": "Silence to shorten",
		"edit.keepSilence": "Silence to keep",
		"edit.noise": "Silence threshold",
		"option.current1MinColor": "Current 1-minute color-matched edit",
		"option.currentOnepass": "Current 1-minute quick edit",
		"option.current5Min": "Current 5-minute final edit",
		"option.newInterview": "New interview edit from selected media",
		"option.speakerAware": "Speaker-aware interview cuts",
		"option.manualPlan": "Use saved manual plan",
		"option.masterFirst": "Master first, close-ups for emphasis",
		"option.externalIfSelected": "Use external audio if selected",
		"option.masterAudio": "Use master video audio",
		"option.rightAudio": "Use right close-up audio",
		"option.leftAudio": "Use left close-up audio",
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
		"workflow.thumbnailLayout": "Thumbnail layout",
		"workflow.thumbnailMainColor": "Thumbnail main color",
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
		"workflow.verificationInput": "Input video to process",
		"workflow.audioReplaceSource": "Video containing replacement audio",
		"workflow.selectInputVideo": "Select input video",
		"workflow.selectAudioReplaceSource": "Select audio source video",
		"workflow.stillTime": "Still image time",
		"workflow.personSampleFps": "Person analysis detail",
		"workflow.yoloModel": "Person detection model",
		"workflow.personConfidence": "Person detection threshold",
		"workflow.analysisMaxSeconds": "Test analysis length",
		"workflow.videoLimit": "Videos to analyze",
		"workflow.rebuildBase": "Recreate the 1-minute base video",
		"workflow.reuseOverlays": "Use existing subtitle images",
		"workflow.reclassifySpeakers": "Re-detect speakers in the transcript",
		"workflow.autoContextCuts": "Cut automatically by subtitle context and speaker",
		"workflow.naturalDialogueCuts": "Prefer natural dialogue gaps for cuts",
		"workflow.retranscribeReview": "Re-transcribe subtitle review clips",
		"workflow.skipReviewAudioClips": "Skip audio clips during subtitle review",
		"workflow.reviewModel": "Subtitle review quality",
		"workflow.personNoMulticamRoot": "Analyze only selected project videos",
		"workflow.syncScore": "Sync score",
		"action.refresh": "Refresh",
		"option.renderSelected": "Create video from selected settings",
		"option.subtitleReview": "Review and fix subtitles",
		"option.generatePunchlines": "Create catchy subtitle images",
		"option.generateFullOverlays": "Create full subtitle images",
		"option.generateGlossaryOverlays": "Create glossary explanation images",
		"option.generateThumbnails": "Create thumbnail candidates",
		"option.analyzeBlocking": "Analyze camera framing",
		"option.analyzePersonEdit": "Analyze people for camera cuts",
		"option.analyzeReference": "Analyze reference video",
		"option.autoSyncDropped": "Sync selected camera files",
		"option.transcribeDropped": "Transcribe selected media",
		"option.transcribeAlign": "Sync using transcript",
		"option.compareAllCameras": "Compare camera transcripts",
		"option.refineStrongWave": "Improve audio sync",
		"option.buildBase": "Create multicam base video",
		"option.transcribeSound2": "Transcribe replacement audio",
		"option.compareSound2": "Compare replacement audio transcript",
		"option.refineSound2": "Fine-tune replacement audio sync",
		"option.replaceSound2": "Replace video audio",
		"option.shortenInput": "Shorten silence in selected video",
		"option.extractStill": "Save a still image",
		"option.verifyDuration": "Check output duration",
		"option.verifyAudio": "Check output audio",
		"option.thumbnailStandard": "Standard: image-by-image text placement",
		"option.thumbnailCloseup": "Center face: one-line bottom title",
		"option.thumbnailRightFace": "Face right: stacked title left",
		"option.thumbnailLeftFace": "Face left: stacked title right",
		"color.yellow": "Yellow",
		"color.red": "Red",
		"color.orange": "Orange",
		"color.green": "Green",
		"color.blue": "Blue",
		"color.cyan": "Cyan",
		"color.purple": "Purple",
		"color.pink": "Pink",
		"color.white": "White",
		"option.render1MinColor": "1-minute color matched edit",
		"option.render1MinOnepass": "1-minute quick edit",
		"option.render5MinOverlays": "5-minute final edit",
		"option.renderAppInterview": "Interview edit from selected media",
		"action.file": "File",
		"placeholder.all": "all",
		"codex.heading": "AI editing request",
		"codex.prompt": "Request text sent to AI",
		"codex.details": "Review request details",
		"codex.reviewBeforeRunning": "Review before running",
		"codex.directCommand": "Execution details",
		"action.refreshCommand": "Refresh execution details",
		"action.refreshPrompt": "Refresh request text",
		"action.interrupt": "Stop running job",
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
		"runLabel.thumbnail": "Thumbnail generation",
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
		"validation.thumbnailGenerate": "Generate thumbnail candidates using {mode} / {color}.",
		"validation.preview": "Preview: {path}",
		"validation.thumbnailImport": "Thumbnail candidates will be imported from the selected assets.",
		"validation.personBbox": "Person bbox: {path}",
		"validation.editPlan": "Edit plan: {path}",
		"validation.analysisFps": "Analysis interval: {fps} fps",
		"validation.selectedVideos": "Analysis target: {count} selected video(s)",
		"validation.sourceRoots": "Analysis target: source/video and 2cam/3cam root",
		"validation.testAnalysis": "A test analysis length is set, so only part of the video will be analyzed.",
		"validation.referenceRequired": "Drag and drop one reference video.",
		"validation.referenceShort": "Reference video is analyzed as under 60 seconds. Longer videos stop at run time.",
		"validation.referenceProfile": "Reference profile: {path}",
		"validation.referenceBbox": "Reference person bbox: {path}",
		"validation.referenceEditPlan": "Reference edit plan: {path}",
		"validation.replaceNeedsOutput": "Audio replacement requires an output path.",
		"validation.shortenNeedsInputOutput": "Silence shortening requires an input video and output path.",
		"validation.verificationNeedsInput": "Choose the video to process for this workflow.",
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
		"validation.silenceOn": "Silence shortening: ON",
		"validation.silenceOff": "Silence shortening: OFF",
		"validation.previousSync": "Previous sync: {role} score {score}",
		"validation.lowSyncScore": "Some previous auto-sync scores are low. Check audio drift with a short QA render.",
		"notification.renderComplete": "Render complete.",
		"notification.analysisComplete": "Asset analysis, transcription, and OpenCV analysis are complete.",
		"notification.analysisCompleteCheck": "Analysis is complete. Check the partial results.",
		"log.projectNotSelected": "No project is selected",
		"log.cannotDeleteDuringIngest": "Cannot delete while asset analysis is running",
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
	renderSyncReport();
	renderOutputPreview();
	updateRunSummary();
	refreshCommand();
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

function outputPreviewTarget(kind = state.outputPreviewKind) {
	if (kind === "thumbnails") {
		return thumbnailContactSheetPath();
	}
	return $("#outputPath")?.value?.trim() || activeOutputRoot();
}

function outputPreviewTitle(kind = state.outputPreviewKind) {
	if (kind === "thumbnails") {
		return t("preview.thumbnailsTitle");
	}
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
	return state.env?.videoEditRoot ? joinPath(state.env.videoEditRoot, "source") : "";
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
	const sendButton = $("#sendRequest");
	if (runButton) {
		runButton.disabled = running;
		runButton.textContent = running
			? t("format.runningButton", { label: label || t("runLabel.run") })
			: t("action.runPresetScript");
	}
	if (sendButton) {
		sendButton.disabled = running;
	}
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
	applySuggestedTitle(titleFromSources(selected));
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

function titleFromSources(paths: string[]) {
	if (!paths.length) {
		return "";
	}
	const source = paths[0];
	const parts = String(source).split(/[\\/]/).filter(Boolean);
	const name = parts.at(-1) || "";
	return name
		.replace(/\.[^.\\/]+$/, "")
		.replace(/[_-]+/g, " ")
		.trim();
}

function shouldReplaceTitleWithSuggestion() {
	const current = String(formValue("titleText") || "").trim();
	return !current || current === LEGACY_DEFAULT_TITLE;
}

function applySuggestedTitle(title: string) {
	const input = $("#titleText");
	const nextTitle = String(title || "").trim();
	if (!input || !nextTitle || !shouldReplaceTitleWithSuggestion()) {
		return;
	}
	input.value = nextTitle;
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
		label.textContent = project ? t("project.ready", { name: project.name }) : t("project.noProjectSelected");
	}
	const preview = $("#projectNamePreview");
	if (preview) {
		preview.textContent = project ? project.name : t("project.noProjectSelected");
	}
	const videoSourceRoot = activeProjectVideoSourceRoot();
	const sourceRootInput = $("#sourceRoot");
	if (sourceRootInput && videoSourceRoot) {
		sourceRootInput.value = videoSourceRoot;
	}
	if (project?.name) {
		applySuggestedTitle(project.name);
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
	["inputVideoPath", "replaceAudioInput"].forEach(renderWorkflowMediaPreview);
}

function loadWorkflowMediaPreviews() {
	const paths = ["inputVideoPath", "replaceAudioInput"].map((id) => String($(`#${id}`)?.value || "")).filter(Boolean);
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
			glossaryTerms: state.glossaryTerms,
			language: state.language,
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
			loadWorkflowMediaPreviews();
			loadOutputTargetPreview();
			applySuggestedTitle(titleFromSources(state.materialPaths) || state.project?.name || "");
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
		if (id === "inputVideoPath" || id === "replaceAudioInput") {
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
		log("project ready", { id: project.id, root: project.root });
	} catch (error) {
		log("project create failed", { message: error.message });
	}
}

async function changeProject() {
	try {
		const result = await editApp.pickProject({ language: state.language });
		if (!result?.project) {
			log("project switch canceled");
			return;
		}
		setProject(result.project);
		clearSelectedAssets();
		setMediaManifest(result.manifest || null);
		await refreshTextOverlayFromAnalysis(result.manifest || null);
		if (!result.manifest) {
			setIngestProgress({
				progress: 0,
				message: t("materials.folderNotAnalyzed"),
				path: "",
			});
		}
		log("project switched", {
			id: result.project.id,
			root: result.project.root,
			manifest: result.manifest?.manifestPath || null,
		});
		await refreshSyncReport();
	} catch (error) {
		log("project switch failed", { message: error.message });
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
		setIngestProgress({
			progress: 0,
			message: t("progress.waitingAnalysis"),
			path: "",
		});
		if (state.env?.knownOutputs?.[0]) {
			$("#outputPath").value = state.env.knownOutputs[0];
			loadOutputTargetPreview();
		}
		const sourceRootInput = $("#sourceRoot");
		if (sourceRootInput && state.env?.videoEditRoot) {
			sourceRootInput.value = joinPath(state.env.videoEditRoot, "source");
		}
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
			await runAnalysisAction(
				"transcribe-dropped",
				t("analysis.transcription"),
				0.58,
				joinPath(activeOutputRoot(), "transcripts", "manifest_sources", "manifest_transcripts.json"),
			),
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
			await runAnalysisAction("analyze-person-edit-metadata", t("analysis.personOpenCv"), 0.78, personEditPlansDir()),
		);
		checks.push(
			await runAnalysisAction(
				"analyze-blocking",
				t("analysis.blockingOpenCv"),
				0.9,
				joinPath(activeOutputRoot(), "diagnostics", "opencv_blocking_analysis", "clip_metrics.json"),
			),
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
		return true;
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

function thumbnailMode() {
	const mode = formValue("thumbnailMode") || "standard";
	return mode in thumbnailModes ? mode : "standard";
}

function thumbnailModeConfig() {
	return thumbnailModes[thumbnailMode()];
}

function thumbnailModeLabel() {
	return t(thumbnailModeConfig().labelKey);
}

function thumbnailMainColor() {
	const color = formValue("thumbnailMainColor") || "yellow";
	return color in thumbnailMainColors ? color : "yellow";
}

function thumbnailMainColorLabel() {
	return t(thumbnailMainColors[thumbnailMainColor()]);
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
		"text-overlays": "analysis.subtitleUi",
		"analyze-person-edit-metadata": "analysis.personOpenCv",
		"analyze-blocking": "analysis.blockingOpenCv",
		"analyze-reference-video": "analysis.referenceVideo",
	};
	return labels[key] ? t(labels[key]) : localizePlainText(fallback || key);
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
		const punchlineInput = $("#punchlineText");
		if (punchlineInput) {
			punchlineInput.value = result?.punchlineText || "";
		}
		setGlossaryTerms(Array.isArray(result?.glossaryTerms) ? result.glossaryTerms : []);
		log("text overlays refreshed", {
			subtitle: result?.subtitlePath || null,
			captions: result?.captionCount || 0,
			glossary: result?.glossaryTerms?.length || 0,
		});
		refreshPrompt();
		return result;
	} catch (error) {
		log("text overlay refresh failed", { message: error.message });
		return null;
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

function sourceRootOverride() {
	return formValue("sourceRoot");
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
	if (action === "generate-thumbnails") {
		return t("runLabel.thumbnail");
	}
	if (action === "auto-sync-dropped") {
		return t("runLabel.sync");
	}
	if (action.startsWith("transcribe")) {
		return t("runLabel.transcribe");
	}
	if (action.startsWith("analyze-")) {
		return t("runLabel.analyze");
	}
	return selectedLabel("workflowAction") || t("runLabel.run");
}

function directRunOutputPath(action: string) {
	if (action === "generate-thumbnails") {
		return thumbnailContactSheetPath();
	}
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
	if (action === "transcribe-sound2") {
		return joinPath(activeOutputRoot() || "output", "transcripts", "sound2");
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

	if (action === "generate-thumbnails") {
		ok.push(t("validation.thumbnailGenerate", { mode: thumbnailModeLabel(), color: thumbnailMainColorLabel() }));
		ok.push(t("validation.preview", { path: shortPath(thumbnailContactSheetPath()) }));
		ok.push(t("validation.thumbnailImport"));
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

	if (action === "replace-sound2" && !outputPath) {
		errors.push(t("validation.replaceNeedsOutput"));
	}
	if (action === "shorten-input" && (!inputVideo || !outputPath)) {
		errors.push(t("validation.shortenNeedsInputOutput"));
	}
	if (["extract-still", "verify-duration", "verify-audio"].includes(action) && !inputVideo) {
		errors.push(t("validation.verificationNeedsInput"));
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
		"- Read docs\\video_edit_method.md for the current ST7_7550 workflow.",
		"- Prefer scripts\\render_1min_onepass_ffmpeg.py for the current 1-minute preset.",
		"- Prefer scripts\\render_final_png_overlays.py for current 5-minute PNG-overlay renders.",
		"- Use scripts\\analyze_person_edit_metadata.py before edit planning when person position/crop decisions matter.",
		"- If a reference video is selected, analyze it first and use output\\reports\\reference_edit_profile.json as the style/layout target.",
		"- Treat the material directory as cameras/audio/images/logo/subtitles only; reference video is selected separately.",
		"- Use scripts\\generate_thumbnail_candidates.py --import-assets --main-color <color> plus the selected thumbnail layout flag for thumbnail candidate generation.",
		"- Keep existing user changes in the repo; do not revert unrelated files.",
		"",
		"Operator selections:",
		`- Edit preset: ${formValue("editPreset")}`,
		`- Direct workflow action: ${formValue("workflowAction")}`,
		`- Transcribe settings: model ${formValue("transcribeModel") || "large-v3"}, language ${formValue("transcribeLanguage") || "ja"}, beam ${formValue("transcribeBeamSize") || "5"}, temperature ${formValue("transcribeTemperature") || "0"}, loudnorm ${formValue("transcribeNormalizeAudio")}, low-confidence filter ${formValue("transcribeFilterLowConfidence")}, previous-text context ${formValue("conditionOnPreviousText")}`,
		`- Transcribe prompt terms: ${formValue("transcribePromptTerms") || "(use glossary terms only)"}`,
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
		"- Regenerate text overlays from current analysis: true",
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
		`- Thumbnail source images: ${joinPath(thumbnailSourceRoot(), "ST-*.jpg")}`,
		`- Thumbnail contact sheet: ${thumbnailContactSheetPath()}`,
		`- Person bbox output: ${personBboxesDir()}`,
		`- Person edit plan output: ${personEditPlansDir()}`,
		`- Reference person edit plan output: ${referenceEditPlansDir()}`,
		`- Python: ${pythonExe()}`,
		`- FFmpeg: ${ffmpegExe()}`,
		`- FFprobe: ${ffprobeExe()}`,
		"",
		"Dropped assets:",
		`- Master/day video: ${state.files.masterVideo || "(use current repo default if preset supports it)"}`,
		`- Right close-up/person 1: ${state.files.rightCloseVideo || "(use current repo default if preset supports it)"}`,
		`- Left close-up/person 2: ${state.files.leftCloseVideo || "(use current repo default if preset supports it)"}`,
		`- Reference style video: ${state.files.referenceVideo || "(not selected)"}`,
		`- External audio: ${state.files.externalAudio || "(not selected)"}`,
		`- Logo: ${state.files.logo || "(use current repo logo)"}`,
		`- Still image inserts: ${state.files.stillImages.length ? state.files.stillImages.join(", ") : "(none)"}`,
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
		"- Prefer the media manifest for source roles. Support variable interview/multicam camera roles: master, camera2, camera3, camera4+.",
		"- The old master/right/left dropped slots are compatibility fields only when a media manifest is not present.",
		"- For person-aware crop/cut planning, analyze source videos first, then use output\\reports\\person_edit_plans as metadata for camera/crop decisions.",
		"- Reflect the reference profile in the edit: match person size, layout, face direction when possible, and visual tone (brightness, contrast, saturation, warmth).",
		"- For full subtitles, use corrected SRT when available.",
		"- For catchy subtitles, use the punchline overlay mode.",
		"- If punchline text/timing/style changed, update the relevant generator script or data in the smallest maintainable way before regenerating overlays.",
		"- If style/logo/title settings are not exposed by CLI flags, update the Python style/title scripts carefully and regenerate PNG overlays.",
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
			sourceRoot: sourceRootOverride(),
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
			skipSubtitleRegeneration: false,
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
			reviewModel: formValue("reviewModel") || "large-v3",
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
			python: pythonExe(),
			ffmpeg: ffmpegExe(),
			ffprobe: ffprobeExe(),
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
		if (action === "generate-thumbnails" && result?.exitCode === 0) {
			log("thumbnail contact sheet", { path: thumbnailContactSheetPath() });
		}
		if (action === "analyze-person-edit-metadata" && result?.exitCode === 0) {
			log("person analysis outputs", { bboxes: personBboxesDir(), plans: personEditPlansDir() });
		}
		if (action === "analyze-reference-video" && result?.exitCode === 0) {
			log("reference analysis output", { profile: referenceEditProfilePath() });
		}
		const ok = result?.exitCode === 0;
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
	setStatus(t("status.codexRunning"), "busy");
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
		setStatus(t("status.codexError"), "idle");
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
		setStatus(t("status.codexIdle"), "ready");
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
	$("#refreshSyncReport").addEventListener("click", refreshSyncReport);
	$("#loadGlossaryCandidates").addEventListener("click", loadGlossaryCandidates);
	$("#addGlossaryTerm").addEventListener("click", addGlossaryTerm);
	$("#runPreset").addEventListener("click", runPreset);
	$("#sendRequest").addEventListener("click", sendRequest);
	$("#interrupt").addEventListener("click", async () => {
		await editApp.interruptCodex();
		log("turn/interrupt requested");
	});
	$("#openOutput").addEventListener("click", () => loadOutputPreview("output"));
	$("#openThumbnails").addEventListener("click", () => loadOutputPreview("thumbnails"));
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
			setActiveSection(button.dataset.section);
			window.scrollTo({ top: 0, behavior: "smooth" });
		});
	});
}

async function init() {
	state.env = await editApp.getEnvironment();
	renderWorkspaceLabel();
	$("#outputPath").value = state.env.knownOutputs[0];
	$("#inputVideoPath").value = state.env.knownOutputs[0];
	$("#replaceAudioInput").value = state.env.knownOutputs[2];
	loadWorkflowMediaPreviews();
	loadOutputTargetPreview();
	const pythonPathInput = $("#pythonPath");
	if (pythonPathInput) {
		pythonPathInput.value = state.env.pythonExe;
	}
	const sourceRootInput = $("#sourceRoot");
	if (sourceRootInput) {
		sourceRootInput.value = joinPath(state.env.videoEditRoot, "source");
	}
	$("#punchlineText").value = defaultPunchlines;
	state.glossaryTerms = defaultGlossaryTerms;
	loadState();
	renderGlossaryList();
	renderMediaManifest();
	initDropZones();
	bindEvents();
	applyTranslations();
	setActiveSection(state.activeSection);
	setStatus(state.statusText, state.statusKind);
	refreshPrompt();

	editApp.onServerReady(() => {
		setStatus(t("status.codexReady"), "ready");
		log("server ready");
	});
	editApp.onServerError((payload) => {
		setStatus(t("status.codexError"), "idle");
		log("server error", payload);
	});
	editApp.onServerExit((payload) => {
		setStatus(t("status.codexExited"), "idle");
		log("server exit", payload);
	});
	editApp.onServerStderr((payload) => log("stderr", payload));
	editApp.onServerNotification(handleNotification);
	editApp.onWorkflowProgress(handleWorkflowProgress);
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
}

init().catch((error) => {
	log("init error", { message: error.message });
});
