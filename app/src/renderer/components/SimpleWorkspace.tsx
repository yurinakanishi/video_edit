import { FileAudio, FileText, FolderOpen, Images, Play, Radio, RefreshCw, Send, Upload, Video } from "lucide-react";
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
import { cn } from "../lib/utils.js";
import { shortPath } from "../preview.js";
import { useAppStore } from "../store/app-store.js";
import { MaterialIngestProgress } from "./MaterialIngestProgress.js";
import { OutputPreview } from "./OutputPreview.js";
import { Badge } from "./ui/badge.js";
import { Button } from "./ui/button.js";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./ui/card.js";
import { Textarea } from "./ui/textarea.js";

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
		<div className="grid grid-cols-2 gap-2 xl:grid-cols-3">
			<SummaryTile label="Project" value={project?.name || "-"} title={project?.root || ""} />
			<SummaryTile label="Files" value={fileCount} />
			<SummaryTile label="Video" value={videoCount} />
			<SummaryTile label="Audio" value={audioCount} />
			<SummaryTile label="Images" value={imageCount} />
			<SummaryTile label="Subtitles" value={subtitleCount} />
		</div>
	);
}

function SummaryTile({
	label,
	value,
	title,
}: {
	readonly label: string;
	readonly value: string | number;
	readonly title?: string;
}) {
	return (
		<div className="min-w-0 rounded-md border border-border bg-muted/45 px-3 py-2">
			<span className="block text-[11px] font-semibold uppercase tracking-normal text-muted-foreground">{label}</span>
			<strong className="block truncate text-sm text-foreground" title={title || String(value)}>
				{value}
			</strong>
		</div>
	);
}

function DropIcon() {
	return (
		<span
			className="grid size-12 shrink-0 place-items-center rounded-full border border-primary/25 bg-accent text-accent-foreground"
			aria-hidden="true"
		>
			<Upload className="size-5" />
		</span>
	);
}

function DropZone({
	compact,
	dragging,
	title,
	subtitle,
	dragProps,
}: {
	readonly compact?: boolean;
	readonly dragging: boolean;
	readonly title: string;
	readonly subtitle: string;
	readonly dragProps: Record<string, unknown>;
}) {
	return (
		<div
			className={cn(
				"drop-reactive grid grid-cols-[48px_minmax(0,1fr)] items-center gap-3 rounded-lg border border-dashed border-primary/35 bg-accent/45 p-4 transition",
				compact ? "min-h-32" : "min-h-44",
				dragging && "border-primary bg-accent shadow-[0_0_0_3px_hsl(174_70%_28%_/_0.14)]",
			)}
			{...dragProps}
		>
			<DropIcon />
			<div className="min-w-0">
				<strong className="block text-base font-semibold text-accent-foreground">{title}</strong>
				<span className="text-xs font-medium text-muted-foreground">{subtitle}</span>
			</div>
		</div>
	);
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
		<Card>
			<CardHeader className="flex-row items-start justify-between gap-3 space-y-0">
				<div>
					<CardTitle className="flex items-center gap-2">
						<Images className="size-5 text-primary" aria-hidden="true" />
						素材
					</CardTitle>
					<CardDescription>Files / folders</CardDescription>
				</div>
				<div className="flex flex-wrap justify-end gap-2">
					<Button
						type="button"
						variant="outline"
						size="sm"
						disabled={disabled}
						onClick={() => dispatchSimpleAction(SIMPLE_MATERIAL_PICK_FILES_EVENT)}
					>
						<FileText className="size-4" aria-hidden="true" />
						ファイル
					</Button>
					<Button
						type="button"
						variant="outline"
						size="sm"
						disabled={disabled}
						onClick={() => dispatchSimpleAction(SIMPLE_MATERIAL_PICK_DIRECTORY_EVENT)}
					>
						<FolderOpen className="size-4" aria-hidden="true" />
						フォルダ
					</Button>
				</div>
			</CardHeader>
			<CardContent className="grid gap-4">
				<DropZone
					dragging={dropTarget.dragging}
					dragProps={dropTarget.dragProps}
					title="Drop source media"
					subtitle="new project / source"
				/>
				<MaterialSummary />
				<MaterialIngestProgress />
				{manifestPath ? (
					<Button
						type="button"
						variant="ghost"
						size="sm"
						className="w-fit max-w-full justify-start truncate px-2 text-accent-foreground"
						title={manifestPath}
						onClick={() => dispatchSimpleAction(OUTPUT_PREVIEW_ENTRY_OPEN_EVENT, { path: manifestPath })}
					>
						<FileText className="size-4 shrink-0" aria-hidden="true" />
						<span className="truncate">{shortPath(manifestPath)}</span>
					</Button>
				) : null}
			</CardContent>
		</Card>
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
		<Card>
			<CardHeader className="flex-row items-start justify-between gap-3 space-y-0">
				<div>
					<CardTitle className="flex items-center gap-2">
						<FileAudio className="size-5 text-primary" aria-hidden="true" />
						音声
					</CardTitle>
					<CardDescription>Audio / transcription</CardDescription>
				</div>
				<Button
					type="button"
					variant="outline"
					size="sm"
					disabled={disabled}
					onClick={() => dispatchSimpleAction(SIMPLE_AUDIO_PICK_EVENT)}
				>
					<FileAudio className="size-4" aria-hidden="true" />
					音声ファイル
				</Button>
			</CardHeader>
			<CardContent className="grid gap-4">
				<DropZone
					compact
					dragging={dropTarget.dragging}
					dragProps={dropTarget.dragProps}
					title="Drop audio"
					subtitle={audioCount ? `${audioCount} audio file(s)` : "optional"}
				/>
				<Button
					type="button"
					className="w-full"
					disabled={!canTranscribe}
					onClick={() => dispatchSimpleAction(SIMPLE_TRANSCRIBE_EVENT)}
				>
					<Radio className="size-4" aria-hidden="true" />
					文字起こし
				</Button>
			</CardContent>
		</Card>
	);
}

function InstructionHistory() {
	const history = useAppStore((store) => store.editRequest.instructionHistory);
	if (!history.length) {
		return (
			<div className="grid min-h-24 place-items-center rounded-md border border-dashed border-border bg-muted/30 text-sm text-muted-foreground">
				No requests yet
			</div>
		);
	}
	return (
		<div className="grid max-h-56 gap-2 overflow-auto rounded-md border border-border bg-muted/35 p-2">
			{history.slice(-6).map((item) => (
				<div key={item.id} className="grid gap-1 rounded-md border border-border bg-card p-3">
					<Badge variant={item.mode === "final" ? "default" : "secondary"} className="w-fit">
						{item.mode === "final" ? "Final" : "Preview"}
					</Badge>
					<p className="text-sm leading-relaxed text-foreground">{item.text}</p>
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
		<Card className="min-h-[420px]">
			<CardHeader>
				<CardTitle className="flex items-center gap-2">
					<Send className="size-5 text-primary" aria-hidden="true" />
					編集指示
				</CardTitle>
				<CardDescription>Natural language</CardDescription>
			</CardHeader>
			<CardContent className="grid gap-4">
				<Textarea
					className="min-h-52 resize-y text-sm leading-relaxed"
					value={draft}
					disabled={appLocked || codexTurnRunning}
					placeholder="例: 会話のテンポをよくして、重要な発言に字幕を入れ、冒頭30秒のプレビューを作成してください。"
					onChange={(event) =>
						dispatchSimpleAction(EDIT_REQUEST_CHANGE_EVENT, { instructionDraft: event.currentTarget.value })
					}
				/>
				<div className="flex flex-wrap gap-2">
					<Button
						type="button"
						disabled={!canSend || directRunRunning}
						onClick={() => dispatchSimpleAction(SIMPLE_PREVIEW_REQUEST_EVENT)}
					>
						<Play className="size-4" aria-hidden="true" />
						プレビューを作成
					</Button>
					<Button
						type="button"
						variant="outline"
						disabled={!canSend || directRunRunning}
						onClick={() => dispatchSimpleAction(SIMPLE_FINAL_RENDER_EVENT)}
					>
						<Video className="size-4" aria-hidden="true" />
						フルレンダリング
					</Button>
				</div>
				<InstructionHistory />
			</CardContent>
		</Card>
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
		<pre
			id="eventLog"
			ref={eventLogRef}
			className="max-h-72 min-h-44 overflow-auto rounded-b-lg border-t border-border bg-slate-950 p-4 font-mono text-xs leading-relaxed text-slate-100"
		>
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
		<div className="grid gap-3 md:grid-cols-2">
			{paths.map((item) => (
				<Button
					type="button"
					key={item.label}
					variant="outline"
					className="h-auto min-w-0 justify-start px-4 py-3 text-left"
					title={item.path}
					onClick={() => dispatchSimpleAction(OUTPUT_PREVIEW_ENTRY_OPEN_EVENT, { path: item.path })}
				>
					<RefreshCw className="size-4 shrink-0 text-primary" aria-hidden="true" />
					<span className="grid min-w-0 gap-0.5">
						<span className="text-[11px] font-semibold uppercase tracking-normal text-muted-foreground">
							{item.label}
						</span>
						<strong className="truncate text-sm text-accent-foreground">{shortPath(item.path)}</strong>
					</span>
				</Button>
			))}
		</div>
	);
}

export function SimpleWorkspace() {
	return (
		<main className="grid min-w-0 gap-4 p-4 md:p-6">
			<OutputPreview />
			<div className="grid items-start gap-4 xl:grid-cols-[minmax(280px,0.9fr)_minmax(240px,0.62fr)_minmax(360px,1.35fr)]">
				<MaterialsCard />
				<AudioCard />
				<InstructionCard />
			</div>
			<OutputLinks />
			<Card className="overflow-hidden">
				<CardHeader>
					<CardTitle>進行状況</CardTitle>
					<CardDescription>Log</CardDescription>
				</CardHeader>
				<EventLog />
			</Card>
		</main>
	);
}
