import { useEffect } from "react";
import { AppHeader, Dialogs, Overlays } from "./components/index.js";
import { SimpleWorkspace } from "./components/SimpleWorkspace.js";
import { FILE_DRAG_RESET_EVENT } from "./events.js";
import { useAppStore } from "./store/app-store.js";

function isFileDragEvent(event: DragEvent) {
	return Array.from(event.dataTransfer?.types || []).includes("Files");
}

function setCopyDropEffect(event: DragEvent) {
	if (event.dataTransfer) {
		event.dataTransfer.dropEffect = "copy";
	}
}

function setFileDragActive(active: boolean) {
	document.body.classList.toggle("file-drag-active", active);
}

function dispatchFileDragReset() {
	document.dispatchEvent(new CustomEvent(FILE_DRAG_RESET_EVENT));
}

function useGlobalFileDragUi() {
	useEffect(() => {
		let fileDragDepth = 0;
		const reset = () => {
			fileDragDepth = 0;
			setFileDragActive(false);
			dispatchFileDragReset();
		};
		const onDragEnter = (event: DragEvent) => {
			if (!isFileDragEvent(event)) {
				return;
			}
			fileDragDepth += 1;
			setFileDragActive(true);
		};
		const onDragOver = (event: DragEvent) => {
			if (!isFileDragEvent(event)) {
				return;
			}
			event.preventDefault();
			setCopyDropEffect(event);
			setFileDragActive(true);
		};
		const onDragLeave = (event: DragEvent) => {
			if (!isFileDragEvent(event)) {
				return;
			}
			fileDragDepth = Math.max(0, fileDragDepth - 1);
			if (fileDragDepth === 0) {
				setFileDragActive(false);
			}
		};
		const onDrop = (event: DragEvent) => {
			if (!isFileDragEvent(event)) {
				return;
			}
			event.preventDefault();
			reset();
		};

		window.addEventListener("dragenter", onDragEnter, true);
		window.addEventListener("dragover", onDragOver, true);
		window.addEventListener("dragleave", onDragLeave, true);
		window.addEventListener("drop", onDrop, true);
		window.addEventListener("blur", reset);
		return () => {
			window.removeEventListener("dragenter", onDragEnter, true);
			window.removeEventListener("dragover", onDragOver, true);
			window.removeEventListener("dragleave", onDragLeave, true);
			window.removeEventListener("drop", onDrop, true);
			window.removeEventListener("blur", reset);
			reset();
		};
	}, []);
}

export function App() {
	const appLocked = useAppStore((appState) => appState.appLocked);
	useGlobalFileDragUi();

	return (
		<>
			<div className="app-shell">
				<fieldset className="app-lock-scope" disabled={appLocked}>
					<AppHeader />
					<SimpleWorkspace />
				</fieldset>
			</div>
			<Overlays />
			<Dialogs />
		</>
	);
}
