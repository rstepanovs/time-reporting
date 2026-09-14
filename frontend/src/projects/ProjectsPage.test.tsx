import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { fetchCurrentUser } from "@/auth/api";
import { listCustomers } from "@/customers/api";
import { createProject, listProjects, ProjectConflictError } from "@/projects/api";
import { testCustomer, testProject, testUser, testWorker } from "@/test/fixtures";
import { renderApp } from "@/test/renderApp";

vi.mock("@/auth/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/auth/api")>()),
  fetchCurrentUser: vi.fn(),
}));

vi.mock("@/customers/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/customers/api")>()),
  listCustomers: vi.fn(),
}));

vi.mock("@/projects/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/projects/api")>()),
  listProjects: vi.fn(),
  createProject: vi.fn(),
}));

const customerPage = { items: [testCustomer], total: 1, limit: 100, offset: 0 };
const projectPage = { items: [testProject], total: 1, limit: 20, offset: 0 };

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(listCustomers).mockResolvedValue(customerPage);
  vi.mocked(listProjects).mockResolvedValue(projectPage);
});

describe("ProjectsPage", () => {
  it("renders the project name, customer and status", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testUser);
    renderApp("/projects");

    await screen.findByText(testProject.name);
    const row = screen.getByRole("row", { name: new RegExp(testProject.name) });
    expect(within(row).getByText(testCustomer.name)).toBeTruthy();
    expect(within(row).getByText("Active")).toBeTruthy();
  });

  it("toggling 'Show archived' requests archived projects too", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testUser);
    renderApp("/projects");
    await screen.findByText(testProject.name);

    fireEvent.click(screen.getByRole("switch", { name: "Show archived" }));

    await waitFor(() => {
      expect(listProjects).toHaveBeenCalledWith(
        expect.objectContaining({ includeInactive: true }),
      );
    });
  });

  it("does not show 'New project' to a worker", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testWorker);
    renderApp("/projects");

    await screen.findByText(testProject.name);
    expect(screen.queryByRole("button", { name: "New project" })).toBeNull();
  });

  it("lets a manager create a project and navigates to its details", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testUser);
    const created = { ...testProject, id: "new-project-id", name: "New Project" };
    vi.mocked(createProject).mockResolvedValue(created);
    renderApp("/projects");
    await screen.findByText(testProject.name);

    fireEvent.click(screen.getByRole("button", { name: "New project" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("combobox", { name: "Customer" }));
    fireEvent.click(await screen.findByRole("option", { name: testCustomer.name }));
    fireEvent.change(within(dialog).getByRole("textbox", { name: "Name" }), {
      target: { value: "New Project" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Create project" }));

    await waitFor(() => {
      expect(createProject).toHaveBeenCalledWith(
        { customerId: testCustomer.id, name: "New Project", description: null },
        expect.anything(),
      );
    });
  });

  it("shows a name conflict error from the create form", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testUser);
    vi.mocked(createProject).mockRejectedValue(new ProjectConflictError());
    renderApp("/projects");
    await screen.findByText(testProject.name);

    fireEvent.click(screen.getByRole("button", { name: "New project" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("combobox", { name: "Customer" }));
    fireEvent.click(await screen.findByRole("option", { name: testCustomer.name }));
    fireEvent.change(within(dialog).getByRole("textbox", { name: "Name" }), {
      target: { value: testProject.name },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Create project" }));

    expect(
      await within(dialog).findByText(
        "A project with this name already exists for this customer",
      ),
    ).toBeTruthy();
  });
});
