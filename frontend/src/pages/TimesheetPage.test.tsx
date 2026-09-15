import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { fetchCurrentUser } from "@/auth/api";
import {
  approveTimesheetWeek,
  getTimesheetWeek,
  listTimesheetOptions,
  returnTimesheetWeek,
  saveTimesheetWeek,
  submitTimesheetWeek,
  TimesheetRuleError,
} from "@/timesheets/api";
import {
  TEST_WEEK_START,
  testTimesheetOption,
  testTimesheetRow,
  testTimesheetWeek,
  testUser,
  testWorker,
} from "@/test/fixtures";
import { renderApp } from "@/test/renderApp";
import { searchUserDirectory } from "@/users/api";

vi.mock("@/auth/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/auth/api")>()),
  fetchCurrentUser: vi.fn(),
}));

vi.mock("@/timesheets/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/timesheets/api")>()),
  getTimesheetWeek: vi.fn(),
  saveTimesheetWeek: vi.fn(),
  listTimesheetOptions: vi.fn(),
  submitTimesheetWeek: vi.fn(),
  approveTimesheetWeek: vi.fn(),
  returnTimesheetWeek: vi.fn(),
}));

vi.mock("@/users/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/users/api")>()),
  searchUserDirectory: vi.fn(),
}));

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(getTimesheetWeek).mockResolvedValue(testTimesheetWeek);
  vi.mocked(listTimesheetOptions).mockResolvedValue([testTimesheetOption]);
  vi.mocked(searchUserDirectory).mockResolvedValue([]);
});

const CELL_NAME = `${testTimesheetRow.billing_item.name} 2026-09-14`;
const TUESDAY_CELL_NAME = `${testTimesheetRow.billing_item.name} 2026-09-15`;

describe("TimesheetPage", () => {
  it("marks weekend and non-working-day columns", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testWorker);
    renderApp("/timesheet");

    await screen.findByText(testTimesheetRow.billing_item.name);
    const table = screen.getByRole("table");
    const weekendHeader = within(table).getByText("Sat 19.09").closest("th");
    const holidayHeader = within(table).getByText("Wed 16.09").closest("th");
    const workdayHeader = within(table).getByText("Mon 14.09").closest("th");

    expect(weekendHeader?.getAttribute("data-kind")).toBe("weekend");
    expect(holidayHeader?.getAttribute("data-kind")).toBe("company_day_off");
    expect(workdayHeader?.getAttribute("data-kind")).toBe("workday");
  });

  it("lets the owner enter and save a value", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testWorker);
    vi.mocked(saveTimesheetWeek).mockResolvedValue(testTimesheetWeek);
    renderApp("/timesheet");
    await screen.findByText(testTimesheetRow.billing_item.name);

    fireEvent.change(screen.getByRole("textbox", { name: TUESDAY_CELL_NAME }), {
      target: { value: "6" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => {
      expect(saveTimesheetWeek).toHaveBeenCalledWith(
        TEST_WEEK_START,
        [
          {
            billing_item_id: testTimesheetRow.billing_item.id,
            date: "2026-09-15",
            quantity: 6,
            note: null,
          },
        ],
        [],
      );
    });
  });

  it("sends quantity: null when clearing an existing cell", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testWorker);
    vi.mocked(saveTimesheetWeek).mockResolvedValue({ ...testTimesheetWeek, rows: [] });
    renderApp("/timesheet");
    await screen.findByText(testTimesheetRow.billing_item.name);

    fireEvent.change(screen.getByRole("textbox", { name: CELL_NAME }), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => {
      expect(saveTimesheetWeek).toHaveBeenCalledWith(
        TEST_WEEK_START,
        [
          {
            billing_item_id: testTimesheetRow.billing_item.id,
            date: "2026-09-14",
            quantity: null,
            note: null,
          },
        ],
        [],
      );
    });
  });

  it("renders a closed row read-only", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testWorker);
    vi.mocked(getTimesheetWeek).mockResolvedValue({
      ...testTimesheetWeek,
      rows: [{ ...testTimesheetRow, is_open: false }],
    });
    renderApp("/timesheet");

    await screen.findByText(testTimesheetRow.billing_item.name);
    expect(screen.getByText("Closed")).toBeTruthy();
    expect(screen.queryByRole("textbox", { name: CELL_NAME })).toBeNull();
  });

  it("renders a row's billed dates read-only and shows a locked notice", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testWorker);
    vi.mocked(getTimesheetWeek).mockResolvedValue({
      ...testTimesheetWeek,
      rows: [{ ...testTimesheetRow, locked_dates: ["2026-09-14"] }],
    });
    renderApp("/timesheet");

    await screen.findByText(testTimesheetRow.billing_item.name);
    expect(screen.getByText("Sent to billing")).toBeTruthy();
    // The locked date's cell is read-only...
    expect(screen.queryByRole("textbox", { name: CELL_NAME })).toBeNull();
    // ...but a different date on the same row stays editable.
    expect(screen.getByRole("textbox", { name: TUESDAY_CELL_NAME })).toBeTruthy();
    // The whole row can't be deleted once any of its dates are locked.
    expect(
      screen.queryByRole("button", { name: `Delete row ${testTimesheetRow.billing_item.name}` }),
    ).toBeNull();
  });

  it("shows a rule error from the server", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testWorker);
    vi.mocked(saveTimesheetWeek).mockRejectedValue(new TimesheetRuleError("Total hours too high"));
    renderApp("/timesheet");
    await screen.findByText(testTimesheetRow.billing_item.name);

    fireEvent.change(screen.getByRole("textbox", { name: TUESDAY_CELL_NAME }), {
      target: { value: "6" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await screen.findByText("Total hours too high");
  });

  it("a project manager viewing another user's week sees no inputs", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testUser); // a project manager
    vi.mocked(getTimesheetWeek).mockResolvedValue({ ...testTimesheetWeek, can_edit: false });
    renderApp(`/timesheet?user=${testWorker.id}`);

    await screen.findByText(testTimesheetRow.billing_item.name);
    expect(screen.getByText(/read-only/)).toBeTruthy();
    expect(screen.queryByRole("textbox", { name: CELL_NAME })).toBeNull();
    expect(screen.queryByRole("button", { name: "Save" })).toBeNull();
  });

  it("a worker cannot pick another user", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testWorker);
    renderApp("/timesheet");

    await screen.findByText(testTimesheetRow.billing_item.name);
    expect(screen.queryByRole("combobox", { name: "Viewing" })).toBeNull();
  });

  it("adds a row via the Add row modal", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testWorker);
    renderApp("/timesheet");
    await screen.findByText(testTimesheetRow.billing_item.name);

    fireEvent.click(screen.getByRole("button", { name: "Add row" }));
    const dialog = await screen.findByRole("dialog");
    await waitFor(() => {
      const projectField = within(dialog).getByRole("combobox", { name: "Project" });
      expect((projectField as HTMLInputElement).disabled).toBe(false);
    });

    fireEvent.click(within(dialog).getByRole("combobox", { name: "Project" }));
    fireEvent.click(await screen.findByRole("option", { name: testTimesheetOption.project.name }));
    fireEvent.click(within(dialog).getByRole("combobox", { name: "Billing item" }));
    fireEvent.click(await screen.findByRole("option", { name: "Overtime working hours" }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Add row" }));

    await screen.findByText("Overtime working hours");
  });

  it("copies open rows from the previous week that aren't already shown", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testWorker);
    const overtimeRow = {
      ...testTimesheetRow,
      billing_item: testTimesheetOption.billing_items[1],
      entries: [],
    };
    vi.mocked(getTimesheetWeek).mockResolvedValueOnce(testTimesheetWeek);
    vi.mocked(getTimesheetWeek).mockResolvedValueOnce({
      ...testTimesheetWeek,
      rows: [testTimesheetRow, overtimeRow],
    });
    renderApp("/timesheet");
    await screen.findByText(testTimesheetRow.billing_item.name);
    expect(screen.queryByText("Overtime working hours")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Copy rows from previous week" }));

    await screen.findByText("Overtime working hours");
  });

  it("prefills an empty draft week with normal hours when there's exactly one open project", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testWorker);
    vi.mocked(getTimesheetWeek).mockResolvedValue({ ...testTimesheetWeek, rows: [] });
    renderApp("/timesheet");

    const mondayCell = (await screen.findByRole("textbox", {
      name: CELL_NAME,
    })) as HTMLInputElement;
    expect(mondayCell.value).toBe("8");
    const tuesdayCell = screen.getByRole("textbox", { name: TUESDAY_CELL_NAME }) as HTMLInputElement;
    expect(tuesdayCell.value).toBe("8");
    // 2026-09-16 is the custom non-working day in testCalendarDays — not prefilled.
    const wednesdayCell = screen.getByRole("textbox", {
      name: `${testTimesheetRow.billing_item.name} 2026-09-16`,
    }) as HTMLInputElement;
    expect(wednesdayCell.value).toBe("");
  });

  it("does not prefill when the user has more than one open project", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testWorker);
    vi.mocked(getTimesheetWeek).mockResolvedValue({ ...testTimesheetWeek, rows: [] });
    vi.mocked(listTimesheetOptions).mockResolvedValue([
      testTimesheetOption,
      { ...testTimesheetOption, project: { ...testTimesheetOption.project, id: "other-project" } },
    ]);
    renderApp("/timesheet");

    await screen.findByText("No rows yet. Add one to start booking time.");
    expect(screen.queryByRole("textbox", { name: CELL_NAME })).toBeNull();
  });

  it("sends a row comment on save", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testWorker);
    vi.mocked(saveTimesheetWeek).mockResolvedValue(testTimesheetWeek);
    renderApp("/timesheet");
    await screen.findByText(testTimesheetRow.billing_item.name);

    fireEvent.click(
      screen.getByRole("button", { name: `Comment for ${testTimesheetRow.billing_item.name}` }),
    );
    fireEvent.change(
      screen.getByRole("textbox", {
        name: `Comment text for ${testTimesheetRow.billing_item.name}`,
      }),
      { target: { value: "Please review" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => {
      expect(saveTimesheetWeek).toHaveBeenCalledWith(TEST_WEEK_START, [], [
        { billing_item_id: testTimesheetRow.billing_item.id, comment: "Please review" },
      ]);
    });
  });

  it("deletes a saved row on save", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testWorker);
    vi.mocked(saveTimesheetWeek).mockResolvedValue({ ...testTimesheetWeek, rows: [] });
    renderApp("/timesheet");
    await screen.findByText(testTimesheetRow.billing_item.name);

    fireEvent.click(
      screen.getByRole("button", { name: `Delete row ${testTimesheetRow.billing_item.name}` }),
    );
    expect(screen.queryByText(testTimesheetRow.billing_item.name)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => {
      expect(saveTimesheetWeek).toHaveBeenCalledWith(
        TEST_WEEK_START,
        [{ billing_item_id: testTimesheetRow.billing_item.id, date: "2026-09-14", quantity: null }],
        [],
      );
    });
  });

  it("renders a submitted week read-only with no Save or Submit button", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testWorker);
    vi.mocked(getTimesheetWeek).mockResolvedValue({
      ...testTimesheetWeek,
      status: "submitted",
      submitted_at: "2026-09-14T09:00:00Z",
      can_edit: false,
      can_submit: false,
    });
    renderApp("/timesheet");

    await screen.findByText(testTimesheetRow.billing_item.name);
    expect(screen.getByText("Submitted")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Save" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Submit" })).toBeNull();
    expect(screen.queryByRole("textbox", { name: CELL_NAME })).toBeNull();
  });

  it("lets a submitted week be submitted after confirmation", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testWorker);
    vi.mocked(submitTimesheetWeek).mockResolvedValue({
      ...testTimesheetWeek,
      status: "submitted",
      can_edit: false,
      can_submit: false,
    });
    renderApp("/timesheet");
    await screen.findByText(testTimesheetRow.billing_item.name);

    fireEvent.click(screen.getByRole("button", { name: "Submit" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Submit" }));

    await waitFor(() => {
      expect(submitTimesheetWeek).toHaveBeenCalled();
    });
  });

  it("a manager must enter a comment before returning a week", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testUser); // a project manager
    vi.mocked(getTimesheetWeek).mockResolvedValue({
      ...testTimesheetWeek,
      status: "submitted",
      can_edit: false,
      can_submit: false,
      can_review: true,
    });
    renderApp(`/timesheet?user=${testWorker.id}`);
    await screen.findByText(testTimesheetRow.billing_item.name);

    fireEvent.click(screen.getByRole("button", { name: "Return…" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("button", { name: "Return" }).hasAttribute("disabled")).toBe(
      true,
    );

    fireEvent.change(within(dialog).getByRole("textbox", { name: "Comment" }), {
      target: { value: "Please add the missing hours" },
    });
    vi.mocked(returnTimesheetWeek).mockResolvedValue({
      ...testTimesheetWeek,
      status: "returned",
      return_comment: "Please add the missing hours",
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Return" }));

    await waitFor(() => {
      expect(returnTimesheetWeek).toHaveBeenCalledWith({
        weekStart: TEST_WEEK_START,
        userId: testWorker.id,
        comment: "Please add the missing hours",
      });
    });
  });

  it("a manager can approve a submitted week", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testUser); // a project manager
    vi.mocked(getTimesheetWeek).mockResolvedValue({
      ...testTimesheetWeek,
      status: "submitted",
      can_edit: false,
      can_submit: false,
      can_review: true,
    });
    vi.mocked(approveTimesheetWeek).mockResolvedValue({
      ...testTimesheetWeek,
      status: "approved",
      can_review: false,
    });
    renderApp(`/timesheet?user=${testWorker.id}`);
    await screen.findByText(testTimesheetRow.billing_item.name);

    fireEvent.click(screen.getByRole("button", { name: "Approve" }));

    await waitFor(() => {
      expect(approveTimesheetWeek).toHaveBeenCalledWith({
        weekStart: TEST_WEEK_START,
        userId: testWorker.id,
      });
    });
  });

  it("asks for confirmation before discarding unsaved changes on navigation", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testWorker);
    renderApp("/timesheet");
    await screen.findByText(testTimesheetRow.billing_item.name);

    fireEvent.change(screen.getByRole("textbox", { name: TUESDAY_CELL_NAME }), {
      target: { value: "6" },
    });
    fireEvent.click(screen.getByRole("button", { name: "This week" }));

    await screen.findByRole("heading", { name: "Discard unsaved changes?" });
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    const cell = screen.getByRole("textbox", { name: TUESDAY_CELL_NAME }) as HTMLInputElement;
    expect(cell.value).toBe("6");
  });
});
