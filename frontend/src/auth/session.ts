export type AuthStatus = "anonymous" | "authenticating" | "authenticated" | "expired";

export interface Principal {
  subject_id: string;
  display_name: string;
  roles: string[];
  permissions: string[];
  auth_method: "development_jwt" | "oidc_jwt";
  issued_at: string;
  expires_at: string;
}

export interface SessionSnapshot {
  accessToken: string | null;
  principal: Principal | null;
  status: AuthStatus;
}

let snapshot: SessionSnapshot = { accessToken: null, principal: null, status: "anonymous" };
const listeners = new Set<() => void>();

function publish(next: SessionSnapshot): void {
  snapshot = next;
  listeners.forEach((listener) => listener());
}

export function getSessionSnapshot(): SessionSnapshot {
  return snapshot;
}

export function subscribeToSession(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function setAuthenticating(): void {
  publish({ accessToken: null, principal: null, status: "authenticating" });
}

export function setAuthenticatedSession(accessToken: string, principal: Principal): void {
  publish({ accessToken, principal, status: "authenticated" });
}

export function expireSession(): void {
  publish({ accessToken: null, principal: null, status: "expired" });
}

export function clearSession(): void {
  publish({ accessToken: null, principal: null, status: "anonymous" });
}

export function isSessionActive(): boolean {
  return snapshot.status === "authenticated" && Boolean(snapshot.accessToken);
}
