import { useEffect, useRef } from "react";
import { LANGUAGE_CHANGE_EVENT, WORKFLOW_SECTION_CHANGE_EVENT } from "../events.js";
import { localizePlainText, t } from "../i18n.js";
import { useAppStore } from "../store/app-store.js";

const WORKFLOW_STEPS = [
	{ section: "assets", labelKey: "nav.assets" },
	{ section: "edit", labelKey: "nav.edit" },
	{ section: "style", labelKey: "nav.style" },
	{ section: "workflow", labelKey: "nav.workflow" },
	{ section: "run", labelKey: "nav.codex" },
] as const;

const DISPLAY_LANGUAGES = [
	{ code: "ja", label: "日本語" },
	{ code: "en", label: "EN" },
] as const;

function dispatchWorkflowSectionChange(section: string) {
	document.dispatchEvent(new CustomEvent(WORKFLOW_SECTION_CHANGE_EVENT, { detail: { section } }));
}

function dispatchLanguageChange(language: string) {
	document.dispatchEvent(new CustomEvent(LANGUAGE_CHANGE_EVENT, { detail: { language } }));
}

export function AppHeader() {
	const activeSection = useAppStore((appState) => appState.activeSection);
	const currentLanguage = useAppStore((appState) => appState.language);
	const languageMenuOpen = useAppStore((appState) => appState.languageMenuOpen);
	const setLanguageMenuOpen = useAppStore((appState) => appState.setLanguageMenuOpen);
	const env = useAppStore((appState) => appState.env);
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
						{t("app.workspaceLabel")}
					</p>
				</div>
			</div>
			<div className="steps" aria-label={t("nav.aria.workflow")} role="tablist">
				{WORKFLOW_STEPS.map((step) => (
					<button
						key={step.section}
						type="button"
						className={`step-button${step.section === activeSection ? " active" : ""}`}
						data-section={step.section}
						role="tab"
						aria-selected={step.section === activeSection ? "true" : "false"}
						onClick={() => dispatchWorkflowSectionChange(step.section)}
					>
						{t(step.labelKey)}
					</button>
				))}
			</div>
			<div className="header-tools">
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
