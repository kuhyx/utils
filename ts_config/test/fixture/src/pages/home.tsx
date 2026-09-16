// Violation: a production page importing a mock (boundaries).
import { mockUser } from "@/mocks/user";
import { fetchUser } from "@/services/api";

export function Home(): React.JSX.Element {
  return <p>{String(fetchUser(mockUser.id))}</p>;
}
