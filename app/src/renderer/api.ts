import type { EditAppApi } from "./types.js";

export const editApp = (window as unknown as { editApp: EditAppApi }).editApp;
