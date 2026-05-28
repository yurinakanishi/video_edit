export type Unsubscribe = () => void;

export type EditAppApi = {
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
	saveMediaManifest: (payload: any) => Promise<MediaManifest>;
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

export type ProjectInfo = {
	id: string;
	name: string;
	root: string;
	sourceRoot: string;
	outputRoot: string;
};

export type ProjectListEntry = {
	project: ProjectInfo;
	updatedAt: string;
	lastModifiedAt: string;
	hasManifest: boolean;
	manifestPath: string;
	mediaCount: number;
};

export type MediaItem = {
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

export type MediaManifest = {
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

export type Locale = "ja" | "en";
export type AnalysisResult = { key: string; label: string; status: string; detail: string; path?: string };
export type CodexModel = {
	id: string;
	model: string;
	displayName: string;
	defaultReasoningEffort?: string;
	isDefault?: boolean;
	hidden?: boolean;
};

export type GlossaryTerm = {
	label: string;
	description: string;
	patterns: string;
	enabled: boolean;
};
