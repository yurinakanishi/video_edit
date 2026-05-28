import { getAppState } from "./store/app-store.js";

export function log(message: string, data?: any) {
	const line = data ? `${message} ${JSON.stringify(data)}` : message;
	getAppState().appendEventLogLine(`${new Date().toLocaleTimeString()}  ${line}`);
}
