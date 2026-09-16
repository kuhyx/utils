// Clean: the JSX map idiom with an implicit multi-line return, which the
// React layer exempts from unicorn/consistent-arrow-return-style.
import { useRef } from "react";

export function ItemList({ items }: { readonly items: readonly string[] }): React.JSX.Element {
  return (
    <ul>
      {items.map((item) => (
        <li key={item}>
          {item}
        </li>
      ))}
    </ul>
  );
}

/** Clean: a `*Ref` name satisfies both unicorn and @eslint-react. */
export function Focused(): React.JSX.Element {
  const inputRef = useRef<HTMLInputElement>(null);
  return <input ref={inputRef} />;
}
