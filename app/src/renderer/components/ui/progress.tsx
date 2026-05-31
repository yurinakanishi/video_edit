import type { HTMLAttributes } from "react";
import { cn } from "../../lib/utils.js";

type ProgressProps = HTMLAttributes<HTMLDivElement> & {
	readonly value: number;
	readonly fillId?: string;
};

export function Progress({ className, value, fillId, ...props }: ProgressProps) {
	const safeValue = Math.max(0, Math.min(100, Number(value || 0)));
	return (
		<div className={cn("relative h-2.5 w-full overflow-hidden rounded-full bg-secondary", className)} {...props}>
			<div
				id={fillId}
				className="h-full rounded-full bg-primary transition-all"
				style={{ width: `${safeValue}%` }}
			></div>
		</div>
	);
}
