import { describe, expect, it } from "vitest";

import {
  addDays,
  addMonths,
  addWeeks,
  formatDayLabel,
  formatHours,
  formatMonthLabel,
  formatWeekLabel,
  isWeekend,
  previousMonth,
  startOfIsoWeek,
  weekDays,
} from "@/timesheets/week";

describe("startOfIsoWeek", () => {
  it("returns the same date when it is already a Monday", () => {
    expect(startOfIsoWeek("2026-09-14")).toBe("2026-09-14");
  });

  it("returns the Monday of the week for any other weekday", () => {
    expect(startOfIsoWeek("2026-09-16")).toBe("2026-09-14"); // Wednesday
    expect(startOfIsoWeek("2026-09-20")).toBe("2026-09-14"); // Sunday
  });

  it("handles a month boundary", () => {
    expect(startOfIsoWeek("2026-10-01")).toBe("2026-09-28"); // Thursday
  });
});

describe("weekDays", () => {
  it("lists all seven ISO dates starting at the given Monday", () => {
    expect(weekDays("2026-09-14")).toEqual([
      "2026-09-14",
      "2026-09-15",
      "2026-09-16",
      "2026-09-17",
      "2026-09-18",
      "2026-09-19",
      "2026-09-20",
    ]);
  });
});

describe("addDays / addWeeks", () => {
  it("adds and subtracts days across a month boundary", () => {
    expect(addDays("2026-09-30", 1)).toBe("2026-10-01");
    expect(addDays("2026-10-01", -1)).toBe("2026-09-30");
  });

  it("adds and subtracts whole weeks", () => {
    expect(addWeeks("2026-09-14", 1)).toBe("2026-09-21");
    expect(addWeeks("2026-09-14", -1)).toBe("2026-09-07");
  });
});

describe("isWeekend", () => {
  it("flags Saturday and Sunday only", () => {
    expect(isWeekend("2026-09-18")).toBe(false); // Friday
    expect(isWeekend("2026-09-19")).toBe(true); // Saturday
    expect(isWeekend("2026-09-20")).toBe(true); // Sunday
    expect(isWeekend("2026-09-21")).toBe(false); // Monday
  });
});

describe("formatDayLabel", () => {
  it("formats as weekday + day.month", () => {
    expect(formatDayLabel("2026-09-14")).toBe("Mon 14.09");
    expect(formatDayLabel("2026-09-20")).toBe("Sun 20.09");
  });
});

describe("formatWeekLabel", () => {
  it("shows the month once when the week stays within it", () => {
    expect(formatWeekLabel("2026-09-14")).toBe("14 – 20 Sep 2026");
  });

  it("shows both months when the week spans a month boundary", () => {
    expect(formatWeekLabel("2026-09-28")).toBe("28 Sep – 4 Oct 2026");
  });
});

describe("formatMonthLabel", () => {
  it("formats as full month name + year", () => {
    expect(formatMonthLabel(2026, 9)).toBe("September 2026");
    expect(formatMonthLabel(2026, 1)).toBe("January 2026");
  });
});

describe("formatHours", () => {
  it("drops a trailing .00", () => {
    expect(formatHours("8.00")).toBe("8");
    expect(formatHours("0.00")).toBe("0");
  });

  it("drops only a trailing zero, keeping the rest", () => {
    expect(formatHours("8.50")).toBe("8.5");
  });

  it("keeps two decimal places when both are significant", () => {
    expect(formatHours("8.25")).toBe("8.25");
  });
});

describe("addMonths", () => {
  it("shifts within the same year", () => {
    expect(addMonths(2026, 9, 1)).toEqual({ year: 2026, month: 10 });
    expect(addMonths(2026, 9, -1)).toEqual({ year: 2026, month: 8 });
  });

  it("carries over into the next or previous year", () => {
    expect(addMonths(2026, 12, 1)).toEqual({ year: 2027, month: 1 });
    expect(addMonths(2026, 1, -1)).toEqual({ year: 2025, month: 12 });
  });

  it("handles a multi-year jump", () => {
    expect(addMonths(2026, 1, -13)).toEqual({ year: 2024, month: 12 });
  });
});

describe("previousMonth", () => {
  it("is addMonths(..., -1)", () => {
    expect(previousMonth(2026, 9)).toEqual({ year: 2026, month: 8 });
    expect(previousMonth(2026, 1)).toEqual({ year: 2025, month: 12 });
  });
});
