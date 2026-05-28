import type { DragEvent } from "react";
import { useEffect, useState } from "react";
import {
	FILE_DRAG_RESET_EVENT,
	FILE_DROP_EVENT,
	FILE_PICK_EVENT,
	MATERIAL_DROP_EVENT,
	OUTPUT_PICK_EVENT,
} from "../events.js";
import { useAppStore } from "../store/app-store.js";
import { AnalysisResultsList } from "./AnalysisResultsList.js";
import { FileSlotPreview, StillImagesLabel, StillImagesList } from "./ManualAssets.js";
import { MaterialIngestActions, MaterialIngestProgress } from "./MaterialIngestControls.js";
import { MaterialManifestList } from "./MaterialManifestList.js";
import { MaterialManifestSummary, MaterialSourceLabel } from "./MaterialSourceSummary.js";
import { OutputTargetPreview } from "./PathPreviews.js";
import { SyncReportList } from "./SyncReportList.js";

type ManualAssetSlotConfig = {
	readonly slot:
		| "masterVideo"
		| "rightCloseVideo"
		| "leftCloseVideo"
		| "referenceVideo"
		| "externalAudio"
		| "logo"
		| "stillImages";
	readonly title: string;
	readonly description: string;
	readonly labelId: string;
	readonly actionLabel: string;
	readonly hint: string;
};

type PanelProps = {
	readonly hidden?: boolean;
};

type FileDropHandler = (files: File[]) => void;

const MANUAL_ASSET_SLOTS: ManualAssetSlotConfig[] = [
	{
		slot: "masterVideo",
		title: "メイン動画・マスター",
		description: "1cam / base timeline",
		labelId: "masterVideoLabel",
		actionLabel: "Select",
		hint: "ファイルをドラッグして追加",
	},
	{
		slot: "rightCloseVideo",
		title: "右からのアップ",
		description: "person 1 close-up",
		labelId: "rightCloseVideoLabel",
		actionLabel: "Select",
		hint: "ファイルをドラッグして追加",
	},
	{
		slot: "leftCloseVideo",
		title: "左からのアップ",
		description: "person 2 / alternate",
		labelId: "leftCloseVideoLabel",
		actionLabel: "Select",
		hint: "ファイルをドラッグして追加",
	},
	{
		slot: "referenceVideo",
		title: "参考動画",
		description: "手動選択 / style reference under 60s",
		labelId: "referenceVideoLabel",
		actionLabel: "Select",
		hint: "ファイルをドラッグして追加",
	},
	{
		slot: "externalAudio",
		title: "別録り音声",
		description: "wav / mp3 / mp4",
		labelId: "externalAudioLabel",
		actionLabel: "Select",
		hint: "ファイルをドラッグして追加",
	},
	{
		slot: "logo",
		title: "右上ロゴ",
		description: "png / jpg",
		labelId: "logoLabel",
		actionLabel: "Select",
		hint: "ファイルをドラッグして追加",
	},
	{
		slot: "stillImages",
		title: "静止画インサート",
		description: "drop multiple png / jpg / webp",
		labelId: "stillImagesLabel",
		actionLabel: "Add",
		hint: "複数ファイル対応",
	},
];

function dispatchAssetsAction(eventName: string) {
	document.dispatchEvent(new CustomEvent(eventName));
}

function dispatchFilePick(slot: string) {
	document.dispatchEvent(new CustomEvent(FILE_PICK_EVENT, { detail: { slot } }));
}

function dispatchFileDrop(slot: string, files: File[]) {
	if (!files.length) {
		return;
	}
	document.dispatchEvent(new CustomEvent(FILE_DROP_EVENT, { detail: { slot, files } }));
}

function dispatchMaterialDrop(files: File[]) {
	if (!files.length) {
		return;
	}
	document.dispatchEvent(new CustomEvent(MATERIAL_DROP_EVENT, { detail: { files } }));
}

function isFileDragEvent(event: DragEvent<HTMLElement>) {
	return Array.from(event.dataTransfer.types || []).includes("Files");
}

function setCopyDropEffect(event: DragEvent<HTMLElement>) {
	event.dataTransfer.dropEffect = "copy";
}

function filesFromDrop(event: DragEvent<HTMLElement>) {
	return Array.from(event.dataTransfer.files || []) as File[];
}

function useFileDropTarget(onDrop: FileDropHandler, options: { readonly stopPropagation?: boolean } = {}) {
	const [dragging, setDragging] = useState(false);
	const stopPropagation = Boolean(options.stopPropagation);

	useEffect(() => {
		const reset = () => setDragging(false);
		document.addEventListener(FILE_DRAG_RESET_EVENT, reset);
		return () => document.removeEventListener(FILE_DRAG_RESET_EVENT, reset);
	}, []);

	const stopIfNeeded = (event: DragEvent<HTMLElement>) => {
		if (stopPropagation) {
			event.stopPropagation();
		}
	};

	return {
		dragging,
		dragProps: {
			onDragEnter: (event: DragEvent<HTMLElement>) => {
				if (!isFileDragEvent(event)) {
					return;
				}
				event.preventDefault();
				stopIfNeeded(event);
				setCopyDropEffect(event);
				setDragging(true);
			},
			onDragOver: (event: DragEvent<HTMLElement>) => {
				if (!isFileDragEvent(event)) {
					return;
				}
				event.preventDefault();
				stopIfNeeded(event);
				setCopyDropEffect(event);
				setDragging(true);
			},
			onDragLeave: (event: DragEvent<HTMLElement>) => {
				if (!isFileDragEvent(event)) {
					return;
				}
				stopIfNeeded(event);
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
				stopIfNeeded(event);
				setDragging(false);
				onDrop(filesFromDrop(event));
			},
		},
	};
}

function DropHint({ hint }: { readonly hint: string }) {
	return (
		<div className="drop-target-hint">
			<span className="drop-target-icon" aria-hidden="true"></span>
			<span className="drop-target-copy">
				<strong>ここにドロップ</strong>
				<small>{hint}</small>
			</span>
		</div>
	);
}

function ManualAssetSlot({ slot }: { readonly slot: ManualAssetSlotConfig }) {
	const { dragging, dragProps } = useFileDropTarget((files) => dispatchFileDrop(slot.slot, files), {
		stopPropagation: true,
	});

	return (
		<div className={`drop-zone${dragging ? " dragging" : ""}`} data-slot={slot.slot} {...dragProps}>
			<strong>{slot.title}</strong>
			<span>{slot.description}</span>
			<DropHint hint={slot.hint} />
			{slot.slot === "stillImages" ? (
				<StillImagesLabel id={slot.labelId} />
			) : (
				<FileSlotPreview id={slot.labelId} slot={slot.slot} />
			)}
			<button type="button" onClick={() => dispatchFilePick(slot.slot)}>
				{slot.actionLabel}
			</button>
		</div>
	);
}

export function AssetsPanel({ hidden = false }: PanelProps) {
	const outputPath = useAppStore((store) => store.outputPath);
	const syncReport = useAppStore((store) => store.syncReport);
	const materialGridDrop = useFileDropTarget(dispatchMaterialDrop);
	const materialFolderDrop = useFileDropTarget(dispatchMaterialDrop, { stopPropagation: true });

	return (
		<div className="panel wide" data-panel="assets" hidden={hidden}>
			<div className="panel-heading">
				<h3>素材</h3>
				<MaterialManifestSummary />
			</div>
			<div
				className={`material-ingest-grid${materialGridDrop.dragging ? " dragging" : ""}`}
				{...materialGridDrop.dragProps}
			>
				<div
					className={`drop-zone folder-drop-zone${materialFolderDrop.dragging ? " dragging" : ""}`}
					data-slot="mediaDirectory"
					{...materialFolderDrop.dragProps}
				>
					<strong>素材</strong>
					<span>フォルダ・単体ファイル・複数ファイルをまとめて自動分類します</span>
					<DropHint hint="フォルダ・複数ファイル対応" />
					<MaterialSourceLabel />
					<MaterialIngestActions />
					<MaterialIngestProgress />
				</div>
				<MaterialManifestList />
			</div>
			<AnalysisResultsList />
			{syncReport ? (
				<div className="sync-report material-sync-report">
					<div className="sync-report-heading">
						<strong>同期結果</strong>
					</div>
					<SyncReportList />
				</div>
			) : null}
			<h4 className="asset-section-heading">Manual material overrides</h4>
			<div className="drop-grid">
				{MANUAL_ASSET_SLOTS.map((slot) => (
					<ManualAssetSlot key={slot.slot} slot={slot} />
				))}
				<StillImagesList />
				<div className="field-block output-block">
					<div className="output-target-heading">
						<strong>Video to create</strong>
						<span>This is where the edited video will be saved.</span>
					</div>
					<input id="outputPath" type="hidden" value={outputPath} readOnly />
					<OutputTargetPreview />
					<button type="button" id="pickOutput" onClick={() => dispatchAssetsAction(OUTPUT_PICK_EVENT)}>
						Choose save location
					</button>
				</div>
			</div>
		</div>
	);
}
