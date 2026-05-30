import {
	PROJECT_CHANGE_EVENT,
	PROJECT_COPY_ASSETS_EVENT,
	PROJECT_CREATE_EVENT,
	PROJECT_DELETE_EVENT,
	PROJECT_FORM_CHANGE_EVENT,
} from "../events.js";
import { t } from "../i18n.js";
import { projectIdFromName } from "../preview.js";
import { useAppStore } from "../store/app-store.js";

type PanelProps = {
	readonly hidden?: boolean;
};

function dispatchProjectAction(eventName: string) {
	document.dispatchEvent(new CustomEvent(eventName));
}

function dispatchProjectFormChange() {
	document.dispatchEvent(new CustomEvent(PROJECT_FORM_CHANGE_EVENT));
}

export function ProjectPanel({ hidden = false }: PanelProps) {
	const language = useAppStore((appState) => appState.language);
	const project = useAppStore((appState) => appState.project);
	const projectDraft = useAppStore((appState) => appState.projectDraft);
	const setProjectDraft = useAppStore((appState) => appState.setProjectDraft);
	const appLocked = useAppStore((appState) => appState.appLocked);
	const projectStatus = project ? t("project.ready", { name: project.name }) : t("project.noProjectSelected");
	const projectName = project?.name || t("project.noProjectSelected");

	return (
		<div className="panel wide" data-panel="assets" data-locale={language} hidden={hidden}>
			<div className="panel-heading">
				<h3>{t("project.heading")}</h3>
				<span id="projectLabel">{projectStatus}</span>
			</div>
			<div className="project-card">
				<div className="project-current">
					<span>{t("project.current")}</span>
					<strong id="projectNamePreview">{projectName}</strong>
				</div>
				<label>
					{t("project.name")}
					<input
						id="projectName"
						placeholder="例: client-a-edit"
						value={projectDraft.name}
						onChange={(event) => {
							const name = event.currentTarget.value;
							setProjectDraft({ name, id: projectIdFromName(name) });
							dispatchProjectFormChange();
						}}
					/>
				</label>
				<input id="projectId" type="hidden" value={projectDraft.id} readOnly />
				<div className="project-actions">
					<button
						type="button"
						className="primary-button"
						id="createProject"
						disabled={appLocked}
						onClick={() => dispatchProjectAction(PROJECT_CREATE_EVENT)}
					>
						{t("project.createSelect")}
					</button>
					<button
						type="button"
						id="changeProject"
						disabled={appLocked}
						onClick={() => dispatchProjectAction(PROJECT_CHANGE_EVENT)}
					>
						{t("project.change")}
					</button>
					<button
						type="button"
						id="copyProjectAssets"
						disabled={appLocked}
						onClick={() => dispatchProjectAction(PROJECT_COPY_ASSETS_EVENT)}
					>
						{t("project.copySelectedSources")}
					</button>
					<button
						type="button"
						className="danger-button"
						id="deleteProject"
						disabled={appLocked || !project}
						onClick={() => dispatchProjectAction(PROJECT_DELETE_EVENT)}
					>
						{t("project.delete")}
					</button>
				</div>
			</div>
		</div>
	);
}
