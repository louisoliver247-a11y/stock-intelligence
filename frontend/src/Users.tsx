import { useEffect, useState } from "react";
import { request } from "./api";

export function LoginForm({ onLogin }: { onLogin: (token: string) => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const messages: Record<string, string> = {
    INVALID_EMAIL_OR_PASSWORD: "The email or password is incorrect. Please try again.",
    TOO_MANY_LOGIN_ATTEMPTS_TRY_IN_5_MINUTES: "Too many attempts. Please try again in five minutes.",
  };
  return <form className="signin-form" onSubmit={async e => {
    e.preventDefault(); if (busy) return; setBusy(true); setError("");
    try {
      const result = await request<{token: string}>("/auth/login", "", { email, password });
      if (!result.token) throw new Error("INVALID_LOGIN_RESPONSE");
      setPassword(""); onLogin(result.token);
    } catch (e) {
      setError(messages[(e as Error).message] ?? "Unable to sign in right now. Please try again.");
    } finally { setBusy(false); }
  }}>
    <label htmlFor="signin-email">Email address</label>
    <input id="signin-email" type="email" placeholder="you@example.com" autoComplete="username" required maxLength={254} value={email} onChange={e => setEmail(e.target.value)} disabled={busy} />
    <label htmlFor="signin-password">Password</label>
    <input id="signin-password" type="password" placeholder="Enter your password" autoComplete="current-password" required minLength={8} maxLength={128} value={password} onChange={e => setPassword(e.target.value)} disabled={busy} />
    {error && <p role="alert" className="signin-error">{error}</p>}
    <button className="primary signin-submit" disabled={busy}>{busy ? "Signing in..." : "Sign in"}<span aria-hidden="true">&rarr;</span></button>
  </form>;
}

interface User { id: string; email: string; role: string; created_at: string }
export function Users({ apiKey }: { apiKey: string }) {
  const [users, setUsers] = useState<User[]>([]);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("user");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [allowed, setAllowed] = useState(false);
  const [busy, setBusy] = useState(false);
  const refresh = async () => { setUsers(await request<User[]>("/users", apiKey)); setAllowed(true); };
  useEffect(() => { void refresh().catch(e => setError(e.message)); }, [apiKey]);
  async function change(work: () => Promise<void>) {
    setBusy(true); setError(""); setNotice("");
    try { await work(); await refresh(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  return <section className="panel"><h2>User management</h2>
    <p>Administrators manage users and market data. Regular users have read-only market access.</p>
    {error && <p role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
    {allowed && <><form onSubmit={e => { e.preventDefault(); void change(async () => {
      await request("/users", apiKey, { email, password, role }); setEmail(""); setPassword(""); setNotice("User created.");
    }); }}>
      <label>New user email<input type="email" required maxLength={254} value={email} onChange={e => setEmail(e.target.value)} /></label>
      <label>New user password<input type="password" autoComplete="new-password" required minLength={8} maxLength={128} value={password} onChange={e => setPassword(e.target.value)} /></label>
      <label>Access<select value={role} onChange={e => setRole(e.target.value)}><option value="user">User (read only)</option><option value="admin">Administrator</option></select></label>
      <button disabled={busy} className="primary">Create user</button>
    </form><table><thead><tr><th>Email</th><th>Access</th><th>Created</th><th>Action</th></tr></thead>
      <tbody>{users.map(user => <tr key={user.id}><td>{user.email}</td><td>{user.role}</td><td>{new Date(user.created_at).toLocaleDateString()}</td>
        <td><button disabled={busy} onClick={() => {
          if (window.confirm(`Delete ${user.email}? Their access will be revoked immediately.`)) void change(async () => {
            await request(`/users/${user.id}`, apiKey, undefined, "DELETE"); setNotice("User deleted.");
          });
        }}>Delete</button></td></tr>)}</tbody></table></>}
  </section>;
}
