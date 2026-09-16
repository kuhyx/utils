// Violation: design-system must not import services.
import { fetchUser } from "@/services/api";

export const theme = { primary: String(fetchUser("x")) };
