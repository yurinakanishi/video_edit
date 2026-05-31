import { Check, Plus, X } from "lucide-react";
import { useEffect, useRef } from "react";
import {
	CONFIRM_DIALOG_CLOSE_EVENT,
	PROJECT_DIALOG_CLOSE_EVENT,
	PROJECT_DIALOG_CREATE_EVENT,
	PROJECT_DIALOG_OPEN_PROJECT_EVENT,
} from "../events.js";
import { t } from "../i18n.js";
import { cn } from "../lib/utils.js";
import { useAppStore } from "../store/app-store.js";
import { Badge } from "./ui/badge.js";
import { Button } from "./ui/button.js";
import { Input } from "./ui/input.js";

function shortPath(value: string) {
	if (!value) {
		return t("label.notSelected");
	}
	const parts = value.split(/[\\/]/);
	return parts.length > 2 ? `${parts.at(-2)}\\${parts.at(-1)}` : value;
}

function formatProjectDate(value: string, language: string) {
	const date = new Date(value);
	if (!Number.isFinite(date.getTime())) {
		return "";
	}
	return new Intl.DateTimeFormat(language === "ja" ? "ja-JP" : "en-US", {
		year: "numeric",
		month: "2-digit",
		day: "2-digit",
		hour: "2-digit",
		minute: "2-digit",
	}).format(date);
}

function dispatchProjectDialogClose() {
	document.dispatchEvent(new CustomEvent(PROJECT_DIALOG_CLOSE_EVENT));
}

function dispatchProjectDialogCreate() {
	document.dispatchEvent(new CustomEvent(PROJECT_DIALOG_CREATE_EVENT));
}

function dispatchProjectDialogOpenProject(index: number) {
	document.dispatchEvent(new CustomEvent(PROJECT_DIALOG_OPEN_PROJECT_EVENT, { detail: { index } }));
}

function dispatchConfirmDialogClose(confirmed: boolean) {
	document.dispatchEvent(new CustomEvent(CONFIRM_DIALOG_CLOSE_EVENT, { detail: { confirmed } }));
}

function ProjectDialogList() {
	const language = useAppStore((appState) => appState.language);
	const project = useAppStore((appState) => appState.project);
	const projectList = useAppStore((appState) => appState.projectList);
	const projectListLoading = useAppStore((appState) => appState.projectListLoading);

	if (projectListLoading) {
		return (
			<div
				className="grid min-h-40 max-h-[min(430px,48vh)] gap-2 overflow-auto pr-1"
				id="projectDialogList"
				data-locale={language}
			>
				<div className="grid min-h-40 place-items-center rounded-lg border border-dashed border-border text-sm text-muted-foreground">
					{t("project.dialogLoading")}
				</div>
			</div>
		);
	}

	if (!projectList.length) {
		return (
			<div
				className="grid min-h-40 max-h-[min(430px,48vh)] gap-2 overflow-auto pr-1"
				id="projectDialogList"
				data-locale={language}
			>
				<div className="grid min-h-40 place-items-center rounded-lg border border-dashed border-border text-sm text-muted-foreground">
					{t("project.dialogEmpty")}
				</div>
			</div>
		);
	}

	return (
		<div
			className="grid min-h-40 max-h-[min(430px,48vh)] gap-2 overflow-auto pr-1"
			id="projectDialogList"
			data-locale={language}
		>
			{projectList.map((entry, index) => {
				const entryProject = entry.project;
				const updated = formatProjectDate(entry.updatedAt || entry.lastModifiedAt, language);
				const active = project?.id === entryProject.id;

				return (
					<button
						key={entryProject.id}
						type="button"
						className={cn(
							"grid min-h-20 grid-cols-[minmax(0,1fr)_auto] items-center gap-3 rounded-lg border border-border bg-muted/35 p-3 text-left transition-colors hover:bg-accent/60",
							active && "border-primary bg-accent",
						)}
						data-project-index={index}
						onClick={() => dispatchProjectDialogOpenProject(index)}
					>
						<div className="grid min-w-0 gap-1">
							<strong className="truncate text-sm text-foreground" title={entryProject.root}>
								{entryProject.name || entryProject.id}
							</strong>
							<small className="truncate text-xs text-muted-foreground" title={entryProject.root}>
								{shortPath(entryProject.root)}
							</small>
							<div className="flex flex-wrap gap-1">
								{updated ? <Badge variant="secondary">{t("project.dialogUpdated", { date: updated })}</Badge> : null}
								<Badge variant="secondary">
									{entry.hasManifest
										? t("project.dialogMediaCount", { count: entry.mediaCount || 0 })
										: t("project.dialogNoManifest")}
								</Badge>
							</div>
						</div>
						{active ? <Badge variant="default">{t("project.dialogActive")}</Badge> : null}
					</button>
				);
			})}
		</div>
	);
}

export function Dialogs() {
	const language = useAppStore((appState) => appState.language);
	const projectDialogOpen = useAppStore((appState) => appState.projectDialogOpen);
	const projectDialogName = useAppStore((appState) => appState.projectDialogName);
	const setProjectDialogName = useAppStore((appState) => appState.setProjectDialogName);
	const confirmDialog = useAppStore((appState) => appState.confirmDialog);
	const projectDialogNameRef = useRef<HTMLInputElement | null>(null);
	const closeProjectDialogRef = useRef<HTMLButtonElement | null>(null);
	const confirmDialogCancelRef = useRef<HTMLButtonElement | null>(null);

	useEffect(() => {
		if (projectDialogOpen) {
			(projectDialogNameRef.current || closeProjectDialogRef.current)?.focus();
		}
	}, [projectDialogOpen]);

	useEffect(() => {
		if (confirmDialog.open) {
			confirmDialogCancelRef.current?.focus();
		}
	}, [confirmDialog.open]);

	return (
		<>
			<div
				className="modal-backdrop fixed inset-0 z-[900] grid place-items-center bg-slate-950/35 p-5"
				id="projectDialog"
				hidden={!projectDialogOpen}
				data-locale={language}
			>
				<button
					type="button"
					className="absolute inset-0 size-full cursor-default border-0 bg-transparent p-0"
					aria-label={t("confirm.cancel")}
					onClick={dispatchProjectDialogClose}
				></button>
				<section
					className="relative z-10 grid max-h-[calc(100vh-40px)] w-[min(760px,100%)] gap-4 overflow-hidden rounded-lg border border-border bg-card p-5 text-card-foreground shadow-2xl"
					role="dialog"
					aria-modal="true"
					aria-labelledby="projectDialogTitle"
				>
					<header className="flex items-start justify-between gap-3">
						<div>
							<h3 id="projectDialogTitle" className="text-lg font-semibold">
								Select project
							</h3>
							<p className="mt-1 text-sm text-muted-foreground">Open an existing project or create a new one.</p>
						</div>
						<Button
							type="button"
							variant="ghost"
							size="icon"
							id="closeProjectDialog"
							ref={closeProjectDialogRef}
							aria-label="Close"
							title="Close"
							onClick={dispatchProjectDialogClose}
						>
							<X className="size-4" aria-hidden="true" />
						</Button>
					</header>
					<div className="grid grid-cols-[minmax(0,1fr)_auto] items-end gap-3 rounded-lg border border-border bg-muted/35 p-3 max-md:grid-cols-1">
						<label htmlFor="projectDialogName" className="grid gap-1.5 text-sm font-medium text-foreground">
							<span>New project name</span>
							<Input
								id="projectDialogName"
								ref={projectDialogNameRef}
								placeholder="e.g. client-a-edit"
								value={projectDialogName}
								onChange={(event) => setProjectDialogName(event.currentTarget.value)}
								onKeyDown={(event) => {
									if (event.key === "Enter") {
										event.preventDefault();
										dispatchProjectDialogCreate();
									}
								}}
							/>
						</label>
						<Button type="button" id="createProjectFromDialog" onClick={dispatchProjectDialogCreate}>
							<Plus className="size-4" aria-hidden="true" />
							Create
						</Button>
					</div>
					<div className="text-sm font-semibold text-accent-foreground">Project list</div>
					<ProjectDialogList />
					<footer className="flex justify-end">
						<Button type="button" variant="outline" id="cancelProjectDialog" onClick={dispatchProjectDialogClose}>
							Cancel
						</Button>
					</footer>
				</section>
			</div>
			<div
				className="modal-backdrop fixed inset-0 z-[900] grid place-items-center bg-slate-950/35 p-5"
				id="confirmDialog"
				hidden={!confirmDialog.open}
				data-locale={language}
			>
				<button
					type="button"
					className="absolute inset-0 size-full cursor-default border-0 bg-transparent p-0"
					aria-label={t("confirm.cancel")}
					onClick={() => dispatchConfirmDialogClose(false)}
				></button>
				<section
					className="relative z-10 grid w-[min(520px,100%)] gap-4 rounded-lg border border-border bg-card p-5 text-card-foreground shadow-2xl"
					role="dialog"
					aria-modal="true"
					aria-labelledby="confirmDialogTitle"
				>
					<header>
						<div>
							<h3 id="confirmDialogTitle" className="text-lg font-semibold">
								{confirmDialog.title}
							</h3>
							<p id="confirmDialogMessage" className="mt-1 text-sm text-muted-foreground">
								{confirmDialog.message}
							</p>
						</div>
					</header>
					<code
						id="confirmDialogDetail"
						className="block overflow-hidden whitespace-pre-line rounded-md border border-border bg-muted p-3 text-xs text-muted-foreground"
						title={confirmDialog.detail}
						hidden={!confirmDialog.detail}
					>
						{confirmDialog.detail}
					</code>
					<footer className="flex flex-wrap justify-end gap-2">
						<Button
							type="button"
							variant="outline"
							id="confirmDialogCancel"
							ref={confirmDialogCancelRef}
							onClick={() => dispatchConfirmDialogClose(false)}
						>
							{confirmDialog.cancelLabel || t("confirm.cancel")}
						</Button>
						<Button
							type="button"
							variant="destructive"
							id="confirmDialogConfirm"
							onClick={() => dispatchConfirmDialogClose(true)}
						>
							<Check className="size-4" aria-hidden="true" />
							{confirmDialog.confirmLabel || t("confirm.removeMaterialConfirm")}
						</Button>
					</footer>
				</section>
			</div>
		</>
	);
}
