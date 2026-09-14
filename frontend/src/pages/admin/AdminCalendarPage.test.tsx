import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  importPublicHolidays,
  listNonWorkingDays,
  NonWorkingDayConflictError,
  updateNonWorkingDay,
} from "@/calendar/api";
import { fetchCurrentUser } from "@/auth/api";
import { testAdmin, testNonWorkingDay } from "@/test/fixtures";
import { renderApp } from "@/test/renderApp";

vi.mock("@/auth/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/auth/api")>()),
  fetchCurrentUser: vi.fn(),
}));

vi.mock("@/calendar/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/calendar/api")>()),
  listNonWorkingDays: vi.fn(),
  addNonWorkingDay: vi.fn(),
  updateNonWorkingDay: vi.fn(),
  deleteNonWorkingDay: vi.fn(),
  importPublicHolidays: vi.fn(),
}));

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(fetchCurrentUser).mockResolvedValue(testAdmin);
  vi.mocked(listNonWorkingDays).mockResolvedValue([testNonWorkingDay]);
});

describe("AdminCalendarPage", () => {
  it("lists the year's non-working days", async () => {
    renderApp("/admin/calendar");

    await screen.findByText(testNonWorkingDay.name);
    expect(screen.getByText(testNonWorkingDay.day)).toBeTruthy();
    expect(screen.getByText("Company day off")).toBeTruthy();
    expect(listNonWorkingDays).toHaveBeenCalledWith(new Date().getFullYear());
  });

  it("shows a conflict error when saving hits a taken date", async () => {
    // Editing (rather than adding) exercises the same error-surfacing form code without needing
    // to drive Mantine's DatePickerInput calendar popup — the date field keeps its pre-filled,
    // already-valid value.
    vi.mocked(updateNonWorkingDay).mockRejectedValue(new NonWorkingDayConflictError());
    renderApp("/admin/calendar");
    await screen.findByText(testNonWorkingDay.name);

    fireEvent.click(screen.getByRole("button", { name: "Actions" }));
    fireEvent.click(await screen.findByRole("menuitem", { name: "Edit" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByRole("textbox", { name: "Name" }), {
      target: { value: "Renamed" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save changes" }));

    await screen.findByText(new NonWorkingDayConflictError().message);
  });

  it("imports public holidays and shows a confirmation", async () => {
    vi.mocked(importPublicHolidays).mockResolvedValue(9);
    renderApp("/admin/calendar");
    await screen.findByText(testNonWorkingDay.name);

    const year = new Date().getFullYear();
    fireEvent.click(screen.getByRole("button", { name: `Import public holidays for ${year}` }));

    await waitFor(() => {
      expect(importPublicHolidays).toHaveBeenCalledWith(year);
    });
    await screen.findByText(`Added 9 days for ${year}`);
  });
});
