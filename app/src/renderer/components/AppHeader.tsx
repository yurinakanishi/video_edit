import { useEffect, useRef } from "react";
import { LANGUAGE_CHANGE_EVENT, PROJECT_CHANGE_EVENT } from "../events.js";
import { localizePlainText, t } from "../i18n.js";
import { shortPath } from "../preview.js";
import { useAppStore } from "../store/app-store.js";

const DISPLAY_LANGUAGES = [
	{ code: "ja", label: "日本語" },
	{ code: "en", label: "EN" },
] as const;

function dispatchLanguageChange(language: string) {
	document.dispatchEvent(new CustomEvent(LANGUAGE_CHANGE_EVENT, { detail: { language } }));
}

function dispatchProjectChange() {
	document.dispatchEvent(new CustomEvent(PROJECT_CHANGE_EVENT));
}

export function AppHeader() {
	const currentLanguage = useAppStore((appState) => appState.language);
	const languageMenuOpen = useAppStore((appState) => appState.languageMenuOpen);
	const setLanguageMenuOpen = useAppStore((appState) => appState.setLanguageMenuOpen);
	const env = useAppStore((appState) => appState.env);
	const project = useAppStore((appState) => appState.project);
	const appLocked = useAppStore((appState) => appState.appLocked);
	const statusText = useAppStore((appState) => appState.statusText);
	const statusKind = useAppStore((appState) => appState.statusKind);
	const languageSwitcherRef = useRef<HTMLDivElement | null>(null);

	useEffect(() => {
		if (!languageMenuOpen) {
			return;
		}
		const closeOnOutsideInteraction = (event: MouseEvent | KeyboardEvent) => {
			if (event instanceof KeyboardEvent) {
				if (event.key === "Escape") {
					setLanguageMenuOpen(false);
				}
				return;
			}
			if (!languageSwitcherRef.current?.contains(event.target as Node)) {
				setLanguageMenuOpen(false);
			}
		};
		document.addEventListener("click", closeOnOutsideInteraction);
		document.addEventListener("keydown", closeOnOutsideInteraction);
		return () => {
			document.removeEventListener("click", closeOnOutsideInteraction);
			document.removeEventListener("keydown", closeOnOutsideInteraction);
		};
	}, [languageMenuOpen, setLanguageMenuOpen]);

	return (
		<header className="app-header">
			<div className="brand-block">
				<div className="app-mark">VE</div>
				<div>
					<h1>Video Edit</h1>
					<p id="workspacePath" title={env?.videoEditRoot || ""}>
						{project ? shortPath(project.root) : t("app.workspaceLabel")}
					</p>
				</div>
			</div>
			<div className="header-project">
				<span>Project</span>
				<strong title={project?.root || ""}>{project?.name || "-"}</strong>
			</div>
			<div className="header-tools">
				<button type="button" disabled={appLocked} onClick={dispatchProjectChange}>
					開く
				</button>
				<div className="server-status" id="serverStatus">
					<span className={`status-dot ${statusKind}`}></span>
					<span>{localizePlainText(statusText)}</span>
				</div>
				<div className="language-switcher" ref={languageSwitcherRef}>
					<button
						type="button"
						id="languageMenuButton"
						className="language-menu-button"
						aria-label={t("language.aria.display")}
						aria-haspopup="true"
						aria-expanded={languageMenuOpen ? "true" : "false"}
						title={t("language.display")}
						onClick={(event) => {
							event.stopPropagation();
							setLanguageMenuOpen(!languageMenuOpen);
						}}
					>
						i18n
					</button>
					<div className="language-popover" id="languagePopover" hidden={!languageMenuOpen} role="menu">
						{DISPLAY_LANGUAGES.map((displayLanguage) => (
							<button
								key={displayLanguage.code}
								type="button"
								className={displayLanguage.code === currentLanguage ? "selected" : undefined}
								data-language={displayLanguage.code}
								role="menuitem"
								onClick={(event) => {
									event.stopPropagation();
									dispatchLanguageChange(displayLanguage.code);
								}}
							>
								{displayLanguage.label}
							</button>
						))}
					</div>
				</div>
			</div>
		</header>
	);
}
