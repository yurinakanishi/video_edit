export type SelectOption = readonly [value: string, label: string];

export function SelectOptions({ options }: { readonly options: readonly SelectOption[] }) {
	return options.map(([value, label]) => (
		<option key={value} value={value}>
			{label}
		</option>
	));
}
