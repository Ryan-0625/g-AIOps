/**
 * Authentication for Worker WebSocket and Brain REST connections.
 *
 * Uses a shared cluster token carried in the Authorization header as
 * "Bearer <token>".  Token mismatch → connection rejected with AUTH_FAILED.
 */

export function authenticate(token: string, expectedToken: string): boolean {
  return token === expectedToken;
}

export function extractBearer(authHeader: string | undefined): string | null {
  if (!authHeader) return null;
  const parts = authHeader.split(" ");
  if (parts.length !== 2 || parts[0] !== "Bearer") return null;
  return parts[1];
}
