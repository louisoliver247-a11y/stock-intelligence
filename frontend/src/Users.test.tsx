import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { LoginForm, Users } from "./Users";

afterEach(() => vi.restoreAllMocks());

describe("user management", () => {
  it("signs in with email and password", async () => {
    const fetcher = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ token: "session" })));
    const login = vi.fn();
    render(<LoginForm onLogin={login} />);
    fireEvent.change(screen.getByLabelText("Email address"), { target: { value: "test@example.com" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "test-password" } });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() => expect(login).toHaveBeenCalledWith("session"));
    expect(fetcher.mock.calls[0][0]).toBe("/api/auth/login");
    expect(screen.getByLabelText("Password")).toHaveValue("");
  });

  it("creates an account and deletes it after confirmation", async () => {
    const user = { id: "123", email: "new@example.com", role: "user", created_at: "2026-01-01" };
    const fetcher = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response("[]"))
      .mockResolvedValueOnce(new Response(JSON.stringify(user)))
      .mockResolvedValueOnce(new Response(JSON.stringify([user])))
      .mockResolvedValueOnce(new Response('{"ok":true}'))
      .mockResolvedValueOnce(new Response("[]"));
    vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<Users apiKey="admin" />);
    fireEvent.change(await screen.findByLabelText("New user email"), { target: { value: user.email } });
    fireEvent.change(screen.getByLabelText("New user password"), { target: { value: "test-password" } });
    fireEvent.click(screen.getByRole("button", { name: "Create user" }));
    const remove = await screen.findByRole("button", { name: "Delete" });
    fireEvent.click(remove);
    await waitFor(() => expect(screen.queryByText(user.email)).not.toBeInTheDocument());
    expect(fetcher.mock.calls[3][0]).toBe("/api/users/123");
    expect(fetcher.mock.calls[3][1]?.method).toBe("DELETE");
  });
});
