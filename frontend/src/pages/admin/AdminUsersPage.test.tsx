import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { getRemovalImpact } from "@/admin/api";
import { fetchCurrentUser } from "@/auth/api";
import { testAdmin, testUser, testWorker } from "@/test/fixtures";
import { renderApp } from "@/test/renderApp";
import {
  createUser,
  listUsers,
  UserEmailConflictError,
  type UserPage,
  updateUser,
} from "@/users/api";

vi.mock("@/auth/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/auth/api")>()),
  fetchCurrentUser: vi.fn(),
}));

vi.mock("@/users/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/users/api")>()),
  listUsers: vi.fn(),
  createUser: vi.fn(),
  updateUser: vi.fn(),
}));

vi.mock("@/admin/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/admin/api")>()),
  getRemovalImpact: vi.fn(),
}));

const inactiveUser = { ...testWorker, is_active: false };

function page(items = [testUser, testWorker]): UserPage {
  return { items, total: items.length, limit: 20, offset: 0 };
}

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(fetchCurrentUser).mockResolvedValue(testAdmin);
  vi.mocked(listUsers).mockResolvedValue(page());
  vi.mocked(getRemovalImpact).mockResolvedValue({
    is_active: true,
    can_delete_permanently: true,
    blockers: [],
    effects: [],
  });
});

describe("AdminUsersPage", () => {
  it("renders the user list", async () => {
    renderApp("/admin/users");

    await screen.findByText(testUser.email);
    expect(screen.getByText(testWorker.email)).toBeTruthy();
    expect(screen.getByText("Project manager")).toBeTruthy();
    expect(screen.getByText("Worker")).toBeTruthy();
  });

  it("searches with a debounce", async () => {
    renderApp("/admin/users");
    await screen.findByText(testUser.email);
    vi.mocked(listUsers).mockClear();

    fireEvent.change(screen.getByLabelText("Search"), { target: { value: "ada" } });

    await waitFor(() =>
      expect(listUsers).toHaveBeenCalledWith(
        expect.objectContaining({ search: "ada" }),
      ),
    );
  });

  it("creates a user", async () => {
    vi.mocked(createUser).mockResolvedValue({ ...testUser, id: "new-id" });
    renderApp("/admin/users");
    await screen.findByText(testUser.email);

    fireEvent.click(screen.getByRole("button", { name: "New user" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText(/^name/i), { target: { value: "New Name" } });
    fireEvent.change(within(dialog).getByLabelText(/^email/i), {
      target: { value: "new@example.com" },
    });
    fireEvent.change(within(dialog).getByLabelText(/^password/i), {
      target: { value: "a-strong-password" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Create user" }));

    await waitFor(() =>
      expect(createUser).toHaveBeenCalledWith(
        {
          name: "New Name",
          email: "new@example.com",
          role: "worker",
          password: "a-strong-password",
        },
        expect.anything(),
      ),
    );
  });

  it("shows a field error when the email is already taken", async () => {
    vi.mocked(createUser).mockRejectedValue(new UserEmailConflictError());
    renderApp("/admin/users");
    await screen.findByText(testUser.email);

    fireEvent.click(screen.getByRole("button", { name: "New user" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText(/^name/i), { target: { value: "Dup" } });
    fireEvent.change(within(dialog).getByLabelText(/^email/i), {
      target: { value: "dup@example.com" },
    });
    fireEvent.change(within(dialog).getByLabelText(/^password/i), {
      target: { value: "a-strong-password" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Create user" }));

    expect(await within(dialog).findByText("A user with this email already exists")).toBeTruthy();
  });

  it("edit sends only the changed fields", async () => {
    vi.mocked(updateUser).mockResolvedValue(testWorker);
    renderApp("/admin/users");
    const row = (await screen.findByText(testWorker.email)).closest("tr")!;

    fireEvent.click(within(row).getByRole("button", { name: "Actions" }));
    fireEvent.click(await screen.findByRole("menuitem", { name: "Edit" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText(/^name/i), { target: { value: "Renamed" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save changes" }));

    await waitFor(() =>
      expect(updateUser).toHaveBeenCalledWith(testWorker.id, { name: "Renamed" }),
    );
  });

  it("restores an inactive user", async () => {
    vi.mocked(listUsers).mockResolvedValue(page([testUser, inactiveUser]));
    vi.mocked(updateUser).mockResolvedValue({ ...inactiveUser, is_active: true });
    renderApp("/admin/users");
    const row = (await screen.findByText(inactiveUser.email)).closest("tr")!;

    fireEvent.click(within(row).getByRole("button", { name: "Actions" }));
    fireEvent.click(await screen.findByRole("menuitem", { name: "Restore" }));

    await waitFor(() =>
      expect(updateUser).toHaveBeenCalledWith(inactiveUser.id, { is_active: true }),
    );
  });

  it("opens the remove dialog from the row menu", async () => {
    renderApp("/admin/users");
    const row = (await screen.findByText(testWorker.email)).closest("tr")!;

    fireEvent.click(within(row).getByRole("button", { name: "Actions" }));
    fireEvent.click(await screen.findByRole("menuitem", { name: "Remove…" }));

    expect(await screen.findByRole("heading", { name: "Remove user" })).toBeTruthy();
  });

  it("disables edit and remove on the signed-in admin's own row", async () => {
    vi.mocked(listUsers).mockResolvedValue(page([testAdmin, testWorker]));
    renderApp("/admin/users");
    const row = (await screen.findByText(testAdmin.email)).closest("tr")!;

    fireEvent.click(within(row).getByRole("button", { name: "Actions" }));

    const editItem = await screen.findByRole("menuitem", { name: "Edit" });
    const removeItem = await screen.findByRole("menuitem", { name: "Remove…" });
    expect(editItem.getAttribute("data-disabled")).toBe("true");
    expect(removeItem.getAttribute("data-disabled")).toBe("true");
  });
});
