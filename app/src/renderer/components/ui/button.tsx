import { cva, type VariantProps } from "class-variance-authority";
import { type ButtonHTMLAttributes, forwardRef } from "react";
import { cn } from "../../lib/utils.js";

const buttonVariants = cva(
	"inline-flex shrink-0 items-center justify-center gap-2 whitespace-nowrap rounded-md border text-sm font-medium " +
		"transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring " +
		"focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50",
	{
		variants: {
			variant: {
				default: "border-transparent bg-primary text-primary-foreground shadow-sm hover:bg-primary/90",
				secondary: "border-border bg-secondary text-secondary-foreground hover:bg-secondary/80",
				outline: "border-border bg-background hover:bg-accent hover:text-accent-foreground",
				ghost: "border-transparent bg-transparent hover:bg-accent hover:text-accent-foreground",
				destructive:
					"border-destructive/20 bg-destructive text-destructive-foreground shadow-sm hover:bg-destructive/90",
			},
			size: {
				default: "h-9 px-4 py-2",
				sm: "h-8 px-3 text-xs",
				lg: "h-10 px-5",
				icon: "h-9 w-9 p-0",
			},
		},
		defaultVariants: {
			variant: "default",
			size: "default",
		},
	},
);

export type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & VariantProps<typeof buttonVariants>;

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(({ className, variant, size, ...props }, ref) => (
	<button ref={ref} className={cn(buttonVariants({ variant, size }), className)} {...props} />
));
Button.displayName = "Button";

export { buttonVariants };
