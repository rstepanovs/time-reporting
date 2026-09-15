import { describe, expect, it } from "vitest";

import { dayStatus } from "@/timesheets/dayStatus";
import type { CalendarDayHours } from "@/timesheets/api";

const TODAY = "2026-09-15";

function day(overrides: Partial<CalendarDayHours> = {}): CalendarDayHours {
  return {
    calendar_day: { day: TODAY, is_weekend: false, non_working_day: null },
    in_month: true,
    is_working_day: true,
    expected_hours: "8.00",
    hours: "0.00",
    ...overrides,
  };
}

describe("dayStatus", () => {
  it("flags today regardless of hours booked", () => {
    expect(dayStatus(day({ calendar_day: { day: TODAY, is_weekend: false, non_working_day: null } }), TODAY)).toBe(
      "today",
    );
  });

  it("flags a non-working day with nothing booked as off", () => {
    const off = day({
      calendar_day: { day: "2026-09-19", is_weekend: true, non_working_day: null },
      is_working_day: false,
    });
    expect(dayStatus(off, TODAY)).toBe("off");
  });

  it("flags hours booked on a non-working day as extra, even before today", () => {
    const extra = day({
      calendar_day: { day: "2026-09-19", is_weekend: true, non_working_day: null },
      is_working_day: false,
      hours: "2.00",
    });
    expect(dayStatus(extra, TODAY)).toBe("extra");
  });

  it("flags a working day after today as future", () => {
    const future = day({ calendar_day: { day: "2026-09-16", is_weekend: false, non_working_day: null } });
    expect(dayStatus(future, TODAY)).toBe("future");
  });

  it("flags a past working day with no hours as missing", () => {
    const missing = day({ calendar_day: { day: "2026-09-14", is_weekend: false, non_working_day: null } });
    expect(dayStatus(missing, TODAY)).toBe("missing");
  });

  it("flags a past working day with some but not all expected hours as partial", () => {
    const partial = day({
      calendar_day: { day: "2026-09-14", is_weekend: false, non_working_day: null },
      hours: "4.00",
    });
    expect(dayStatus(partial, TODAY)).toBe("partial");
  });

  it("flags a past working day with at least the expected hours as complete", () => {
    const complete = day({
      calendar_day: { day: "2026-09-14", is_weekend: false, non_working_day: null },
      hours: "8.00",
    });
    expect(dayStatus(complete, TODAY)).toBe("complete");
  });
});
