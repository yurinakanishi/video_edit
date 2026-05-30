import React from "react";
import {
	AbsoluteFill,
	Audio,
	Composition,
	Img,
	Sequence,
	Video,
	getInputProps,
	registerRoot,
	staticFile,
} from "remotion";

type SourceRef = {
	id?: string;
	kind?: string;
	role?: string;
	path?: string;
	publicPath?: string;
	exists?: boolean;
	duration?: number;
	width?: number;
	height?: number;
	fps?: string | number;
};

type OverlayItem = {
	start: number;
	end: number;
	relativeStart: number;
	relativeEnd: number;
	file: string;
	publicPath?: string;
	exists?: boolean;
	width?: number;
	height?: number;
	fontSize?: number;
	lines?: string[];
	speakerRole?: string;
};

type SubtitleStyle = {
	fontFamily?: string;
	fontSize?: number;
	fontWeight?: number;
	tracking?: number;
	padX?: number;
	padY?: number;
	lineGap?: number;
	boxRadius?: number;
	bottomMargin?: number;
	textColor?: string;
	onscreenBoxColor?: string;
	interviewerBoxColor?: string;
};

type TimelineLayer = {
	id: string;
	trackId: string;
	kind: string;
	layerKind: string;
	relativeStart: number;
	relativeEnd: number;
	startFrame: number;
	endFrame: number;
	durationFrames: number;
	source?: SourceRef | null;
	sourceIn?: number;
	sourceOut?: number;
	position?: Record<string, unknown>;
	fit?: Record<string, unknown>;
	style?: Record<string, unknown>;
	effects?: Array<{ type?: string; params?: Record<string, unknown> }>;
	metadata?: Record<string, unknown>;
	overlayManifest?: { path?: string; items?: OverlayItem[]; style?: SubtitleStyle; renderMode?: string };
};

type TimelineManifest = {
	schemaVersion?: string;
	adapter?: string;
	target?: {
		width?: number;
		height?: number;
		fpsNumber?: number;
		durationFrames?: number;
	};
	layers?: TimelineLayer[];
};

const inputProps = getInputProps() as TimelineManifest;
const target = inputProps.target ?? {};
const width = Math.max(1, Math.round(Number(target.width ?? 1920)));
const height = Math.max(1, Math.round(Number(target.height ?? 1080)));
const fps = Number.isFinite(Number(target.fpsNumber)) ? Number(target.fpsNumber) : 30;
const durationInFrames = Math.max(1, Math.round(Number(target.durationFrames ?? fps)));

const toFileUrl = (value: string | undefined) => {
	if (!value) {
		return "";
	}
	const normalized = value.replace(/\\/g, "/");
	if (/^[A-Za-z]:\//.test(normalized)) {
		return encodeURI(`file:///${normalized}`);
	}
	if (normalized.startsWith("/")) {
		return encodeURI(`file://${normalized}`);
	}
	return encodeURI(normalized);
};

const mediaSrc = (source: { publicPath?: string; path?: string } | null | undefined) => {
	if (!source) {
		return "";
	}
	if (source.publicPath) {
		return staticFile(source.publicPath);
	}
	return toFileUrl(source.path);
};

const numberValue = (value: unknown, fallback: number) => {
	const number = Number(value);
	return Number.isFinite(number) ? number : fallback;
};

const sourceStartFrame = (layer: TimelineLayer) => Math.max(0, Math.round(numberValue(layer.sourceIn, 0) * fps));
const sourceEndFrame = (layer: TimelineLayer) =>
	Math.max(sourceStartFrame(layer) + 1, Math.round(numberValue(layer.sourceOut, 0) * fps));

const cropCenter = (layer: TimelineLayer) => {
	let centerX = numberValue((layer.fit?.crop as Record<string, unknown> | undefined)?.centerX, 0.5);
	let centerY = numberValue((layer.fit?.crop as Record<string, unknown> | undefined)?.centerY, 0.5);
	let scale = numberValue(layer.fit?.scale, 1);
	for (const effect of layer.effects ?? []) {
		if (effect?.type !== "scaleCrop") {
			continue;
		}
		const params = effect.params ?? {};
		const crop = params.crop as Record<string, unknown> | undefined;
		scale = numberValue(params.scale, scale);
		centerX = numberValue(crop?.centerX, centerX);
		centerY = numberValue(crop?.centerY, centerY);
	}
	return {
		centerX: Math.min(1, Math.max(0, centerX)),
		centerY: Math.min(1, Math.max(0, centerY)),
		scale: Math.max(1, scale),
	};
};

const fullFrameStyle = (layer: TimelineLayer): React.CSSProperties => {
	const crop = cropCenter(layer);
	return {
		width: "100%",
		height: "100%",
		objectFit: "cover",
		objectPosition: `${crop.centerX * 100}% ${crop.centerY * 100}%`,
		transform: `scale(${crop.scale})`,
		transformOrigin: `${crop.centerX * 100}% ${crop.centerY * 100}%`,
	};
};

const overlayPosition = (layer: TimelineLayer): React.CSSProperties => {
	const position = layer.position ?? {};
	return {
		position: "absolute",
		left: typeof position.x === "number" ? position.x : position.x ? String(position.x) : 0,
		top: typeof position.y === "number" ? position.y : position.y ? String(position.y) : 0,
		width: typeof position.width === "number" ? position.width : position.width ? String(position.width) : undefined,
		height: typeof position.height === "number" ? position.height : position.height ? String(position.height) : undefined,
	};
};

const SubtitleManifestLayer: React.FC<{ layer: TimelineLayer }> = ({ layer }) => {
	const items = layer.overlayManifest?.items ?? [];
	const manifestStyle = layer.overlayManifest?.style ?? {};
	const renderHtmlSubtitle = (item: OverlayItem) => {
		const lines = item.lines ?? [];
		if (!lines.length) {
			return null;
		}
		const fontSize = numberValue(item.fontSize, numberValue(manifestStyle.fontSize, 80));
		const padX = numberValue(manifestStyle.padX, 18);
		const padY = numberValue(manifestStyle.padY, 10);
		const lineGap = numberValue(manifestStyle.lineGap, 6);
		const radius = numberValue(manifestStyle.boxRadius, 10);
		const isInterviewer = item.speakerRole === "interviewer";
		const boxColor = isInterviewer
			? String(manifestStyle.interviewerBoxColor ?? "rgba(0, 0, 0, 0.6863)")
			: String(manifestStyle.onscreenBoxColor ?? "rgba(174, 72, 224, 0.7255)");
		return (
			<div
				style={{
					display: "flex",
					flexDirection: "column",
					alignItems: "center",
					gap: lineGap,
					maxWidth: "92%",
				}}
			>
				{lines.map((line, lineIndex) => (
					<div
						key={`${item.start}-${lineIndex}`}
						style={{
							backgroundColor: boxColor,
							borderRadius: radius,
							color: String(manifestStyle.textColor ?? "rgba(255, 255, 255, 1)"),
							fontFamily: String(manifestStyle.fontFamily ?? "Yu Gothic UI"),
							fontSize,
							fontWeight: numberValue(manifestStyle.fontWeight, 700),
							letterSpacing: numberValue(manifestStyle.tracking, 4),
							lineHeight: 1.1,
							padding: `${padY}px ${padX}px`,
							whiteSpace: "nowrap",
						}}
					>
						{line}
					</div>
				))}
			</div>
		);
	};
	return (
		<>
			{items.map((item, index) => {
				const startFrame = Math.max(0, Math.round(item.relativeStart * fps));
				const endFrame = Math.max(startFrame + 1, Math.round(item.relativeEnd * fps));
				const shouldRenderImage = Boolean(item.publicPath || item.file);
				return (
					<Sequence
						key={`${layer.id}-subtitle-${index}`}
						from={startFrame}
						durationInFrames={endFrame - startFrame}
					>
						<AbsoluteFill
							style={{
								justifyContent: "flex-end",
								alignItems: "center",
								paddingBottom: numberValue(manifestStyle.bottomMargin, 16),
							}}
						>
							{shouldRenderImage ? (
								<Img
									src={item.publicPath ? staticFile(item.publicPath) : toFileUrl(item.file)}
									style={{
										maxWidth: "92%",
										width: item.width ? Math.min(item.width, width * 0.92) : undefined,
										height: "auto",
									}}
								/>
							) : (
								renderHtmlSubtitle(item)
							)}
						</AbsoluteFill>
					</Sequence>
				);
			})}
		</>
	);
};

const TextFallback: React.FC<{ layer: TimelineLayer }> = ({ layer }) => {
	const text = String(layer.style?.text ?? layer.style?.title ?? layer.id ?? "");
	if (!text) {
		return null;
	}
	return (
		<AbsoluteFill style={{ ...overlayPosition(layer), justifyContent: "center", alignItems: "center" }}>
			<div
				style={{
					color: String(layer.style?.color ?? "#ffffff"),
					fontSize: numberValue(layer.style?.fontSize, 64),
					fontWeight: 700,
					textAlign: "center",
					textShadow: "0 2px 10px rgba(0,0,0,0.5)",
				}}
			>
				{text}
			</div>
		</AbsoluteFill>
	);
};

const LayerRenderer: React.FC<{ layer: TimelineLayer }> = ({ layer }) => {
	const source = mediaSrc(layer.source);
	if (layer.layerKind === "video-reference") {
		return null;
	}
	if (layer.layerKind === "audio-reference") {
		return null;
	}
	if (layer.layerKind === "image" && source) {
		return <Img src={source} style={{ ...overlayPosition(layer), objectFit: "contain" }} />;
	}
	if (layer.layerKind === "subtitle" && layer.overlayManifest?.items?.length) {
		return <SubtitleManifestLayer layer={layer} />;
	}
	return <TextFallback layer={layer} />;
};

const TimelineVideo: React.FC<TimelineManifest> = ({ layers = [] }) => {
	return (
		<AbsoluteFill style={{ backgroundColor: "transparent" }}>
			{layers.map((layer) => {
				const from = Math.max(0, Math.round(layer.startFrame));
				const duration = Math.max(1, Math.round(layer.durationFrames));
				return (
					<Sequence key={layer.id} from={from} durationInFrames={duration}>
						<LayerRenderer layer={layer} />
					</Sequence>
				);
			})}
		</AbsoluteFill>
	);
};

const Root: React.FC = () => (
	<Composition
		id="VideoEditTimeline"
		component={TimelineVideo}
		durationInFrames={durationInFrames}
		fps={fps}
		width={width}
		height={height}
		defaultProps={inputProps}
	/>
);

registerRoot(Root);
