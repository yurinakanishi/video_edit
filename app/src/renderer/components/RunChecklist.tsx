import { useAppStore } from "../store/app-store.js";

export function RunChecklist() {
	const items = useAppStore((store) => store.runChecklist);

	return (
		<ul id="runChecklist">
			{items.map((item) => (
				<li className={item.kind} key={`${item.kind}-${item.text}`}>
					{item.text}
				</li>
			))}
		</ul>
	);
}
