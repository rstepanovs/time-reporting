import { MantineProvider } from "@mantine/core";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { testYearHours } from "@/test/fixtures";
import { theme } from "@/theme";
import { YearHoursTableView } from "@/timesheets/YearHoursTableView";

function renderView(props: Partial<Parameters<typeof YearHoursTableView>[0]> = {}) {
  render(
    <MantineProvider theme={theme} env="test">
      <YearHoursTableView data={testYearHours} {...props} />
    </MantineProvider>,
  );
}

describe("YearHoursTableView", () => {
  it("shows a default heading from the data's year", () => {
    renderView();
    expect(screen.getByRole("heading", { level: 3, name: "2026" })).toBeTruthy();
  });

  it("overrides the heading, or hides it, via the title prop", () => {
    const { unmount } = render(
      <MantineProvider theme={theme} env="test">
        <YearHoursTableView data={testYearHours} title="Custom" />
      </MantineProvider>,
    );
    expect(screen.getByRole("heading", { level: 3, name: "Custom" })).toBeTruthy();
    unmount();

    renderView({ title: "" });
    expect(screen.queryByRole("heading", { level: 3 })).toBeNull();
  });

  it("hides the Other column when no month has other-preset hours", () => {
    renderView();
    expect(screen.queryByText("Other")).toBeNull();
  });

  it("expands a month into its per-project breakdown", async () => {
    renderView();

    expect(screen.queryByText(/Website Revamp/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Expand September" }));

    expect(await screen.findByText(/Website Revamp/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Collapse September" }));
    expect(screen.queryByText(/Website Revamp/)).toBeNull();
  });

  it("badges the current month as in progress and shows a delta for a past month", () => {
    renderView();

    expect(screen.getByText("In progress")).toBeTruthy();
    // August: total 172.00 vs expected-to-date 168.00 -> +4.
    expect(screen.getByText("+4")).toBeTruthy();
  });

  it("shows an empty state when no months are listed", () => {
    renderView({ data: { ...testYearHours, months: [] } });
    expect(screen.getByText("No hours booked this year yet.")).toBeTruthy();
  });
});
