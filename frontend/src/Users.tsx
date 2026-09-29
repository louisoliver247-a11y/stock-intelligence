import { useEffect, useState } from "react";
import { request } from "./api";

export function LoginForm({ onLogin }: { onLogin: (token: string) => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  return <section className="panel"><h2>Sign in</h2><form onSubmit={async e => {
    e.preventDefault(); setBusy(true); setError("");
    try {
      const result = await request<{token: string}>("/auth/login", "", { email, password });
      setPassword(""); onLogin(result.token);
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }}>
    <label>Email<input type="email" autoComplete="username" required value={email} onChange={e => setEmail(e.target.value)} /></label>
    <label>Password<input type="password" autoComplete="current-password" required minLength={8} maxLength={128} value={password} onChange={e => setPassword(e.target.value)} /></label>
    <button className="primary" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
    {error && <p role="alert">{error}</p>}
  </form></section>;
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
