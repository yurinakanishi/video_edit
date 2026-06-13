import {
	Clock,
	FileAudio,
	FileText,
	FolderOpen,
	Images,
	Play,
	Radio,
	RefreshCw,
	Send,
	Upload,
	Video,
} from "lucide-react";
import type { DragEvent, KeyboardEvent as ReactKeyboardEvent, MouseEvent as ReactMouseEvent } from "react";
import { useEffect, useRef, useState } from "react";
import {
	EDIT_REQUEST_CHANGE_EVENT,
	OUTPUT_PREVIEW_ENTRY_OPEN_EVENT,
	REVIEW_PREVIEW_REFRESH_EVENT,
	REVIEW_STATE_CHANGE_EVENT,
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

function dispatchReviewChange(detail: Record<string, unknown>) {
	document.dispatchEvent(new CustomEvent(REVIEW_STATE_CHANGE_EVENT, { detail }));
}

function formatTimecode(value: number) {
	const seconds = Math.max(0, Number(value) || 0);
	const hours = Math.floor(seconds / 3600);
	const minutes = Math.floor((seconds % 3600) / 60);
	const rest = seconds % 60;
	const body = `${String(minutes).padStart(2, "0")}:${String(Math.floor(rest)).padStart(2, "0")}.${String(
		Math.floor((rest % 1) * 1000),
	).padStart(3, "0")}`;
	return hours ? `${hours}:${body}` : body;
}

function clamp(value: number, min: number, max: number) {
	return Math.min(max, Math.max(min, value));
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

function ReviewPlayer() {
	const project = useAppStore((store) => store.project);
	const outputPath = useAppStore((store) => store.outputPath);
	const editRequest = useAppStore((store) => store.editRequest);
	const review = useAppStore((store) => store.review);
	const videoUrl = useAppStore((store) => store.reviewPreviewUrl);
	const metadata = useAppStore((store) => store.reviewPreviewMetadata);
	const timeline = useAppStore((store) => store.reviewTimeline);
	const thumbnailStrip = useAppStore((store) => store.reviewThumbnailStrip);
	const waveform = useAppStore((store) => store.reviewWaveform);
	const loading = useAppStore((store) => store.reviewPreviewLoading);
	const error = useAppStore((store) => store.reviewPreviewError);
	const videoRef = useRef<HTMLVideoElement | null>(null);
	const timelineRef = useRef<HTMLDivElement | null>(null);
	const scrollRef = useRef<HTMLDivElement | null>(null);
	const dragStartRef = useRef<number | null>(null);
	const lastTimeUpdateRef = useRef(0);
	const lastLoadKeyRef = useRef("");
	const duration = Math.max(
		0,
		Number(timeline?.duration || metadata?.duration || metadata?.metadata?.duration || 0) || 0,
	);
	const zoom = Math.max(1, Number(review.zoom || 1));
	const timelineWidth = Math.max(900, Math.ceil(duration * 1.4 * zoom));
	const selectedRange = review.selectedRange;
	const currentTime = clamp(Number(review.currentTime || 0), 0, duration || Number.MAX_SAFE_INTEGER);
	const thumbs = Array.isArray(thumbnailStrip?.items) ? thumbnailStrip.items : [];
	const peaks = Array.isArray(waveform?.peaks) ? waveform.peaks : [];
	const tickMarks = Array.from({ length: 9 }, (_, index) => {
		const ratio = index / 8;
		return {
			id: `tick-${index}`,
			ratio,
			time: duration * ratio,
		};
	});
	const peakBars = peaks.map((peak: number, index: number) => ({
		id: `peak-${index}-${Number(peak).toFixed(4)}`,
		peak,
	}));

	useEffect(() => {
		if (!project) {
			return;
		}
		const candidate =
			review.previewVideoPath || editRequest.lastPreviewPath || editRequest.requestedPreviewPath || outputPath;
		const key = `${project.id}|${candidate || ""}`;
		if (key === lastLoadKeyRef.current) {
			return;
		}
		lastLoadKeyRef.current = key;
		dispatchSimpleAction(REVIEW_PREVIEW_REFRESH_EVENT, { previewPath: candidate || "" });
	}, [project, review.previewVideoPath, editRequest.lastPreviewPath, editRequest.requestedPreviewPath, outputPath]);

	useEffect(() => {
		const video = videoRef.current;
		if (!video || !Number.isFinite(currentTime)) {
			return;
		}
		if (Math.abs(video.currentTime - currentTime) > 0.35) {
			video.currentTime = currentTime;
		}
	}, [currentTime]);

	useEffect(() => {
		const scrollElement = scrollRef.current;
		if (!scrollElement) {
			return;
		}
		if (Math.abs(scrollElement.scrollLeft - Number(review.scrollStart || 0)) > 2) {
			scrollElement.scrollLeft = Number(review.scrollStart || 0);
		}
	}, [review.scrollStart]);

	function timeFromClientX(clientX: number) {
		const element = timelineRef.current;
		const scroller = scrollRef.current;
		if (!element || !scroller || duration <= 0) {
			return 0;
		}
		const rect = element.getBoundingClientRect();
		const x = clamp(clientX - rect.left + scroller.scrollLeft, 0, timelineWidth);
		return clamp((x / timelineWidth) * duration, 0, duration);
	}

	useEffect(() => {
		function handleMove(event: MouseEvent) {
			if (dragStartRef.current === null) {
				return;
			}
			const pointerTime = timeFromClientX(event.clientX);
			const start = Math.min(dragStartRef.current, pointerTime);
			const end = Math.max(dragStartRef.current, pointerTime);
			dispatchReviewChange({
				currentTime: pointerTime,
				selectedRange: end - start >= 0.05 ? { start, end } : null,
			});
		}
		function handleUp(event: MouseEvent) {
			if (dragStartRef.current === null) {
				return;
			}
			const pointerTime = timeFromClientX(event.clientX);
			const start = Math.min(dragStartRef.current, pointerTime);
			const end = Math.max(dragStartRef.current, pointerTime);
			dragStartRef.current = null;
			dispatchReviewChange({
				currentTime: pointerTime,
				selectedRange: end - start >= 0.25 ? { start, end } : null,
			});
		}
		window.addEventListener("mousemove", handleMove);
		window.addEventListener("mouseup", handleUp);
		return () => {
			window.removeEventListener("mousemove", handleMove);
			window.removeEventListener("mouseup", handleUp);
		};
	});

	function handleTimelineMouseDown(event: ReactMouseEvent<HTMLDivElement>) {
		if (event.button !== 0 || duration <= 0) {
			return;
		}
		const pointerTime = timeFromClientX(event.clientX);
		dragStartRef.current = pointerTime;
		dispatchReviewChange({ currentTime: pointerTime, selectedRange: null });
	}

	function handleTimelineKeyDown(event: ReactKeyboardEvent<HTMLDivElement>) {
		if (duration <= 0) {
			return;
		}
		const step = event.shiftKey ? 5 : 1;
		if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
			event.preventDefault();
			const direction = event.key === "ArrowRight" ? 1 : -1;
			dispatchReviewChange({ currentTime: clamp(currentTime + direction * step, 0, duration) });
		}
		if (event.key === "Escape") {
			event.preventDefault();
			dispatchReviewChange({ selectedRange: null });
		}
	}

	function handleVideoTimeUpdate() {
		const now = Date.now();
		if (now - lastTimeUpdateRef.current < 250) {
			return;
		}
		lastTimeUpdateRef.current = now;
		dispatchReviewChange({ currentTime: videoRef.current?.currentTime || 0 });
	}

	const playheadLeft = duration > 0 ? `${(currentTime / duration) * 100}%` : "0%";
	const selectedLeft = selectedRange && duration > 0 ? `${(selectedRange.start / duration) * 100}%` : "0%";
	const selectedWidth =
		selectedRange && duration > 0 ? `${((selectedRange.end - selectedRange.start) / duration) * 100}%` : "0%";

	return (
		<Card className="overflow-hidden" data-testid="review-panel">
			<CardHeader className="flex-row items-start justify-between gap-3 space-y-0">
				<div>
					<CardTitle className="flex items-center gap-2">
						<Play className="size-5 text-primary" aria-hidden="true" />
						レビュー
					</CardTitle>
					<CardDescription>
						{review.previewVideoPath ? shortPath(review.previewVideoPath) : "Latest preview"}
					</CardDescription>
				</div>
				<div className="flex flex-wrap justify-end gap-2">
					<Button
						type="button"
						variant="outline"
						size="sm"
						disabled={!project || loading}
						onClick={() => dispatchSimpleAction(REVIEW_PREVIEW_REFRESH_EVENT)}
					>
						<RefreshCw className="size-4" aria-hidden="true" />
						更新
					</Button>
					<Button
						type="button"
						variant="outline"
						size="sm"
						disabled={!review.previewVideoPath}
						onClick={() => dispatchSimpleAction(OUTPUT_PREVIEW_ENTRY_OPEN_EVENT, { path: review.previewVideoPath })}
					>
						<FolderOpen className="size-4" aria-hidden="true" />
						表示
					</Button>
				</div>
			</CardHeader>
			<CardContent className="grid gap-4">
				<div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_220px]">
					<div className="overflow-hidden rounded-md border border-border bg-slate-950">
						{videoUrl ? (
							<video
								ref={videoRef}
								src={videoUrl}
								controls
								data-testid="review-video"
								className="aspect-video w-full bg-black"
								onTimeUpdate={handleVideoTimeUpdate}
								onLoadedMetadata={() => {
									if (videoRef.current && review.currentTime) {
										videoRef.current.currentTime = review.currentTime;
									}
								}}
							>
								<track kind="captions" src="data:text/vtt,WEBVTT%0A" srcLang="en" label="captions" />
							</video>
						) : (
							<div className="grid aspect-video place-items-center px-4 text-sm text-slate-200">
								{loading ? "プレビューを読み込んでいます" : error || "まだレビュー可能なプレビュー動画がありません"}
							</div>
						)}
					</div>
					<div className="grid content-start gap-2 rounded-md border border-border bg-muted/35 p-3 text-sm">
						<div className="flex items-center gap-2 font-semibold text-foreground">
							<Clock className="size-4 text-primary" aria-hidden="true" />
							{formatTimecode(currentTime)}
						</div>
						<div className="text-xs text-muted-foreground">
							Duration {duration ? formatTimecode(duration) : "--:--"}
						</div>
						<div className="grid gap-1 text-xs">
							<span className="font-semibold text-muted-foreground">選択範囲</span>
							<strong className="text-foreground">
								{selectedRange
									? `${formatTimecode(selectedRange.start)} - ${formatTimecode(selectedRange.end)}`
									: "未選択"}
							</strong>
						</div>
						<label className="grid gap-1 text-xs font-semibold text-muted-foreground">
							Zoom
							<input
								type="range"
								min="1"
								max="12"
								step="0.5"
								value={zoom}
								onChange={(event) => dispatchReviewChange({ zoom: Number(event.currentTarget.value) })}
							/>
						</label>
					</div>
				</div>
				<div
					ref={scrollRef}
					data-testid="review-timeline-scroller"
					className="overflow-x-auto rounded-md border border-border bg-background"
					onScroll={(event) => dispatchReviewChange({ scrollStart: event.currentTarget.scrollLeft })}
				>
					<div
						ref={timelineRef}
						data-testid="review-timeline"
						className="relative h-40 cursor-crosshair select-none"
						style={{ width: `${timelineWidth}px` }}
						role="slider"
						tabIndex={0}
						aria-label="Review timeline"
						aria-valuemin={0}
						aria-valuemax={Math.max(0, Math.round(duration))}
						aria-valuenow={Number(currentTime.toFixed(3))}
						onMouseDown={handleTimelineMouseDown}
						onKeyDown={handleTimelineKeyDown}
					>
						<div className="absolute inset-x-0 top-0 flex h-7 border-b border-border bg-muted/50 text-[11px] font-semibold text-muted-foreground">
							{tickMarks.map((tick) => (
								<span key={tick.id} className="absolute top-1" style={{ left: `${tick.ratio * 100}%` }}>
									{formatTimecode(tick.time)}
								</span>
							))}
						</div>
						<div className="absolute inset-x-0 top-7 flex h-20 overflow-hidden bg-slate-900">
							{thumbs.length ? (
								thumbs.map((thumb: any) => (
									<img
										key={thumb.path || thumb.index}
										src={thumb.url}
										alt=""
										className="h-full min-w-24 border-r border-slate-700 object-cover"
										style={{ width: `${100 / thumbs.length}%` }}
									/>
								))
							) : (
								<div className="grid size-full place-items-center text-xs text-slate-300">thumbnail strip</div>
							)}
						</div>
						<div className="absolute inset-x-0 bottom-0 flex h-12 items-end gap-px border-t border-border bg-card px-1">
							{peaks.length ? (
								peakBars.map((bar) => (
									<span
										key={bar.id}
										className="min-w-px flex-1 rounded-t bg-primary/65"
										style={{ height: `${Math.max(8, Math.min(100, Number(bar.peak) * 100))}%` }}
									/>
								))
							) : (
								<div className="grid size-full place-items-center text-xs text-muted-foreground">waveform</div>
							)}
						</div>
						{selectedRange ? (
							<div
								className="absolute top-7 bottom-0 border-x border-primary bg-primary/20"
								style={{ left: selectedLeft, width: selectedWidth }}
							/>
						) : null}
						<div className="absolute top-0 bottom-0 w-0.5 bg-destructive" style={{ left: playheadLeft }} />
					</div>
				</div>
			</CardContent>
		</Card>
	);
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
					<div className="flex flex-wrap gap-1">
						<Badge variant={item.mode === "final" ? "default" : "secondary"} className="w-fit">
							{item.mode === "final" ? "Final" : "Preview"}
						</Badge>
						<Badge variant={item.scope === "range" ? "default" : "secondary"} className="w-fit">
							{item.scope === "range" ? "Range" : "Global"}
						</Badge>
					</div>
					<p className="text-sm leading-relaxed text-foreground">{item.text}</p>
					{item.selection ? (
						<p className="text-xs font-medium text-muted-foreground">
							{formatTimecode(item.selection.start)} - {formatTimecode(item.selection.end)}
						</p>
					) : null}
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
	const selectedRange = useAppStore((store) => store.review.selectedRange);
	const hasInstruction = Boolean(draft.trim() || history.length);
	const canSend = Boolean(
		project && mediaManifest?.files?.length && hasInstruction && !appLocked && !codexTurnRunning && !directRunRunning,
	);
	const canSendRange = Boolean(canSend && selectedRange);

	return (
		<Card className="min-h-[420px]">
			<CardHeader>
				<CardTitle className="flex items-center gap-2">
					<Send className="size-5 text-primary" aria-hidden="true" />
					編集指示
				</CardTitle>
				<CardDescription>
					{selectedRange
						? `${formatTimecode(selectedRange.start)} - ${formatTimecode(selectedRange.end)}`
						: "動画全体または選択範囲"}
				</CardDescription>
			</CardHeader>
			<CardContent className="grid gap-4">
				<Textarea
					className="min-h-52 resize-y text-sm leading-relaxed"
					value={draft}
					disabled={appLocked || codexTurnRunning}
					placeholder="例: この部分の間を詰めてください。話者の表情が見えるカットにしてください。字幕を短くしてください。"
					onChange={(event) =>
						dispatchSimpleAction(EDIT_REQUEST_CHANGE_EVENT, { instructionDraft: event.currentTarget.value })
					}
				/>
				<div className="flex flex-wrap gap-2">
					<Button
						type="button"
						disabled={!canSendRange}
						onClick={() => dispatchSimpleAction(SIMPLE_PREVIEW_REQUEST_EVENT, { instructionScope: "range" })}
					>
						<Play className="size-4" aria-hidden="true" />
						この範囲に指示
					</Button>
					<Button
						type="button"
						variant="outline"
						disabled={!canSend}
						onClick={() => dispatchSimpleAction(SIMPLE_PREVIEW_REQUEST_EVENT, { instructionScope: "global" })}
					>
						<Send className="size-4" aria-hidden="true" />
						動画全体に指示
					</Button>
					<Button
						type="button"
						variant="ghost"
						disabled={!canSend}
						onClick={() => dispatchSimpleAction(SIMPLE_FINAL_RENDER_EVENT, { instructionScope: "global" })}
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
			<ReviewPlayer />
			<div className="grid items-start gap-4 xl:grid-cols-[minmax(420px,1.25fr)_minmax(280px,0.8fr)_minmax(240px,0.62fr)]">
				<InstructionCard />
				<MaterialsCard />
				<AudioCard />
			</div>
			<OutputLinks />
			<OutputPreview />
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
