export function codexErrorMessage(error: any): string {
	if (!error) {
		return "";
	}
	const raw = typeof error === "string" ? error : error.message || error.error?.message || error.codexErrorInfo || "";
	if (!raw) {
		return "";
	}
	try {
		const parsed = JSON.parse(raw);
		return codexErrorMessage(parsed.error || parsed) || raw;
	} catch {
		return String(raw);
	}
}
