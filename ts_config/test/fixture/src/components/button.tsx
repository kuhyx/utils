// Violations: you-might-not-need-an-effect (derived state via effect),
// jsx-a11y (img without alt, click on non-interactive div).
import { useEffect, useState } from "react";

export function Button({ label }: { label: string }): React.JSX.Element {
  const [upper, setUpper] = useState("");
  useEffect(() => {
    setUpper(label.toUpperCase());
  }, [label]);
  return (
    <div onClick={() => undefined}>
      <img src="x.png" />
      {upper}
    </div>
  );
}
