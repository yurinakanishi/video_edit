import { useEffect } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App.js";
import "./styles.css";
import { startRenderer } from "./renderer.js";

const root = document.getElementById("root");

if (!root) {
	throw new Error("renderer root element was not found");
}

function RendererRoot() {
	useEffect(() => {
		void startRenderer();
	}, []);

	return <App />;
}

createRoot(root).render(<RendererRoot />);
