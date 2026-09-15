import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { getRemovalImpact } from "@/admin/api";
import { fetchCurrentUser } from "@/auth/api";
import { listCustomers } from "@/customers/api";
import {
  createProject,
  listProjects,
  ProjectRuleError,
  type Project,
  type ProjectPage,
  updateProject,
} from "@/projects/api";
import { testAdmin, testCustomer, testProject } from "@/test/fixtures";
import { renderApp } from "@/test/renderApp";
import { searchUserDirectory } from "@/users/api";

vi.mock("@/auth/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/auth/api")>()),
  fetchCurrentUser: vi.fn(),
}));

vi.mock("@/projects/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/projects/api")>()),
  listProjects: vi.fn(),
  createProject: vi.fn(),
  updateProject: vi.fn(),
}));

vi.mock("@/customers/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/customers/api")>()),
  listCustomers: vi.fn(),
}));

vi.mock("@/users/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/users/api")>()),
  searchUserDirectory: vi.fn(),
}));

vi.mock("@/admin/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/admin/api")>()),
  getRemovalImpact: vi.fn(),
}));

const archivedProject: Project = { ...testProject, id: "p2", name: "Archived Project", is_active: false };

function page(items = [testProject]): ProjectPage {
  return { items, total: items.length, limit: 20, offset: 0 };
}

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(fetchCurrentUser).mockResolvedValue(testAdmin);
  vi.mocked(listProjects).mockResolvedValue(page());
  vi.mocked(listCustomers).mockResolvedValue({
    items: [testCustomer],
    total: 1,
    limit: 100,
    offset: 0,
  });
  vi.mocked(getRemovalImpact).mockResolvedValue({
    is_active: true,
    can_delete_permanently: true,
    blockers: [],
    effects: [],
  });
  vi.mocked(searchUserDirectory).mockResolvedValue([]);
});

describe("AdminProjectsPage", () => {
  it("renders the project list with filters", async () => {
    renderApp("/admin/projects");

    const nameCell = await screen.findByText(testProject.name);
    const row = nameCell.closest("tr")!;
    expect(within(row).getByText(testProject.customer.name)).toBeTruthy();
  });

  it("creates a project and stays on the admin page", async () => {
    vi.mocked(createProject).mockResolvedValue({ ...testProject, id: "new-id" });
    renderApp("/admin/projects");
    await screen.findByText(testProject.name);

    fireEvent.click(screen.getByRole("button", { name: "New project" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("combobox", { name: "Customer" }));
    fireEvent.click(await screen.findByRole("option", { name: testCustomer.name }));
    fireEvent.change(within(dialog).getByRole("textbox", { name: "Name" }), {
      target: { value: "New Project" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Create project" }));

    await waitFor(() => expect(createProject).toHaveBeenCalled());
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(await screen.findByRole("heading", { name: "Projects" })).toBeTruthy();
  });

  it("shows a rule error when restoring under an archived customer", async () => {
    vi.mocked(listProjects).mockResolvedValue(page([archivedProject]));
    vi.mocked(updateProject).mockRejectedValue(new ProjectRuleError("Customer is archived"));
    renderApp("/admin/projects");
    const row = (await screen.findByText(archivedProject.name)).closest("tr")!;

    fireEvent.click(within(row).getByRole("button", { name: "Actions" }));
    fireEvent.click(await screen.findByRole("menuitem", { name: "Restore" }));

    expect(await screen.findByText("Customer is archived")).toBeTruthy();
  });

  it("opens the remove dialog from the row menu", async () => {
    renderApp("/admin/projects");
    const row = (await screen.findByText(testProject.name)).closest("tr")!;

    fireEvent.click(within(row).getByRole("button", { name: "Actions" }));
    fireEvent.click(await screen.findByRole("menuitem", { name: "Remove…" }));

    expect(await screen.findByRole("heading", { name: "Remove project" })).toBeTruthy();
  });
});
