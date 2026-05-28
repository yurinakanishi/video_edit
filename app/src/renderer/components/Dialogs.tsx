import { useEffect, useRef } from "react";
import {
	CONFIRM_DIALOG_CLOSE_EVENT,
	PROJECT_DIALOG_CLOSE_EVENT,
	PROJECT_DIALOG_CREATE_EVENT,
	PROJECT_DIALOG_OPEN_PROJECT_EVENT,
} from "../events.js";
import { t } from "../i18n.js";
import { useAppStore } from "../store/app-store.js";

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
			<div className="project-dialog-list" id="projectDialogList" data-locale={language}>
				<div className="project-dialog-empty">{t("project.dialogLoading")}</div>
			</div>
		);
	}

	if (!projectList.length) {
		return (
			<div className="project-dialog-list" id="projectDialogList" data-locale={language}>
				<div className="project-dialog-empty">{t("project.dialogEmpty")}</div>
			</div>
		);
	}

	return (
		<div className="project-dialog-list" id="projectDialogList" data-locale={language}>
			{projectList.map((entry, index) => {
				const entryProject = entry.project;
				const updated = formatProjectDate(entry.updatedAt || entry.lastModifiedAt, language);
				const active = project?.id === entryProject.id;

				return (
					<button
						key={entryProject.id}
						type="button"
						className={`project-list-item${active ? " active" : ""}`}
						data-project-index={index}
						onClick={() => dispatchProjectDialogOpenProject(index)}
					>
						<div className="project-list-main">
							<strong title={entryProject.root}>{entryProject.name || entryProject.id}</strong>
							<small title={entryProject.root}>{shortPath(entryProject.root)}</small>
							<div className="project-list-meta">
								{updated ? <span>{t("project.dialogUpdated", { date: updated })}</span> : null}
								<span>
									{entry.hasManifest
										? t("project.dialogMediaCount", { count: entry.mediaCount || 0 })
										: t("project.dialogNoManifest")}
								</span>
							</div>
						</div>
						{active ? <span className="project-active-badge">{t("project.dialogActive")}</span> : null}
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
			<div className="modal-backdrop" id="projectDialog" hidden={!projectDialogOpen} data-locale={language}>
				<button
					type="button"
					className="modal-dismiss"
					aria-label={t("confirm.cancel")}
					onClick={dispatchProjectDialogClose}
				></button>
				<section className="project-dialog" role="dialog" aria-modal="true" aria-labelledby="projectDialogTitle">
					<header className="project-dialog-header">
						<div>
							<h3 id="projectDialogTitle">Select project</h3>
							<p>Open an existing project or create a new one.</p>
						</div>
						<button
							type="button"
							className="icon-button"
							id="closeProjectDialog"
							ref={closeProjectDialogRef}
							aria-label="Close"
							title="Close"
							onClick={dispatchProjectDialogClose}
						>
							×
						</button>
					</header>
					<div className="project-dialog-create">
						<label>
							New project name
							<input
								id="projectDialogName"
								ref={projectDialogNameRef}
								placeholder="e.g. interview-client-a"
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
						<button
							type="button"
							className="primary-button"
							id="createProjectFromDialog"
							onClick={dispatchProjectDialogCreate}
						>
							Create
						</button>
					</div>
					<div className="project-dialog-list-heading">Project list</div>
					<ProjectDialogList />
					<footer className="project-dialog-footer">
						<button type="button" id="cancelProjectDialog" onClick={dispatchProjectDialogClose}>
							Cancel
						</button>
					</footer>
				</section>
			</div>
			<div className="modal-backdrop" id="confirmDialog" hidden={!confirmDialog.open} data-locale={language}>
				<button
					type="button"
					className="modal-dismiss"
					aria-label={t("confirm.cancel")}
					onClick={() => dispatchConfirmDialogClose(false)}
				></button>
				<section className="confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="confirmDialogTitle">
					<header className="project-dialog-header">
						<div>
							<h3 id="confirmDialogTitle">{confirmDialog.title}</h3>
							<p id="confirmDialogMessage">{confirmDialog.message}</p>
						</div>
					</header>
					<code id="confirmDialogDetail" title={confirmDialog.detail} hidden={!confirmDialog.detail}>
						{confirmDialog.detail}
					</code>
					<footer className="project-dialog-footer">
						<button
							type="button"
							id="confirmDialogCancel"
							ref={confirmDialogCancelRef}
							onClick={() => dispatchConfirmDialogClose(false)}
						>
							{confirmDialog.cancelLabel || t("confirm.cancel")}
						</button>
						<button
							type="button"
							className="danger-button"
							id="confirmDialogConfirm"
							onClick={() => dispatchConfirmDialogClose(true)}
						>
							{confirmDialog.confirmLabel || t("confirm.removeMaterialConfirm")}
						</button>
					</footer>
				</section>
			</div>
		</>
	);
}
