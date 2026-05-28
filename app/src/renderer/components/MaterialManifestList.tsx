import {
	MATERIAL_ITEM_REANALYZE_EVENT,
	MATERIAL_ITEM_REMOVE_EVENT,
	MATERIAL_ROLE_CHANGE_EVENT,
	MATERIAL_SOURCE_REMOVE_EVENT,
} from "../events.js";
import { localizePlainText, t } from "../i18n.js";
import {
	fallbackPreviewForPath,
	isMissingPreview,
	mediaMetaBadges,
	mediaRoleLabel,
	previewEntryMeta,
	previewKindLabel,
	shortPath,
} from "../preview.js";
import { useAppStore } from "../store/app-store.js";
import type { MediaItem } from "../types.js";
import { MediaThumbnail } from "./MediaThumbnail.js";

function dispatchMaterialEvent(name: string, detail: Record<string, string>) {
	document.dispatchEvent(new CustomEvent(name, { detail }));
}

function materialStatusKey(filePath: string) {
	return String(filePath || "")
		.trim()
		.toLowerCase();
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

function canReanalyzeItem(item: MediaItem) {
	const cameraRoles = new Set(["master", "camera2", "camera3", "camera4", "camera5", "camera6"]);
	return (
		(item.kind === "video" && cameraRoles.has(item.role)) ||
		(item.kind === "audio" && String(item.role || "").startsWith("external"))
	);
}

function loadedPreviewForPath(filePreviews: Record<string, any>, sourcePath: string) {
	const normalized = String(sourcePath || "").toLowerCase();
	return (
		filePreviews[sourcePath] ||
		(Object.values(filePreviews) as any[]).find(
			(preview) => String(preview?.path || "").toLowerCase() === normalized,
		) ||
		null
	);
}

function EmptyMaterialState() {
	return <div className="empty-material-state">{t("materials.noAnalyzedAssets")}</div>;
}

function RemoveButton({ eventName, detail }: { readonly eventName: string; readonly detail: Record<string, string> }) {
	return (
		<button
			type="button"
			className="material-remove-button"
			title={t("action.remove")}
			aria-label={t("action.remove")}
			onClick={(event) => {
				event.stopPropagation();
				dispatchMaterialEvent(eventName, detail);
			}}
		>
			×
		</button>
	);
}

function ReanalyzeButton({ itemId, disabled }: { readonly itemId: string; readonly disabled: boolean }) {
	return (
		<button
			type="button"
			className="material-reanalyze-button"
			title={t("action.reanalyze")}
			aria-label={t("action.reanalyze")}
			disabled={disabled}
			onClick={(event) => {
				event.stopPropagation();
				dispatchMaterialEvent(MATERIAL_ITEM_REANALYZE_EVENT, { id: itemId });
			}}
		>
			{t("action.reanalyze")}
		</button>
	);
}

function analysisStateLabel(state: string) {
	if (state === "done") {
		return t("analysis.fileStatusDone");
	}
	if (state === "partial") {
		return t("analysis.fileStatusPartial");
	}
	if (state === "running") {
		return t("analysis.fileStatusRunning");
	}
	if (state === "error") {
		return t("analysis.fileStatusError");
	}
	return t("analysis.fileStatusNone");
}

function MaterialAnalysisStatusView({ status }: { readonly status: any }) {
	if (!status) {
		return null;
	}
	const total = Number(status.total || 0);
	const completed = Number(status.completed || 0);
	const percent = total > 0 ? Math.round((completed / total) * 100) : 0;
	const outputs = Array.isArray(status.outputs) ? status.outputs : [];
	return (
		<div className={`material-analysis-status ${status.state || "none"}`.trim()}>
			<div className="material-analysis-status-meta">
				<strong>{analysisStateLabel(status.state)}</strong>
				<span>{total > 0 ? `${completed}/${total}` : t("analysis.noPerFileOutputs")}</span>
			</div>
			{total > 0 ? (
				<div className="material-analysis-completion" aria-hidden="true">
					<span style={{ width: `${percent}%` }}></span>
				</div>
			) : null}
			{outputs.length ? (
				<div className="material-analysis-files">
					{outputs.map((output: any) => (
						<span key={output.key} className={output.exists ? "exists" : "missing"} title={output.path || output.label}>
							{output.labelKey ? t(output.labelKey) : localizePlainText(output.label || output.key)}
						</span>
					))}
				</div>
			) : null}
		</div>
	);
}

function MaterialSourceList() {
	const language = useAppStore((store) => store.language);
	const materialPaths = useAppStore((store) => store.materialPaths);
	const materialSourcePreviews = useAppStore((store) => store.materialSourcePreviews);
	const materialSourcePreviewLoading = useAppStore((store) => store.materialSourcePreviewLoading);
	const filePreviews = useAppStore((store) => store.filePreviews);

	if (!materialPaths.length) {
		return (
			<div id="mediaManifestList" className="manifest-list" data-locale={language}>
				<EmptyMaterialState />
			</div>
		);
	}

	const sourceRows = materialSourcePreviews.length ? materialSourcePreviews : materialPaths;

	return (
		<div id="mediaManifestList" className="manifest-list" data-locale={language}>
			{sourceRows.map((source) => {
				const sourcePath = typeof source === "string" ? source : source.path || "";
				const loadedPreview = typeof source === "string" ? loadedPreviewForPath(filePreviews, sourcePath) : source;
				const preview = loadedPreview || fallbackPreviewForPath(sourcePath);
				const missing = isMissingPreview(preview);
				const badges = [
					previewKindLabel(preview.kind || "other"),
					...previewEntryMeta(preview),
					!loadedPreview || (materialSourcePreviewLoading && !materialSourcePreviews.length)
						? t("preview.loading")
						: "",
				].filter(Boolean);

				return (
					<div
						key={sourcePath}
						className={`material-card material-source-card ${missing ? "missing" : ""} ${preview.kind || "other"}`}
						title={sourcePath}
					>
						<RemoveButton eventName={MATERIAL_SOURCE_REMOVE_EVENT} detail={{ path: sourcePath }} />
						<MediaThumbnail preview={preview} />
						<div className="material-detail">
							<span title={sourcePath}>{preview.relativePath || preview.name || shortPath(sourcePath)}</span>
							<strong>
								{materialSourcePreviewLoading && !materialSourcePreviews.length
									? t("preview.loading")
									: t("materials.detectedAsset")}
							</strong>
							<div className="material-meta">
								{badges.map((badgeText) => (
									<span key={badgeText}>{badgeText}</span>
								))}
							</div>
							<small>{preview.relativePath ? preview.path : sourcePath}</small>
						</div>
					</div>
				);
			})}
		</div>
	);
}

function ManifestFileList() {
	const language = useAppStore((store) => store.language);
	const mediaManifest = useAppStore((store) => store.mediaManifest);
	const filePreviews = useAppStore((store) => store.filePreviews);
	const materialAnalysisStatus = useAppStore((store) => store.materialAnalysisStatus);
	const appLocked = useAppStore((store) => store.appLocked);
	const ingestRunning = useAppStore((store) => store.ingestRunning);

	if (!mediaManifest?.files?.length) {
		return (
			<div id="mediaManifestList" className="manifest-list" data-locale={language}>
				<EmptyMaterialState />
			</div>
		);
	}

	return (
		<div id="mediaManifestList" className="manifest-list" data-locale={language}>
			{mediaManifest.files.map((item) => {
				const roleOptions = roleOptionsFor(item);
				const preview = filePreviews[item.path] || filePreviews[item.originalPath || ""] || item;
				const missing = isMissingPreview(preview);
				const analysisStatus = materialAnalysisStatus[materialStatusKey(item.path)];
				const badges = [
					previewKindLabel(item.kind),
					...mediaMetaBadges(item),
					Number(item.confidence || 0) > 0 ? `${t("label.confidence")} ${Number(item.confidence || 0).toFixed(2)}` : "",
				].filter(Boolean);

				return (
					<div
						key={item.id}
						className={`material-card ${item.kind} ${item.role === "ignore" ? "muted" : ""} ${
							missing ? "missing" : ""
						}`}
					>
						<RemoveButton eventName={MATERIAL_ITEM_REMOVE_EVENT} detail={{ id: item.id }} />
						<MediaThumbnail preview={preview} />
						<div className="material-detail">
							<span title={item.path}>{item.relativePath || item.name}</span>
							<strong>
								{item.role === "ignore"
									? t("materials.unselected")
									: t("materials.selectedRole", { role: mediaRoleLabel(item.role) })}
							</strong>
							<div className="material-meta">
								{badges.map((badgeText) => (
									<span key={badgeText}>{badgeText}</span>
								))}
							</div>
							<small>{item.reason ? localizePlainText(item.reason) : ""}</small>
							<MaterialAnalysisStatusView status={analysisStatus} />
						</div>
						<div className="material-actions">
							<ReanalyzeButton itemId={item.id} disabled={appLocked || ingestRunning || !canReanalyzeItem(item)} />
							<select
								data-media-role={item.id}
								value={item.role}
								onChange={(event) => {
									const role = event.currentTarget.value;
									dispatchMaterialEvent(MATERIAL_ROLE_CHANGE_EVENT, {
										id: item.id,
										role,
										label: roleOptions.find(([value]) => value === role)?.[1] || role,
									});
								}}
							>
								{roleOptions.map(([value, label]) => (
									<option key={value} value={value}>
										{label}
									</option>
								))}
							</select>
						</div>
					</div>
				);
			})}
		</div>
	);
}

export function MaterialManifestList() {
	const mediaManifest = useAppStore((store) => store.mediaManifest);
	return mediaManifest ? <ManifestFileList /> : <MaterialSourceList />;
}
