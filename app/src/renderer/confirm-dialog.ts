import { t } from "./i18n.js";
import { getAppState } from "./store/app-store.js";

type ConfirmActionOptions = {
	readonly title: string;
	readonly message: string;
	readonly detail?: string;
	readonly confirmLabel?: string;
	readonly cancelLabel?: string;
};

export function createConfirmDialogController() {
	let pendingConfirmResolve: ((confirmed: boolean) => void) | null = null;

	function setConfirmDialogOpen(open: boolean) {
		getAppState().setConfirmDialog({ open });
	}

	function closeConfirmDialog(confirmed: boolean) {
		setConfirmDialogOpen(false);
		const resolve = pendingConfirmResolve;
		pendingConfirmResolve = null;
		resolve?.(confirmed);
	}

	function confirmAction(options: ConfirmActionOptions) {
		getAppState().setConfirmDialog({
			title: options.title,
			message: options.message,
			detail: options.detail || "",
			confirmLabel: options.confirmLabel || t("confirm.removeMaterialConfirm"),
			cancelLabel: options.cancelLabel || t("confirm.cancel"),
		});
		setConfirmDialogOpen(true);
		return new Promise<boolean>((resolve) => {
			pendingConfirmResolve = resolve;
		});
	}

	return {
		closeConfirmDialog,
		confirmAction,
		setConfirmDialogOpen,
	};
}
