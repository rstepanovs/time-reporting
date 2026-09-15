import { MantineProvider } from "@mantine/core";
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MemoryRouter } from "react-router";

import { MonthCalendarTable } from "@/timesheets/MonthCalendarTable";
import { testMonthCalendar } from "@/test/fixtures";
import { theme } from "@/theme";

// testMonthCalendar's "today" (2026-09-15) matches the fixture's own booked/missing days; see
// test/fixtures.ts for the week-by-week layout this exercises.
const TODAY = "2026-09-15";

function renderTable(props: Partial<Parameters<typeof MonthCalendarTable>[0]> = {}) {
  render(
    <MantineProvider theme={theme} env="test">
      <MemoryRouter>
        <MonthCalendarTable calendar={testMonthCalendar} today={TODAY} {...props} />
      </MemoryRouter>
    </MantineProvider>,
  );
}

describe("MonthCalendarTable", () => {
  it("shows a default heading from the calendar's year and month", () => {
    renderTable();
    expect(screen.getByRole("heading", { level: 3, name: "September 2026" })).toBeTruthy();
  });

  it("overrides the heading, or hides it, via the title prop", () => {
    const { unmount } = render(
      <MantineProvider theme={theme} env="test">
        <MemoryRouter>
          <MonthCalendarTable calendar={testMonthCalendar} today={TODAY} title="Custom" />
        </MemoryRouter>
      </MantineProvider>,
    );
    expect(screen.getByRole("heading", { level: 3, name: "Custom" })).toBeTruthy();
    unmount();

    renderTable({ title: "" });
    expect(screen.queryByRole("heading", { level: 3 })).toBeNull();
  });

  it("marks each day's kind and status, and links the week number to its timesheet", () => {
    renderTable();

    const table = screen.getByRole("table");
    const holidayCell = within(table).getByText("16").closest("td");
    expect(holidayCell?.getAttribute("data-kind")).toBe("company_day_off");

    // Sep 7 is a fully-booked past working day (8 of 8 expected hours).
    const bookedDayCell = within(table).getByText("7").closest("td");
    expect(bookedDayCell?.getAttribute("data-status")).toBe("complete");

    const weekLink = within(table).getByRole("link", { name: "37" });
    expect(weekLink.getAttribute("href")).toBe("/timesheet?week=2026-09-07");
  });

  it("shows the week and month totals", () => {
    renderTable();

    expect(screen.getByText("6 / 32 h")).toBeTruthy();
    expect(screen.getByText(/46 h booked/)).toBeTruthy();
  });
});
