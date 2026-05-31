import { FolderOpen, Languages, Video } from "lucide-react";
import { useEffect, useRef } from "react";
import { LANGUAGE_CHANGE_EVENT, PROJECT_CHANGE_EVENT } from "../events.js";
import { localizePlainText, t } from "../i18n.js";
import { cn } from "../lib/utils.js";
import { shortPath } from "../preview.js";
import { useAppStore } from "../store/app-store.js";
import { Button } from "./ui/button.js";

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
		<header className="sticky top-0 z-20 border-b border-border/80 bg-card/90 px-4 py-3 shadow-sm backdrop-blur md:px-6">
			<div className="grid items-center gap-3 lg:grid-cols-[minmax(220px,auto)_minmax(0,1fr)_auto]">
				<div className="grid min-w-0 grid-cols-[44px_minmax(0,1fr)] items-center gap-3">
					<div className="grid size-11 place-items-center rounded-lg bg-primary text-primary-foreground shadow-sm">
						<Video className="size-5" aria-hidden="true" />
					</div>
					<div className="min-w-0">
						<h1 className="text-lg font-semibold tracking-normal text-foreground">Video Edit</h1>
						<p id="workspacePath" className="truncate text-xs text-muted-foreground" title={env?.videoEditRoot || ""}>
							{project ? shortPath(project.root) : t("app.workspaceLabel")}
						</p>
					</div>
				</div>
				<div className="min-w-0 rounded-md border border-border/70 bg-muted/55 px-3 py-2 lg:justify-self-center lg:text-center">
					<span className="block text-[11px] font-semibold uppercase tracking-normal text-muted-foreground">
						Project
					</span>
					<strong
						className="block max-w-full truncate text-sm text-accent-foreground lg:max-w-[44vw]"
						title={project?.root || ""}
					>
						{project?.name || "-"}
					</strong>
				</div>
				<div className="flex min-w-0 flex-wrap items-center gap-2 lg:justify-end">
					<Button type="button" variant="outline" size="sm" disabled={appLocked} onClick={dispatchProjectChange}>
						<FolderOpen className="size-4" aria-hidden="true" />
						開く
					</Button>
					<div
						className="flex min-w-0 items-center gap-2 rounded-md border border-border bg-background px-3 py-2 text-sm text-muted-foreground"
						id="serverStatus"
					>
						<span
							className={cn("size-2.5 shrink-0 rounded-full bg-slate-400", {
								"bg-primary": statusKind === "ready",
								"bg-amber-500": statusKind === "busy",
							})}
						></span>
						<span className="max-w-[220px] truncate">{localizePlainText(statusText)}</span>
					</div>
					<div className="relative" ref={languageSwitcherRef}>
						<Button
							type="button"
							id="languageMenuButton"
							variant="outline"
							size="icon"
							aria-label={t("language.aria.display")}
							aria-haspopup="true"
							aria-expanded={languageMenuOpen ? "true" : "false"}
							title={t("language.display")}
							onClick={(event) => {
								event.stopPropagation();
								setLanguageMenuOpen(!languageMenuOpen);
							}}
						>
							<Languages className="size-4" aria-hidden="true" />
						</Button>
						<div
							className="language-popover absolute right-0 top-[calc(100%+8px)] z-30 grid min-w-28 gap-1 rounded-lg border border-border bg-popover p-1 text-popover-foreground shadow-lg"
							id="languagePopover"
							hidden={!languageMenuOpen}
							role="menu"
						>
							{DISPLAY_LANGUAGES.map((displayLanguage) => (
								<Button
									key={displayLanguage.code}
									type="button"
									variant={displayLanguage.code === currentLanguage ? "secondary" : "ghost"}
									size="sm"
									className="justify-start"
									data-language={displayLanguage.code}
									role="menuitem"
									onClick={(event) => {
										event.stopPropagation();
										dispatchLanguageChange(displayLanguage.code);
									}}
								>
									{displayLanguage.label}
								</Button>
							))}
						</div>
					</div>
				</div>
			</div>
		</header>
	);
}
