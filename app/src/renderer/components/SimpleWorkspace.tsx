import type { DragEvent } from "react";
import { useEffect, useRef, useState } from "react";
import {
	EDIT_REQUEST_CHANGE_EVENT,
	OUTPUT_PREVIEW_ENTRY_OPEN_EVENT,
	SIMPLE_AUDIO_DROP_EVENT,
	SIMPLE_AUDIO_PICK_EVENT,
	SIMPLE_FINAL_RENDER_EVENT,
	SIMPLE_MATERIAL_DROP_EVENT,
	SIMPLE_MATERIAL_PICK_DIRECTORY_EVENT,
	SIMPLE_MATERIAL_PICK_FILES_EVENT,
	SIMPLE_PREVIEW_REQUEST_EVENT,
	SIMPLE_TRANSCRIBE_EVENT,
} from "../events.js";
import { shortPath } from "../preview.js";
import { useAppStore } from "../store/app-store.js";
import { MaterialIngestProgress } from "./MaterialIngestProgress.js";
import { OutputPreview } from "./OutputPreview.js";

type DropTargetOptions = {
	readonly onDrop: (files: File[]) => void;
};

function dispatchSimpleAction(eventName: string, detail?: Record<string, unknown>) {
	document.dispatchEvent(new CustomEvent(eventName, { detail }));
}

function isFileDragEvent(event: DragEvent<HTMLElement>) {
	return Array.from(event.dataTransfer.types || []).includes("Files");
}

function useSimpleDropTarget({ onDrop }: DropTargetOptions) {
	const [dragging, setDragging] = useState(false);
	return {
		dragging,
		dragProps: {
			onDragEnter: (event: DragEvent<HTMLElement>) => {
				if (!isFileDragEvent(event)) {
					return;
				}
				event.preventDefault();
				event.stopPropagation();
				event.dataTransfer.dropEffect = "copy";
				setDragging(true);
			},
			onDragOver: (event: DragEvent<HTMLElement>) => {
				if (!isFileDragEvent(event)) {
					return;
				}
				event.preventDefault();
				event.stopPropagation();
				event.dataTransfer.dropEffect = "copy";
				setDragging(true);
			},
			onDragLeave: (event: DragEvent<HTMLElement>) => {
				if (!isFileDragEvent(event)) {
					return;
				}
				event.stopPropagation();
				const nextTarget = event.relatedTarget as Node | null;
				if (!nextTarget || !event.currentTarget.contains(nextTarget)) {
					setDragging(false);
				}
			},
			onDrop: (event: DragEvent<HTMLElement>) => {
				if (!isFileDragEvent(event)) {
					return;
				}
				event.preventDefault();
				event.stopPropagation();
				setDragging(false);
				onDrop(Array.from(event.dataTransfer.files || []) as File[]);
			},
		},
	};
}

function countByKind(mediaManifest: any | null, kind: string) {
	return Array.isArray(mediaManifest?.files)
		? mediaManifest.files.filter((item: any) => String(item?.kind || "") === kind).length
		: 0;
}

function MaterialSummary() {
	const project = useAppStore((store) => store.project);
	const mediaManifest = useAppStore((store) => store.mediaManifest);
	const fileCount = Array.isArray(mediaManifest?.files) ? mediaManifest.files.length : 0;
	const videoCount = countByKind(mediaManifest, "video");
	const audioCount = countByKind(mediaManifest, "audio");
	const imageCount = countByKind(mediaManifest, "image");
	const subtitleCount = countByKind(mediaManifest, "subtitle");

	return (
		<div className="simple-summary">
			<div>
				<span>Project</span>
				<strong title={project?.root || ""}>{project?.name || "-"}</strong>
			</div>
			<div>
				<span>Files</span>
				<strong>{fileCount}</strong>
			</div>
			<div>
				<span>Video</span>
				<strong>{videoCount}</strong>
			</div>
			<div>
				<span>Audio</span>
				<strong>{audioCount}</strong>
			</div>
			<div>
				<span>Images</span>
				<strong>{imageCount}</strong>
			</div>
			<div>
				<span>Subtitles</span>
				<strong>{subtitleCount}</strong>
			</div>
		</div>
	);
}

function DropIcon() {
	return <span className="simple-drop-icon" aria-hidden="true"></span>;
}

function MaterialsCard() {
	const appLocked = useAppStore((store) => store.appLocked);
	const ingestRunning = useAppStore((store) => store.ingestRunning);
	const mediaManifest = useAppStore((store) => store.mediaManifest);
	const dropTarget = useSimpleDropTarget({
		onDrop: (files) => dispatchSimpleAction(SIMPLE_MATERIAL_DROP_EVENT, { files }),
	});
	const disabled = appLocked || ingestRunning;
	const manifestPath = mediaManifest?.manifestPath || "";

	return (
		<section className="simple-panel simple-materials">
			<div className="simple-panel-heading">
				<div>
					<h2>素材</h2>
					<p>Files / folders</p>
				</div>
				<div className="simple-actions">
					<button
						type="button"
						disabled={disabled}
						onClick={() => dispatchSimpleAction(SIMPLE_MATERIAL_PICK_FILES_EVENT)}
					>
						ファイル
					</button>
					<button
						type="button"
						disabled={disabled}
						onClick={() => dispatchSimpleAction(SIMPLE_MATERIAL_PICK_DIRECTORY_EVENT)}
					>
						フォルダ
					</button>
				</div>
			</div>
			<div className={`simple-drop-zone${dropTarget.dragging ? " dragging" : ""}`} {...dropTarget.dragProps}>
				<DropIcon />
				<div>
					<strong>Drop source media</strong>
					<span>new project / source</span>
				</div>
			</div>
			<MaterialSummary />
			<MaterialIngestProgress />
			{manifestPath ? (
				<button
					type="button"
					className="simple-path-button"
					title={manifestPath}
					onClick={() => dispatchSimpleAction(OUTPUT_PREVIEW_ENTRY_OPEN_EVENT, { path: manifestPath })}
				>
					{shortPath(manifestPath)}
				</button>
			) : null}
		</section>
	);
}

function AudioCard() {
	const project = useAppStore((store) => store.project);
	const mediaManifest = useAppStore((store) => store.mediaManifest);
	const appLocked = useAppStore((store) => store.appLocked);
	const ingestRunning = useAppStore((store) => store.ingestRunning);
	const directRunRunning = useAppStore((store) => store.directRunRunning);
	const audioCount = countByKind(mediaManifest, "audio");
	const timeSourceCount = Array.isArray(mediaManifest?.files)
		? mediaManifest.files.filter((item: any) => ["audio", "video"].includes(String(item?.kind || ""))).length
		: 0;
	const dropTarget = useSimpleDropTarget({
		onDrop: (files) => dispatchSimpleAction(SIMPLE_AUDIO_DROP_EVENT, { files }),
	});
	const disabled = appLocked || ingestRunning || !project;
	const canTranscribe = Boolean(project && timeSourceCount && !appLocked && !ingestRunning && !directRunRunning);

	return (
		<section className="simple-panel">
			<div className="simple-panel-heading">
				<div>
					<h2>音声</h2>
					<p>Audio / transcription</p>
				</div>
				<button type="button" disabled={disabled} onClick={() => dispatchSimpleAction(SIMPLE_AUDIO_PICK_EVENT)}>
					音声ファイル
				</button>
			</div>
			<div className={`simple-drop-zone compact${dropTarget.dragging ? " dragging" : ""}`} {...dropTarget.dragProps}>
				<DropIcon />
				<div>
					<strong>Drop audio</strong>
					<span>{audioCount ? `${audioCount} audio file(s)` : "optional"}</span>
				</div>
			</div>
			<button
				type="button"
				className="primary-button simple-full-width"
				disabled={!canTranscribe}
				onClick={() => dispatchSimpleAction(SIMPLE_TRANSCRIBE_EVENT)}
			>
				文字起こし
			</button>
		</section>
	);
}

function InstructionHistory() {
	const history = useAppStore((store) => store.editRequest.instructionHistory);
	if (!history.length) {
		return <div className="simple-history-empty">No requests yet</div>;
	}
	return (
		<div className="simple-history">
			{history.slice(-6).map((item) => (
				<div key={item.id} className="simple-history-item">
					<span>{item.mode === "final" ? "Final" : "Preview"}</span>
					<p>{item.text}</p>
				</div>
			))}
		</div>
	);
}

function InstructionCard() {
	const appLocked = useAppStore((store) => store.appLocked);
	const codexTurnRunning = useAppStore((store) => store.codexTurnRunning);
	const directRunRunning = useAppStore((store) => store.directRunRunning);
	const project = useAppStore((store) => store.project);
	const mediaManifest = useAppStore((store) => store.mediaManifest);
	const draft = useAppStore((store) => store.editRequest.instructionDraft);
	const history = useAppStore((store) => store.editRequest.instructionHistory);
	const hasInstruction = Boolean(draft.trim() || history.length);
	const canSend = Boolean(project && mediaManifest?.files?.length && hasInstruction && !appLocked && !codexTurnRunning);

	return (
		<section className="simple-panel simple-instructions">
			<div className="simple-panel-heading">
				<div>
					<h2>編集指示</h2>
					<p>Natural language</p>
				</div>
			</div>
			<textarea
				className="simple-instruction-input"
				value={draft}
				disabled={appLocked || codexTurnRunning}
				placeholder="例: 会話のテンポをよくして、重要な発言に字幕を入れ、冒頭30秒のプレビューを作成してください。"
				onChange={(event) =>
					dispatchSimpleAction(EDIT_REQUEST_CHANGE_EVENT, { instructionDraft: event.currentTarget.value })
				}
			></textarea>
			<div className="simple-run-actions">
				<button
					type="button"
					className="primary-button"
					disabled={!canSend || directRunRunning}
					onClick={() => dispatchSimpleAction(SIMPLE_PREVIEW_REQUEST_EVENT)}
				>
					プレビューを作成
				</button>
				<button
					type="button"
					disabled={!canSend || directRunRunning}
					onClick={() => dispatchSimpleAction(SIMPLE_FINAL_RENDER_EVENT)}
				>
					フルレンダリング
				</button>
			</div>
			<InstructionHistory />
		</section>
	);
}

function EventLog() {
	const eventLogLines = useAppStore((store) => store.eventLogLines);
	const eventLogRef = useRef<HTMLPreElement | null>(null);
	const text = eventLogLines.length ? `${eventLogLines.join("\n")}\n` : "";

	useEffect(() => {
		const element = eventLogRef.current;
		if (element) {
			element.scrollTop = element.scrollHeight;
		}
	});

	return (
		<pre id="eventLog" ref={eventLogRef}>
			{text}
		</pre>
	);
}

function OutputLinks() {
	const lastPreviewPath = useAppStore((store) => store.editRequest.lastPreviewPath);
	const lastFinalPath = useAppStore((store) => store.editRequest.lastFinalPath);
	const paths = [
		{ label: "Latest preview", path: lastPreviewPath },
		{ label: "Latest final", path: lastFinalPath },
	].filter((item) => item.path);

	if (!paths.length) {
		return null;
	}

	return (
		<div className="simple-output-links">
			{paths.map((item) => (
				<button
					type="button"
					key={item.label}
					title={item.path}
					onClick={() => dispatchSimpleAction(OUTPUT_PREVIEW_ENTRY_OPEN_EVENT, { path: item.path })}
				>
					<span>{item.label}</span>
					<strong>{shortPath(item.path)}</strong>
				</button>
			))}
		</div>
	);
}

export function SimpleWorkspace() {
	return (
		<main className="simple-workspace">
			<OutputPreview />
			<div className="simple-grid">
				<MaterialsCard />
				<AudioCard />
				<InstructionCard />
			</div>
			<OutputLinks />
			<section className="simple-panel simple-log-panel">
				<div className="simple-panel-heading">
					<div>
						<h2>進行状況</h2>
						<p>Log</p>
					</div>
				</div>
				<EventLog />
			</section>
		</main>
	);
}
